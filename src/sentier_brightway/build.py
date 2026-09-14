"""Turn Sentier frames into the ``{(db, code): node}`` dicts ``bw2data.Database.write`` takes."""

from __future__ import annotations

import math
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from .bridge import BridgeEntry
from .constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB
from .inventory import Inventory
from .methods import MethodSpec
from .report import Coverage
from .units import normalize_unit

Key = tuple[str, str]

# stats_arrays ids whose support is positive: lognormal, bernoulli, weibull, gamma, beta.
# A negative amount under one of these carries ``negative: True`` and loc = ln(|amount|).
_POSITIVE_ONLY_DISTRIBUTIONS = frozenset({2, 6, 8, 9, 10})
_RESOURCE_PREFIXES = ("resources", "natural resource", "raw", "land use")
_MAX_EXAMPLES = 5


@dataclass(frozen=True)
class BoundMethod:
    key: tuple[str, ...]
    unit: str
    description: str
    method_id: str
    cfs: tuple[tuple[Key, float], ...]


@dataclass(frozen=True)
class BuildResult:
    biosphere: Mapping[Key, dict]
    residual: Mapping[Key, dict]
    inventory: Mapping[Key, dict]
    methods: tuple[BoundMethod, ...]
    coverage: Coverage


def _is_null(value: object) -> bool:
    """True for None, float NaN and pandas NA (the real ``minimum``/``maximum`` columns are
    all-null ``string`` dtype, so ``pd.NA`` must be handled, not only float NaN)."""
    return value is None or bool(pd.isna(value))


def _node_type(categories: tuple[str, ...]) -> str:
    """bw2data flow type from the first category: resources are ``natural resource``."""
    first = categories[0].lower() if categories else ""
    return "natural resource" if first.startswith(_RESOURCE_PREFIXES) else "emission"


# ----------------------------------------------------------------------------- biosphere


def _bridge_units(bridge: Mapping[str, BridgeEntry]) -> tuple[dict[str, str], tuple[str, ...]]:
    """First normalised target unit per EF code (bridge order), plus the codes whose entries
    disagree on the unit, in the order they were first seen."""
    seen: dict[str, set[str]] = defaultdict(set)
    units: dict[str, str] = {}
    for entry in bridge.values():
        unit = normalize_unit(entry.target_unit)
        units.setdefault(entry.target_code, unit)
        seen[entry.target_code].add(unit)
    conflicts = tuple(code for code, found in seen.items() if len(found) > 1)
    return units, conflicts


def _warn_unit_conflicts(conflicts: tuple[str, ...]) -> None:
    if conflicts:
        examples = ", ".join(conflicts[:3])
        warnings.warn(
            f"{len(conflicts)} EF flows are targeted with conflicting units in the bridge "
            f"(e.g. {examples}); the first package's unit is kept",
            stacklevel=2,
        )


def build_biosphere(
    ef_flows: pd.DataFrame, units: Mapping[str, str], methods: tuple[MethodSpec, ...]
) -> dict[Key, dict]:
    """One node per EF flow known to vocab, to any CF table, or to any bridge target.

    ``units`` is the first normalised target unit per EF code, as computed once by
    ``_bridge_units`` in ``build()`` (conflict warnings are also ``build()``'s job)."""
    names: dict[str, str] = dict(zip(ef_flows["code"], ef_flows["name"]))
    cas: dict[str, str | None] = dict(zip(ef_flows["code"], ef_flows["cas_number"]))
    # CF context is more specific than the vocab compartment, so it takes priority; among
    # methods the first one listing a flow wins, like names.
    cf_categories: dict[str, tuple[str, ...]] = {}
    for spec in methods:
        for code, name in spec.flow_name.items():
            names.setdefault(code, name)
        for code, ctx in spec.flow_context.items():
            if ctx:
                cf_categories.setdefault(code, ctx)
    categories = {**dict(zip(ef_flows["code"], ef_flows["categories"])), **cf_categories}
    nodes = {}
    for code in sorted(set(names) | set(units)):
        cats = tuple(categories.get(code, ()))
        node = {
            "name": names.get(code, code),
            "categories": cats,
            "unit": units.get(code, "kilogram"),
            "type": _node_type(cats),
            "exchanges": [],
        }
        if cas.get(code):
            node["CAS number"] = cas[code]
        nodes[(BIOSPHERE_DB, code)] = node
    return nodes


# ----------------------------------------------------------------------------- residual


