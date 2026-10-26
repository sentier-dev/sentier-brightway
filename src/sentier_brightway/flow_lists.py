"""BAFU-2026 flows as they land in Brightway, as flat tables for method developers.

Written for the FOODTURE / ADEME request (2026-10-09, "Liste Flux BAFU-Brightway"): one
xlsx with a README, one row per BAFU elementary flow used by the inventory with the EF 3.1
flow it is relinked to (bridge package, factor coverage, Brightway database and code), the
distinct EF 3.1 flows reached, and the process list. Everything is read from a ``data_root``
shaped like the ``~/dds`` checkout through the package's own readers; ``coverage.json`` in
sentier-mappings is the authoritative per-flow sidecar (status, package, tier, reasons) and
the bridge packages supply the EF target. The two are cross-checked and any disagreement
raises ``ValueError`` rather than producing a silently wrong table.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Mapping

import pandas as pd

from ._frames import data_root_error
from .bridge import BridgeEntry, load_bridge
from .constants import (
    BIOSPHERE_DB,
    BRIDGE_FOLDER,
    DEFAULT_SOURCE,
    REPO_MAPPINGS,
    inventory_db,
    residual_db,
)
from .flow_lists_output import (  # noqa: F401  (re-exported for callers and tests)
    SHEETS,
    ExportResult,
    RepoPin,
    headline_numbers,
    readme_markdown,
    readme_rows,
    repo_pins,
    write_outputs,
)
from .flows import load_ef_flows, load_source_flows
from .inventory import Inventory, load_inventory
from .methods import MethodSpec, load_methods

COVERAGE_FILE = "coverage.json"
STATUSES = frozenset({"mapped", "unmapped"})
_PACKAGE_PREFIX = re.compile(r"^biosphere-\d+-")

COVERAGE_COLUMNS = (
    "bafu_code",
    "bafu_name",
    "bafu_unit",
    "bafu_compartment",
    "bafu_sub_compartment",
    "status",
    "package",
    "tier",
    "placement",
    "reason",
    "detail",
    "caveats",
    "cas_conflict",
)


def _cell(value: object) -> str:
    """One coverage field as a spreadsheet cell: lists joined, dicts as JSON, None empty."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _coverage_path(data_root: Path) -> Path:
    return Path(data_root) / REPO_MAPPINGS / "data" / BRIDGE_FOLDER / COVERAGE_FILE


def load_coverage(data_root: Path) -> pd.DataFrame:
    """``coverage.json`` flattened to one row per BAFU flow, columns ``COVERAGE_COLUMNS``."""
    path = _coverage_path(data_root)
    if not path.is_file():
        raise data_root_error(COVERAGE_FILE, path)
    rows = json.loads(path.read_text()).get("coverage")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a 'coverage' list")
    out = []
    for i, row in enumerate(rows):
        source = row.get("source") or {}
        code = source.get("code")
        if not code:
            raise ValueError(f"{path} row {i}: missing source.code")
        status = row.get("status")
        if status not in STATUSES:
            raise ValueError(f"{path} row {i} ({code}): unknown status {status!r}")
        context = list(source.get("context") or [])
        out.append(
            {
                "bafu_code": code,
                "bafu_name": _cell(source.get("name")),
                "bafu_unit": _cell(source.get("unit")),
                "bafu_compartment": context[0] if context else "",
                "bafu_sub_compartment": context[1] if len(context) > 1 else "",
                "status": status,
                "package": _PACKAGE_PREFIX.sub("", _cell(row.get("package"))),
                "tier": _cell(row.get("tier")),
                "placement": _cell(row.get("placement")),
                "reason": _cell(row.get("reason")),
                "detail": _cell(row.get("detail")),
                "caveats": _cell(row.get("caveats")),
                "cas_conflict": _cell(row.get("cas_conflict")),
            }
        )
    return pd.DataFrame(out, columns=list(COVERAGE_COLUMNS))


# ------------------------------------------------------------------ EF side lookups


def ef_flow_table(ef_flows: pd.DataFrame, methods: tuple[MethodSpec, ...]) -> pd.DataFrame:
    """Every EF 3.1 flow the Brightway biosphere can hold: columns ``code, name, context, cas``.

    Same precedence as ``build.build_biosphere``: the vocab names a flow first, a method's
    CF table names flows the vocab lacks, and the CF context (three levels) beats the vocab
    compartment because it is more specific."""
    names: dict[str, str] = dict(zip(ef_flows["code"], ef_flows["name"]))
    cas: dict[str, str] = {c: (v or "") for c, v in zip(ef_flows["code"], ef_flows["cas_number"])}
    context: dict[str, str] = {
        c: " / ".join(cats) for c, cats in zip(ef_flows["code"], ef_flows["categories"])
    }
    cf_context: dict[str, str] = {}
    for spec in methods:
        for code, name in spec.flow_name.items():
            names.setdefault(code, name)
        for code, ctx in spec.flow_context.items():
            if ctx:
                cf_context.setdefault(code, " / ".join(ctx))
    context.update(cf_context)
    codes = sorted(names)
    return pd.DataFrame(
        {
            "code": codes,
            "name": [names[c] for c in codes],
            "context": [context.get(c, "") for c in codes],
            "cas": [cas.get(c, "") for c in codes],
        }
    )


