"""Read sentier-inventory sector folders into two flat frames."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ._frames import data_root_error, require_columns
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


def _with_uncertainty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee the optional uncertainty columns exist, as float64 all-null when absent."""
    missing = [c for c in UNCERTAINTY_COLUMNS if c not in df.columns]
    if not missing:
        return df
    extra = {c: pd.Series(float("nan"), index=df.index, dtype="float64") for c in missing}
    return df.assign(**extra)


def load_inventory(data_root: Path) -> Inventory:
    """Concatenate every ``data/<NN>-<sector>/`` folder of sentier-inventory.

    Sectors such as ``99-obsolete`` are intentionally included: their processes are
    still link targets for exchanges recorded in other sectors.
    """
    base = Path(data_root) / REPO_INVENTORY / "data"
    sectors = sorted(p for p in base.glob("*-*") if (p / "processes.parquet").is_file())
    if not sectors:
        raise data_root_error("sector folders with processes.parquet", base)
    processes, exchanges = [], []
    for sector in sectors:
        p = pd.read_parquet(sector / "processes.parquet")
        require_columns(p, PROCESS_COLUMNS, sector / "processes.parquet")
        exchanges_path = sector / "exchanges.parquet"
        if not exchanges_path.is_file():
            raise FileNotFoundError(f"{sector} has processes.parquet but no exchanges.parquet")
        e = pd.read_parquet(exchanges_path)
        require_columns(e, EXCHANGE_COLUMNS, exchanges_path)
        processes.append(p)
        exchanges.append(_with_uncertainty_columns(e))
    return Inventory(
        processes=pd.concat(processes, ignore_index=True),
        exchanges=pd.concat(exchanges, ignore_index=True),
    )
