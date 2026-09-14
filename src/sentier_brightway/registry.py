"""Flat parquet registry with integer ``bw_id`` columns, the file-mode twin of the bw2data DBs.

Downstream (``datapackage.py``) conventions baked into these frames:

- A production exchange is identified by ``type == "production"``, never by
  ``input_bw_id == process_bw_id``: the real BAFU-2026 inventory has 78 technosphere
  self-loops (a process consuming its own reference product as an input), so that
  equality does not distinguish production from technosphere rows.
- ``negative`` is a nullable boolean; ``pd.NA`` means "not flagged", i.e. false.
- ``uncertainty_type`` is a nullable ``Int64``; ``pd.NA`` means undefined (bw2data's
  ``uncertainty type`` code 0), not "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from ._frames import require_columns
from .build import BuildResult, Key

CATEGORY_SEP = "::"
KEY_SEP = "|"

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "processes": (
        "bw_id",
        "database",
        "code",
        "name",
        "reference_product",
        "unit",
        "location",
        "production_amount",
    ),
    "biosphere": ("bw_id", "database", "code", "name", "categories", "unit", "type"),
    "exchanges": (
        "process_bw_id",
        "input_bw_id",
        "input_database",
        "input_code",
        "type",
        "amount",
        "unit",
        "uncertainty_type",
        "loc",
        "scale",
        "minimum",
        "maximum",
        "negative",
    ),
    "methods": ("method_id", "method_key", "unit", "description"),
    "characterization_factors": (
        "method_id",
        "flow_bw_id",
        "flow_database",
        "flow_code",
        "factor",
    ),
}
TABLE_NAMES = tuple(TABLE_COLUMNS)

_UNCERTAINTY_FIELDS = {
    "uncertainty_type": "uncertainty type",
    "loc": "loc",
    "scale": "scale",
    "minimum": "minimum",
    "maximum": "maximum",
}
_FLOAT_EXCHANGE_COLUMNS = ("amount", "loc", "scale", "minimum", "maximum")


@dataclass(frozen=True)
class Registry:
    processes: pd.DataFrame
    biosphere: pd.DataFrame
    exchanges: pd.DataFrame
    methods: pd.DataFrame
    characterization_factors: pd.DataFrame


def _assign_ids(result: BuildResult) -> Mapping[Key, int]:
    """Processes first (sorted), then biosphere then residual nodes; ids start at 1."""
    ordered = sorted(result.inventory) + sorted(result.biosphere) + sorted(result.residual)
    return {key: i for i, key in enumerate(ordered, start=1)}


def _process_rows(result: BuildResult, ids: Mapping[Key, int]) -> pd.DataFrame:
    rows = [
        {
            "bw_id": ids[key],
            "database": key[0],
            "code": key[1],
            "name": node["name"],
            "reference_product": node["reference product"],
            "unit": node["unit"],
            "location": node["location"],
            "production_amount": node["production amount"],
        }
        for key, node in result.inventory.items()
    ]
    frame = pd.DataFrame(rows, columns=list(TABLE_COLUMNS["processes"]))
    return frame.sort_values("bw_id").reset_index(drop=True)


def _biosphere_rows(result: BuildResult, ids: Mapping[Key, int]) -> pd.DataFrame:
    rows = [
        {
            "bw_id": ids[key],
            "database": key[0],
            "code": key[1],
            "name": node["name"],
            "categories": CATEGORY_SEP.join(node["categories"]),
            "unit": node["unit"],
            "type": node["type"],
        }
        for table in (result.biosphere, result.residual)
        for key, node in table.items()
    ]
    frame = pd.DataFrame(rows, columns=list(TABLE_COLUMNS["biosphere"]))
    return frame.sort_values("bw_id").reset_index(drop=True)


def _exchange_rows(result: BuildResult, ids: Mapping[Key, int]) -> pd.DataFrame:
    rows = []
    for key, node in result.inventory.items():
        for ex in node["exchanges"]:
            row = {
                "process_bw_id": ids[key],
                "input_bw_id": ids[ex["input"]],
                "input_database": ex["input"][0],
                "input_code": ex["input"][1],
                "type": ex["type"],
                "amount": ex["amount"],
                "unit": ex["unit"],
            }
            row.update({col: ex.get(field) for col, field in _UNCERTAINTY_FIELDS.items()})
            row["negative"] = ex.get("negative")
            rows.append(row)
    frame = pd.DataFrame(rows, columns=list(TABLE_COLUMNS["exchanges"]))
    # Fixed dtypes regardless of which rows happen to carry uncertainty data or not: bw2calc
    # and bw_processing (Task 16) need numeric columns even when every value is null.
    for col in _FLOAT_EXCHANGE_COLUMNS:
        frame[col] = frame[col].astype("float64")
    frame["uncertainty_type"] = frame["uncertainty_type"].astype("Int64")
    frame["negative"] = frame["negative"].astype("boolean")
    return frame


def _method_rows(result: BuildResult) -> pd.DataFrame:
    rows = [
        {
            "method_id": m.method_id,
            "method_key": KEY_SEP.join(m.key),
            "unit": m.unit,
            "description": m.description,
        }
        for m in result.methods
    ]
    return pd.DataFrame(rows, columns=list(TABLE_COLUMNS["methods"]))


def _cf_rows(result: BuildResult, ids: Mapping[Key, int]) -> pd.DataFrame:
    rows = [
        {
            "method_id": m.method_id,
            "flow_bw_id": ids[key],
            "flow_database": key[0],
            "flow_code": key[1],
            "factor": value,
        }
        for m in result.methods
        for key, value in m.cfs
    ]
    return pd.DataFrame(rows, columns=list(TABLE_COLUMNS["characterization_factors"]))


def build_registry(result: BuildResult) -> Registry:
    """Assign contiguous integer ``bw_id`` values (processes first, then biosphere nodes) and
    flatten ``result`` into the five ``Registry`` frames, ``TABLE_COLUMNS`` order and dtypes."""
    ids = _assign_ids(result)
    return Registry(
        processes=_process_rows(result, ids),
        biosphere=_biosphere_rows(result, ids),
        exchanges=_exchange_rows(result, ids),
        methods=_method_rows(result),
        characterization_factors=_cf_rows(result, ids),
    )


def _filename(table: str) -> str:
    return table.replace("_", "-") + ".parquet"


def write_registry(registry: Registry, folder: Path) -> Path:
    """Write each ``Registry`` frame as its own parquet file under ``folder``."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for table in TABLE_NAMES:
        getattr(registry, table).to_parquet(folder / _filename(table), index=False)
    return folder


def load_registry(folder: Path) -> Registry:
    """Read back a folder written by ``write_registry``.

    Raises ``FileNotFoundError`` for a missing table and ``ValueError`` (naming the file and
    the missing columns) for a table that is present but does not match ``TABLE_COLUMNS`` --
    guards against a stale or hand-edited registry folder being fed into ``datapackage.py``."""
    folder = Path(folder)
    frames = {}
    for table in TABLE_NAMES:
        path = folder / _filename(table)
        if not path.is_file():
            raise FileNotFoundError(f"registry table missing: {path}")
        df = pd.read_parquet(path)
        require_columns(df, frozenset(TABLE_COLUMNS[table]), path)
        frames[table] = df
    return Registry(**frames)
