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
from pathlib import Path

import pandas as pd

from ._frames import data_root_error
from .constants import BRIDGE_FOLDER, REPO_MAPPINGS
from .methods import MethodSpec

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