def methods_per_flow(methods: tuple[MethodSpec, ...]) -> dict[str, tuple[str, ...]]:
    """``{ef_flow_code: (method_id, ...)}`` over the global characterization factors."""
    out: dict[str, list[str]] = {}
    for spec in methods:
        for code, _factor in spec.cfs:
            ids = out.setdefault(code, [])
            if spec.method_id not in ids:
                ids.append(spec.method_id)
    return {code: tuple(ids) for code, ids in out.items()}


# ------------------------------------------------------------------ bafu_to_ef sheet

BAFU_TO_EF_COLUMNS = (
    "bafu_name",
    "bafu_code",
    "bafu_unit",
    "bafu_compartment",
    "bafu_sub_compartment",
    "bafu_cas",
    "exchange_count",
    "status",
    "package",
    "tier",
    "placement",
    "ef_uuid",
    "ef_name",
    "ef_context",
    "ef_unit",
    "ef_cas",
    "conversion_factor",
    "ef_methods_with_factor",
    "brightway_database",
    "brightway_code",
    "reason",
    "detail",
    "caveats",
    "cas_conflict",
)


def _first(codes) -> str:
    return ", ".join(sorted(codes)[:5])


def _check_coverage_against_inputs(
    coverage: pd.DataFrame,
    bridge: Mapping[str, BridgeEntry],
    ef_table: pd.DataFrame,
    exchanges: pd.DataFrame,
) -> None:
    """Every disagreement between the sidecar, the bridge and the inventory is an error."""
    dup = coverage["bafu_code"][coverage["bafu_code"].duplicated()]
    if not dup.empty:
        raise ValueError(f"coverage.json: duplicate bafu_code: {_first(dup)}")
    used = set(exchanges.loc[exchanges["flow_type"] == "biosphere", "flow"])
    covered = set(coverage["bafu_code"])
    if used != covered:
        raise ValueError(
            "coverage.json rows differ from the flows the inventory uses: "
            f"used but not covered: {_first(used - covered) or '-'}; "
            f"covered but not used: {_first(covered - used) or '-'}"
        )
    mapped = set(coverage.loc[coverage["status"] == "mapped", "bafu_code"])
    unmapped = covered - mapped
    missing = mapped - set(bridge)
    if missing:
        raise ValueError(f"coverage says mapped but no bridge entry: {_first(missing)}")
    stray = unmapped & set(bridge)
    if stray:
        raise ValueError(f"coverage says unmapped but the bridge maps it: {_first(stray)}")
    known = set(ef_table["code"])
    unknown = {bridge[c].target_code for c in mapped} - known
    if unknown:
        raise ValueError(f"bridge targets unknown to vocab and EF methods: {_first(unknown)}")


def build_bafu_to_ef(
    coverage: pd.DataFrame,
    bridge: Mapping[str, BridgeEntry],
    ef_table: pd.DataFrame,
    bafu_flows: pd.DataFrame,
    exchanges: pd.DataFrame,
    methods: tuple[MethodSpec, ...],
    source: str = DEFAULT_SOURCE,
) -> pd.DataFrame:
    """One row per BAFU flow the inventory uses, with the EF 3.1 flow it lands on."""
    _check_coverage_against_inputs(coverage, bridge, ef_table, exchanges)
    bio = exchanges[exchanges["flow_type"] == "biosphere"]
    counts = bio["flow"].value_counts()
    bafu_cas = {c: (v or "") for c, v in zip(bafu_flows["code"], bafu_flows["cas_number"])}
    ef = ef_table.set_index("code")
    per_flow = methods_per_flow(methods)
    rows = []
    for rec in coverage.to_dict("records"):
        code = rec["bafu_code"]
        row = dict(rec)
        row["bafu_cas"] = bafu_cas.get(code, "")
        row["exchange_count"] = int(counts.get(code, 0))
        if rec["status"] == "mapped":
            entry = bridge[code]
            target = ef.loc[entry.target_code]
            row.update(
                ef_uuid=entry.target_code,
                ef_name=target["name"],
                ef_context=target["context"],
                ef_unit=entry.target_unit,
                ef_cas=target["cas"],
                conversion_factor=entry.conversion_factor,
                ef_methods_with_factor=len(per_flow.get(entry.target_code, ())),
                brightway_database=BIOSPHERE_DB,
                brightway_code=entry.target_code,
            )
        else:
            row.update(
                ef_uuid="",
                ef_name="",
                ef_context="",
                ef_unit="",
                ef_cas="",
                conversion_factor=None,
                ef_methods_with_factor=0,
                brightway_database=residual_db(source),
                brightway_code=code,
            )
        rows.append(row)
    df = pd.DataFrame(rows, columns=list(BAFU_TO_EF_COLUMNS))
    return df.sort_values(
        ["bafu_compartment", "bafu_sub_compartment", "bafu_name"], kind="stable"
    ).reset_index(drop=True)


