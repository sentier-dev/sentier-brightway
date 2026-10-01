"""Read the sector folders of sentier-inventory for one ``source`` into two flat frames."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ._frames import data_root_error, require_columns
from .constants import DEFAULT_SOURCE, REPO_INVENTORY

PROCESS_COLUMNS = frozenset(
    {
        "process_id",
        "name",
        "reference_product",
        "reference_unit",
        "reference_amount",
        "location",
        "process_type",
        "source",
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
    source: str = DEFAULT_SOURCE
    source_version: str | None = None
    sectors: tuple[str, ...] = ()  # folders actually read, in rank order


def _with_uncertainty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee the optional uncertainty columns exist, as float64 all-null when absent."""
    missing = [c for c in UNCERTAINTY_COLUMNS if c not in df.columns]
    if not missing:
        return df
    extra = {c: pd.Series(float("nan"), index=df.index, dtype="float64") for c in missing}
    return df.assign(**extra)


def _declared_sources(sector: Path) -> list[str]:
    """The ``sources`` list of a sector's ``metadata.json``; 0.1.0 metadata is an error."""
    meta_path = sector / "metadata.json"
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"{sector} has no metadata.json; cannot tell which sources it holds"
        )
    meta = json.loads(meta_path.read_text())
    sources = meta.get("sources")
    if not isinstance(sources, list):
        raise ValueError(
            f"{meta_path} has no 'sources' list (sentier-inventory schema < 0.2.0); "
            "refusing to read the folder blind"
        )
    return sources


def _select_sectors(base: Path, source: str) -> list[Path]:
    """Pass one: folders whose metadata lists ``source``; their parquet is not opened."""
    sectors = sorted(p for p in base.glob("*-*") if (p / "processes.parquet").is_file())
    if not sectors:
        raise data_root_error("sector folders with processes.parquet", base)
    available: set[str] = set()
    selected = []
    for sector in sectors:
        declared = _declared_sources(sector)
        available.update(declared)
        if source in declared:
            selected.append(sector)
    if not selected:
        raise ValueError(
            f"no sector folder lists source={source!r} under {base}; "
            f"available: {sorted(available)}"
        )
    return selected


def _read_sector(sector: Path, source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pass two: the rows of ``source`` in one folder (predicate pushdown on ``source``)."""
    processes_path = sector / "processes.parquet"
    # check the contract on the file schema before filtering: a missing ``source`` column
    # must surface as our column error, not as a pyarrow filter failure
    require_columns(
        pq.read_schema(processes_path).empty_table().to_pandas(), PROCESS_COLUMNS, processes_path
    )
    p = pd.read_parquet(processes_path, filters=[("source", "==", source)])
    exchanges_path = sector / "exchanges.parquet"
    if not exchanges_path.is_file():
        raise FileNotFoundError(f"{sector} has processes.parquet but no exchanges.parquet")
    e = pd.read_parquet(exchanges_path)
    require_columns(e, EXCHANGE_COLUMNS, exchanges_path)
    e = e[e["process_id"].isin(p["process_id"])]
    return p, _with_uncertainty_columns(e)


def _version(processes: pd.DataFrame) -> str | None:
    """Distinct ``source_version`` values, comma-joined; None when the column is absent/null."""
    if "source_version" not in processes.columns:
        return None
    values = sorted(set(processes["source_version"].dropna().astype(str)))
    return ",".join(values) if values else None


def load_inventory(data_root: Path, source: str = DEFAULT_SOURCE) -> Inventory:
    """Rows of one inventory ``source`` across every sector folder that holds it.

    Folder selection reads only ``metadata.json`` (its ``sources`` list is CI-checked
    against the parquet in sentier-inventory), so folders delivered by other sources are
    never opened. Inside a selected folder only the rows with ``processes.source ==
    source`` are materialised, and exchanges follow their process. ``99-obsolete`` is
    read like any other folder whenever it lists the source: its processes are link
    targets for exchanges recorded in other sectors.
    """
    base = Path(data_root) / REPO_INVENTORY / "data"
    selected = _select_sectors(base, source)
    processes, exchanges = [], []
    for sector in selected:
        p, e = _read_sector(sector, source)
        processes.append(p)
        exchanges.append(e)
    all_processes = pd.concat(processes, ignore_index=True)
    return Inventory(
        processes=all_processes,
        exchanges=pd.concat(exchanges, ignore_index=True),
        source=source,
        source_version=_version(all_processes),
        sectors=tuple(s.name for s in selected),
    )
