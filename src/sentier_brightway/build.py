"""Turn Sentier frames into the ``{(db, code): node}`` dicts ``bw2data.Database.write`` takes."""

from __future__ import annotations

import math
from collections import Counter
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


# ----------------------------------------------------------------------------- biosphere


def _ef_units_from_bridge(bridge: Mapping[str, BridgeEntry]) -> dict[str, str]:
    units: dict[str, str] = {}
    for entry in bridge.values():
        units.setdefault(entry.target_code, normalize_unit(entry.target_unit))
    return units


def build_biosphere(
    ef_flows: pd.DataFrame, bridge: Mapping[str, BridgeEntry], methods: tuple[MethodSpec, ...]
) -> dict[Key, dict]:
    """One node per EF flow known to vocab, to any CF table, or to any bridge target."""
    names: dict[str, str] = dict(zip(ef_flows["code"], ef_flows["name"]))
    categories: dict[str, tuple[str, ...]] = dict(zip(ef_flows["code"], ef_flows["categories"]))
    cas: dict[str, str | None] = dict(zip(ef_flows["code"], ef_flows["cas_number"]))
    for spec in methods:
        for code, name in spec.flow_name.items():
            names.setdefault(code, name)
        for code, ctx in spec.flow_context.items():
            if ctx:
                categories[code] = ctx  # CF context is more specific than vocab compartment
    units = _ef_units_from_bridge(bridge)
    codes = set(names) | {e.target_code for e in bridge.values()}
    nodes = {}
    for code in sorted(codes):
        node = {
            "name": names.get(code, code),
            "categories": tuple(categories.get(code, ())),
            "unit": units.get(code, "kilogram"),
            "type": "emission",
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
    by_code = exchanges.drop_duplicates("flow").set_index("flow")
    nodes = {}
    for code in sorted(unmapped_codes):
        name = str(vocab["name"].get(code, by_code["flow_name"].get(code, code)))
        cats = tuple(vocab["categories"].get(code, ()))
        nodes[(RESIDUAL_DB, code)] = {
            "name": name,
            "categories": cats,
            "unit": normalize_unit(by_code["unit"].get(code)),
            "type": "emission",
            "exchanges": [],
        }
    return nodes


# ----------------------------------------------------------------------------- inventory


def _uncertainty(row: pd.Series, factor: float) -> dict:
    """bw2data uncertainty fields, rescaled when the amount was multiplied by ``factor``."""
    utype = row["uncertainty_type"]
    if _is_null(utype):
        return {}
    utype = int(utype)
    out: dict = {"uncertainty type": utype}
    loc, scale = row["loc"], row["scale"]
    if not _is_null(loc):
        if utype == 2:  # lognormal: loc is ln(amount)
            out["loc"] = float(loc) + math.log(factor)
        else:
            out["loc"] = float(loc) * factor
    if not _is_null(scale):
        out["scale"] = float(scale) if utype == 2 else float(scale) * factor
    for field in ("minimum", "maximum"):
        if not _is_null(row[field]):
            out[field] = float(row[field]) * factor
    return out


def _exchange(row: pd.Series, bridge: Mapping[str, BridgeEntry]) -> dict:
    flow_type = row["flow_type"]
    factor = 1.0
    if flow_type == "production":
        key, etype, unit = (INVENTORY_DB, row["process_id"]), "production", row["unit"]
    elif flow_type == "technosphere":
        key, etype, unit = (INVENTORY_DB, row["flow"]), "technosphere", row["unit"]
    else:
        entry = bridge.get(row["flow"])
        if entry is None:
            key, etype, unit = (RESIDUAL_DB, row["flow"]), "biosphere", row["unit"]
        else:
            key, etype, unit = (BIOSPHERE_DB, entry.target_code), "biosphere", entry.target_unit
            factor = entry.conversion_factor
    return {
        "input": key,
        "type": etype,
        "amount": float(row["amount"]) * factor,
        "unit": normalize_unit(unit),
        "name": str(row["flow_name"]),
        **_uncertainty(row, factor),
    }


def build_inventory(inventory: Inventory, bridge: Mapping[str, BridgeEntry]) -> dict[Key, dict]:
    grouped = {pid: df for pid, df in inventory.exchanges.groupby("process_id", sort=False)}
    nodes = {}
    for p in inventory.processes.itertuples(index=False):
        rows = grouped.get(p.process_id)
        exchanges = [] if rows is None else [_exchange(r, bridge) for _, r in rows.iterrows()]
        node = {
            "name": str(p.name),
            "reference product": str(p.reference_product),
            "unit": normalize_unit(p.reference_unit),
            "location": str(p.location),
            "type": "process",
            "production amount": float(p.reference_amount),
            "exchanges": exchanges,
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
    inventory: Inventory,
    bridge: Mapping[str, BridgeEntry],
    bafu_flows: pd.DataFrame,
    unmapped: set[str],
    n_methods: int,
) -> Coverage:
    bio = inventory.exchanges[inventory.exchanges["flow_type"] == "biosphere"]
    used = set(bio["flow"])
    mapped_rows = int(bio["flow"].isin(bridge.keys()).sum())
    compartments = dict(
        zip(bafu_flows["code"], (c[0] if c else "unknown" for c in bafu_flows["categories"]))
    )
    counter = Counter(compartments.get(code, "unknown") for code in unmapped)
    return Coverage(
        flows_used=len(used),
        flows_mapped=len(used & set(bridge.keys())),
        flows_nomenclature=sum(1 for code in used if code in bridge and bridge[code].nomenclature),
        exchange_rows=len(bio),
        exchange_rows_mapped=mapped_rows,
        residual_by_compartment=tuple(sorted(counter.items())),
        processes=len(inventory.processes),
        methods=n_methods,
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
    return BuildResult(
        biosphere=build_biosphere(ef_flows, bridge, methods),
        residual=build_residual(unmapped, bafu_flows, inventory.exchanges),
        inventory=build_inventory(inventory, bridge),
        methods=_bind_methods(methods),
        coverage=_coverage(inventory, bridge, bafu_flows, unmapped, len(methods)),
    )