# ------------------------------------------------------------------ ef_flows, processes

EF_FLOWS_COLUMNS = (
    "ef_uuid",
    "ef_name",
    "ef_context",
    "ef_unit",
    "ef_cas",
    "bafu_source_count",
    "exchange_count",
    "ef_methods_with_factor",
    "ef_methods",
)

PROCESS_COLUMNS = (
    "name",
    "reference_product",
    "unit",
    "location",
    "sector",
    "process_type",
    "code",
    "brightway_database",
)


def build_ef_flows(
    bafu_to_ef: pd.DataFrame,
    bridge: Mapping[str, BridgeEntry],
    methods: tuple[MethodSpec, ...],
) -> pd.DataFrame:
    """The distinct EF 3.1 flows the mapped BAFU flows land on."""
    units: dict[str, str] = {}
    for entry in bridge.values():  # package order, first wins: same rule as build()
        units.setdefault(entry.target_code, entry.target_unit)
    per_flow = methods_per_flow(methods)
    mapped = bafu_to_ef[bafu_to_ef["status"] == "mapped"]
    grouped = mapped.groupby("ef_uuid", sort=False).agg(
        ef_name=("ef_name", "first"),
        ef_context=("ef_context", "first"),
        ef_cas=("ef_cas", "first"),
        bafu_source_count=("bafu_code", "size"),
        exchange_count=("exchange_count", "sum"),
    )
    grouped = grouped.reset_index()
    grouped["ef_unit"] = grouped["ef_uuid"].map(units)
    grouped["ef_methods"] = grouped["ef_uuid"].map(lambda c: "; ".join(per_flow.get(c, ())))
    grouped["ef_methods_with_factor"] = grouped["ef_uuid"].map(lambda c: len(per_flow.get(c, ())))
    df = grouped[list(EF_FLOWS_COLUMNS)]
    return df.sort_values(["ef_context", "ef_name"], kind="stable").reset_index(drop=True)


def build_processes(inventory: Inventory) -> pd.DataFrame:
    """The technosphere nomenclature: one row per process, as installed in Brightway."""
    p = inventory.processes
    dup = p["process_id"][p["process_id"].duplicated()]
    if not dup.empty:
        raise ValueError(f"processes: duplicate process_id: {_first(dup)}")
    df = pd.DataFrame(
        {
            "name": p["name"],
            "reference_product": p["reference_product"],
            "unit": p["reference_unit"],
            "location": p["location"],
            "sector": p["sector"] if "sector" in p.columns else "",
            "process_type": p["process_type"],
            "code": p["process_id"],
            "brightway_database": inventory_db(inventory.source),
        },
        columns=list(PROCESS_COLUMNS),
    )
    return df.sort_values(["sector", "name", "location"], kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------ entry point


def export(
    data_root: Path,
    out_dir: Path,
    today: date | None = None,
    overwrite: bool = False,
    source: str = DEFAULT_SOURCE,
) -> ExportResult:
    """Read the four data repos under ``data_root`` and write the workbook into ``out_dir``."""
    today = today or date.today()
    inventory = load_inventory(data_root, source=source)
    methods = load_methods(data_root)
    bridge = load_bridge(data_root)
    ef_table = ef_flow_table(load_ef_flows(data_root), methods)
    bafu_to_ef = build_bafu_to_ef(
        coverage=load_coverage(data_root),
        bridge=bridge,
        ef_table=ef_table,
        bafu_flows=load_source_flows(data_root, source),
        exchanges=inventory.exchanges,
        methods=methods,
        source=inventory.source,
    )
    ef_flows = build_ef_flows(bafu_to_ef, bridge, methods)
    processes = build_processes(inventory)
    frames = {"bafu_to_ef": bafu_to_ef, "ef_flows": ef_flows, "processes": processes}
    counts = {name: int(len(df)) for name, df in frames.items()}
    headline = headline_numbers(bafu_to_ef, ef_flows, processes)
    readme = readme_rows(repo_pins(data_root), counts, headline, today, inventory.source)
    stem = f"{BRIDGE_FOLDER}_flow-lists_{today.isoformat()}"
    xlsx = write_outputs(frames, readme, out_dir, stem, overwrite=overwrite)
    return ExportResult(xlsx=xlsx, counts=counts, headline=headline)