def build_residual(
    unmapped_codes: set[str], bafu_flows: pd.DataFrame, exchanges: pd.DataFrame
) -> dict[Key, dict]:
    vocab = bafu_flows.set_index("code")
    bio = exchanges[exchanges["flow_type"] == "biosphere"]
    by_code = bio.drop_duplicates("flow").set_index("flow")
    nodes = {}
    for code in sorted(unmapped_codes):
        name = str(vocab["name"].get(code, by_code["flow_name"].get(code, code)))
        cats = tuple(vocab["categories"].get(code, ()))
        nodes[(RESIDUAL_DB, code)] = {
            "name": name,
            "categories": cats,
            "unit": normalize_unit(by_code["unit"].get(code)),
            "type": _node_type(cats),
            "exchanges": [],
        }
    return nodes


# ----------------------------------------------------------------------------- inventory

EXCHANGE_FIELDS = (
    "process_id",
    "flow",
    "flow_name",
    "flow_type",
    "amount",
    "unit",
    "uncertainty_type",
    "loc",
    "scale",
    "minimum",
    "maximum",
)


def _column(df: pd.DataFrame, name: str) -> list:
    """One plain Python list per column, nulls (NaN and ``pd.NA``) normalised to ``None``."""
    s = df[name]
    return s.astype(object).where(s.notna(), None).tolist()


def _uncertainty(
    utype: object,
    loc: object,
    scale: object,
    minimum: object,
    maximum: object,
    factor: float,
    amount: float,
) -> dict:
    """bw2data uncertainty fields, rescaled when the amount was multiplied by ``factor``.

    ``amount`` is the already-scaled exchange amount; it only decides the ``negative`` flag."""
    if utype is None:
        return {}
    utype = int(utype)
    out: dict = {"uncertainty type": utype}
    if loc is not None:
        # lognormal: loc is ln(|amount|), so a multiplicative factor is an additive shift
        out["loc"] = float(loc) + math.log(factor) if utype == 2 else float(loc) * factor
    if scale is not None:
        out["scale"] = float(scale) if utype == 2 else float(scale) * factor
    if minimum is not None:
        out["minimum"] = float(minimum) * factor
    if maximum is not None:
        out["maximum"] = float(maximum) * factor
    if amount < 0 and utype in _POSITIVE_ONLY_DISTRIBUTIONS:
        out["negative"] = True
    return out


def _link(pid: str, flow: str, flow_type: str, bridge: Mapping[str, BridgeEntry]) -> tuple:
    """``(input key, exchange type, target unit or None, conversion factor)`` for one row."""
    if flow_type == "production":
        return (INVENTORY_DB, pid), "production", None, 1.0
    if flow_type == "technosphere":
        return (INVENTORY_DB, flow), "technosphere", None, 1.0
    entry = bridge.get(flow)
    if entry is None:
        return (RESIDUAL_DB, flow), "biosphere", None, 1.0
    return (
        (BIOSPHERE_DB, entry.target_code),
        "biosphere",
        entry.target_unit,
        entry.conversion_factor,
    )


_VALID_FLOW_TYPES = frozenset({"production", "technosphere", "biosphere"})


def _check_links(processes: pd.DataFrame, exchanges: pd.DataFrame) -> None:
    """Fail fast on: unknown ``flow_type`` values, exchange rows owned by an unknown process,
    technosphere links to unknown processes, and processes whose exchange rows lack a
    production row (a process with no rows at all is allowed and stays empty)."""
    known = set(processes["process_id"])

    bad_types = sorted(set(exchanges["flow_type"]) - _VALID_FLOW_TYPES)
    if bad_types:
        raise ValueError(
            f"{len(bad_types)} exchange rows have unknown flow_type values: {bad_types}"
        )

    orphans = exchanges[~exchanges["process_id"].isin(known)]
    if not orphans.empty:
        owners = sorted(set(orphans["process_id"]))
        raise ValueError(
            f"{len(orphans)} exchange rows reference unknown processes, e.g. "
            f"{owners[:_MAX_EXAMPLES]}"
        )

    tech = exchanges[exchanges["flow_type"] == "technosphere"]
    dangling = tech[~tech["flow"].isin(known)]
    if not dangling.empty:
        pairs = list(dangling[["process_id", "flow"]].itertuples(index=False, name=None))
        raise ValueError(
            f"{len(dangling)} technosphere exchanges point at unknown processes, e.g. "
            f"{pairs[:_MAX_EXAMPLES]}"
        )
    with_rows = set(exchanges["process_id"])
    with_production = set(exchanges.loc[exchanges["flow_type"] == "production", "process_id"])
    missing = sorted((with_rows & known) - with_production)
    if missing:
        raise ValueError(
            f"{len(missing)} processes have exchanges but no production exchange, e.g. "
            f"{missing[:_MAX_EXAMPLES]}"
        )


