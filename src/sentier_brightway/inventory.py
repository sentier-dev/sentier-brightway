"""Read sentier-inventory sector folders into two flat frames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .constants import REPO_INVENTORY

PROCESS_COLUMNS = frozenset(
    {
        "process_id",
        "name",
        "reference_product",
        "reference_unit",
        "reference_amount",
        "location",
        "process_type",
    }
)
EXCHANGE_COLUMNS = frozenset(
    {"process_id", "flow", "flow_name", "flow_type", "direction", "amount", "unit"}
)
UNCERTAINTY_COLUMNS = ("uncertainty_type", "loc", "scale", "minimum", "maximum")


@dataclass(frozen=True)
class Inventory:
    processes: pd.DataFrame
    exchanges: pd.DataFrame


def _require(df: pd.DataFrame, required: frozenset[str], path: Path) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns {missing}")


def _with_uncertainty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee the optional uncertainty columns exist (all-null when absent)."""
    extra = {c: None for c in UNCERTAINTY_COLUMNS if c not in df.columns}
    return df.assign(**extra) if extra else df


def load_inventory(data_root: Path) -> Inventory:
    """Concatenate every ``data/<NN>-<sector>/`` folder of sentier-inventory."""
    base = Path(data_root) / REPO_INVENTORY / "data"
    sectors = sorted(p for p in base.glob("*-*") if (p / "processes.parquet").is_file())
    if not sectors:
        raise FileNotFoundError(f"no sector folders with processes.parquet under {base}")
    processes, exchanges = [], []
    for sector in sectors:
        p = pd.read_parquet(sector / "processes.parquet")
        _require(p, PROCESS_COLUMNS, sector / "processes.parquet")
        e = pd.read_parquet(sector / "exchanges.parquet")
        _require(e, EXCHANGE_COLUMNS, sector / "exchanges.parquet")
        processes.append(p)
        exchanges.append(_with_uncertainty_columns(e))
    return Inventory(
        processes=pd.concat(processes, ignore_index=True),
        exchanges=pd.concat(exchanges, ignore_index=True),
    )
