"""Flat parquet registry with integer ``bw_id`` columns, the file-mode twin of the bw2data DBs."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping

import pandas as pd

from .build import BuildResult, Key

CATEGORY_SEP = "::"
KEY_SEP = "|"

EXCHANGE_COLUMNS = (
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
)
_UNCERTAINTY_FIELDS = {
    "uncertainty_type": "uncertainty type",
    "loc": "loc",
    "scale": "scale",
    "minimum": "minimum",
    "maximum": "maximum",
}


@dataclass(frozen=True)
class Registry:
    processes: pd.DataFrame
    biosphere: pd.DataFrame
    exchanges: pd.DataFrame
    methods: pd.DataFrame
    characterization_factors: pd.DataFrame

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in fields(self))


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
    return pd.DataFrame(rows).sort_values("bw_id").reset_index(drop=True)


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
    return pd.DataFrame(rows).sort_values("bw_id").reset_index(drop=True)


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
    frame = pd.DataFrame(rows, columns=list(EXCHANGE_COLUMNS))
    frame["negative"] = frame["negative"].astype("boolean")
    return frame


def _method_rows(result: BuildResult) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "method_id": m.method_id,
                "method_key": KEY_SEP.join(m.key),
                "unit": m.unit,
                "description": m.description,
            }
            for m in result.methods
        ]
    )


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
    return pd.DataFrame(
        rows, columns=["method_id", "flow_bw_id", "flow_database", "flow_code", "factor"]
    )


def build_registry(result: BuildResult) -> Registry:
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
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for table in registry.table_names:
        getattr(registry, table).to_parquet(folder / _filename(table), index=False)
    return folder


def load_registry(folder: Path) -> Registry:
    folder = Path(folder)
    frames = {}
    for table in (f.name for f in fields(Registry)):
        path = folder / _filename(table)
        if not path.is_file():
            raise FileNotFoundError(f"registry table missing: {path}")
        frames[table] = pd.read_parquet(path)
    return Registry(**frames)