def _exchanges_by_process(
    exchanges: pd.DataFrame, bridge: Mapping[str, BridgeEntry]
) -> dict[str, list[dict]]:
    """One column-wise pass over the exchange frame; far cheaper than per-row ``iterrows``."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    columns = [_column(exchanges, name) for name in EXCHANGE_FIELDS]
    for pid, flow, name, ftype, amount, unit, utype, loc, scale, mn, mx in zip(*columns):
        key, etype, target_unit, factor = _link(pid, flow, ftype, bridge)
        scaled = float(amount) * factor
        grouped[pid].append(
            {
                "input": key,
                "type": etype,
                "amount": scaled,
                "unit": normalize_unit(unit if target_unit is None else target_unit),
                "name": str(name),
                **_uncertainty(utype, loc, scale, mn, mx, factor, scaled),
            }
        )
    return grouped


def build_inventory(inventory: Inventory, bridge: Mapping[str, BridgeEntry]) -> dict[Key, dict]:
    _check_links(inventory.processes, inventory.exchanges)
    grouped = _exchanges_by_process(inventory.exchanges, bridge)
    nodes = {}
    for p in inventory.processes.itertuples(index=False):
        node = {
            "name": str(p.name),
            "reference product": str(p.reference_product),
            "unit": normalize_unit(p.reference_unit),
            "location": str(p.location),
            "type": "process",
            "production amount": float(p.reference_amount),
            "exchanges": grouped.get(p.process_id, []),
        }
        comment = getattr(p, "comment", None)
        if not _is_null(comment):
            node["comment"] = str(comment)
        nodes[(INVENTORY_DB, p.process_id)] = node
    return nodes


# ----------------------------------------------------------------------------- assembly


def _bind_methods(methods: tuple[MethodSpec, ...]) -> tuple[BoundMethod, ...]:
    return tuple(
        BoundMethod(
            key=m.key,
            unit=m.unit,
            description=m.description,
            method_id=m.method_id,
            cfs=tuple(((BIOSPHERE_DB, code), value) for code, value in m.cfs),
        )
        for m in methods
    )


def _coverage(
    bio: pd.DataFrame,
    unmapped: set[str],
    bridge: Mapping[str, BridgeEntry],
    bafu_flows: pd.DataFrame,
    processes: int,
    methods: int,
    unit_conflicts: int,
) -> Coverage:
    """Coverage over ``bio`` (the biosphere exchange rows) and the ``unmapped`` codes."""
    used = set(bio["flow"])
    compartments = dict(
        zip(bafu_flows["code"], (c[0] if c else "unknown" for c in bafu_flows["categories"]))
    )
    counter = Counter(compartments.get(code, "unknown") for code in unmapped)
    return Coverage(
        flows_used=len(used),
        flows_mapped=len(used) - len(unmapped),
        flows_nomenclature=sum(1 for code in used if code in bridge and bridge[code].nomenclature),
        exchange_rows=len(bio),
        exchange_rows_mapped=int(bio["flow"].isin(bridge.keys()).sum()),
        residual_by_compartment=tuple(sorted(counter.items())),
        processes=processes,
        methods=methods,
        unit_conflicts=unit_conflicts,
    )


def build(
    inventory: Inventory,
    ef_flows: pd.DataFrame,
    bafu_flows: pd.DataFrame,
    bridge: Mapping[str, BridgeEntry],
    methods: tuple[MethodSpec, ...],
) -> BuildResult:
    bio = inventory.exchanges[inventory.exchanges["flow_type"] == "biosphere"]
    unmapped = set(bio["flow"]) - set(bridge.keys())
    units, conflicts = _bridge_units(bridge)
    _warn_unit_conflicts(conflicts)
    return BuildResult(
        biosphere=build_biosphere(ef_flows, units, methods),
        residual=build_residual(unmapped, bafu_flows, inventory.exchanges),
        inventory=build_inventory(inventory, bridge),
        methods=_bind_methods(methods),
        coverage=_coverage(
            bio,
            unmapped,
            bridge,
            bafu_flows,
            processes=len(inventory.processes),
            methods=len(methods),
            unit_conflicts=len(conflicts),
        ),
    )
