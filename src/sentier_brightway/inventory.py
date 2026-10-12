"""Read one source folder of sentier-inventory (``data/<source>-<version>/``) into two frames."""

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
        "sector",
        "source",
        "source_version",
    }
)
EXCHANGE_COLUMNS = frozenset(
    {"process_id", "flow", "flow_name", "flow_type", "direction", "amount", "unit"}
)
UNCERTAINTY_COLUMNS = ("uncertainty_type", "loc", "scale", "minimum", "maximum")
METADATA_SCHEMA = "0.3.0"  # first sentier-inventory schema with one source per folder


@dataclass(frozen=True)
class Inventory:
    processes: pd.DataFrame  # keeps the ``sector`` column so callers can filter on it
    exchanges: pd.DataFrame
    source: str = DEFAULT_SOURCE
    source_version: str | None = None  # ``metadata.source_version`` of the folder read
    sectors: tuple[str, ...] = ()  # ``metadata.sectors`` of the folder read, sorted


@dataclass(frozen=True)
class SourceFolder:
    """One ``data/<source>-<source_version>/`` folder as its ``metadata.json`` describes it."""

    path: Path
    source: str
    source_version: str
    sectors: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.source}/{self.source_version} ({self.path.name})"


def _with_uncertainty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee the optional uncertainty columns exist, as float64 all-null when absent."""
    missing = [c for c in UNCERTAINTY_COLUMNS if c not in df.columns]
    if not missing:
        return df
    extra = {c: pd.Series(float("nan"), index=df.index, dtype="float64") for c in missing}
    return df.assign(**extra)


def _read_metadata(folder: Path) -> SourceFolder:
    """The folder's ``metadata.json`` as a ``SourceFolder``; pre-0.3.0 metadata is an error."""
    meta_path = folder / "metadata.json"
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"{folder} has no metadata.json; cannot tell which source it holds"
        )
    meta = json.loads(meta_path.read_text())
    source, version, sectors = meta.get("source"), meta.get("source_version"), meta.get("sectors")
    if not isinstance(source, str) or not isinstance(version, str):
        raise ValueError(
            f"{meta_path} has no 'source' / 'source_version' keys (sentier-inventory schema "
            f"< {METADATA_SCHEMA}, one folder per source); refusing to read the folder blind"
        )
    if not isinstance(sectors, list) or not all(isinstance(s, str) for s in sectors):
        raise ValueError(f"{meta_path} has no 'sectors' list (sentier-inventory schema >= 0.3.0)")
    return SourceFolder(folder, source, version, tuple(sorted(sectors)))


def scan_source_folders(base: Path) -> list[SourceFolder]:
    """Every ``data/*/`` folder with a ``processes.parquet``, described by its metadata only."""
    folders = sorted(p.parent for p in base.glob("*/processes.parquet"))
    if not folders:
        raise data_root_error("source folders with processes.parquet", base)
    return [_read_metadata(folder) for folder in folders]


def _select_folder(base: Path, source: str, source_version: str | None) -> SourceFolder:
    """Pass one: the folder whose metadata declares ``source`` (and the version when given)."""
    folders = scan_source_folders(base)
    matches = [
        f
        for f in folders
        if f.source == source and (source_version is None or f.source_version == source_version)
    ]
    if not matches:
        wanted = f"source={source!r}"
        if source_version is not None:
            wanted += f", source_version={source_version!r}"
        raise ValueError(
            f"no source folder with {wanted} under {base}; available: "
            + ", ".join(f.label for f in folders)
        )
    if len(matches) > 1:
        raise ValueError(
            f"several folders hold source={source!r} under {base}: "
            + ", ".join(f.label for f in matches)
            + "; pass source_version to pick one"
        )
    return matches[0]


def _read_folder(folder: SourceFolder) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pass two: the folder's rows; the ``source`` predicate pushdown is a consistency guard.

    The folder holds exactly one source by contract (CI-checked in sentier-inventory), so the
    filter changes nothing on valid data and drops rows that contradict the metadata."""
    processes_path = folder.path / "processes.parquet"
    # check the contract on the file schema before filtering: a missing ``source`` column
    # must surface as our column error, not as a pyarrow filter failure
    require_columns(
        pq.read_schema(processes_path).empty_table().to_pandas(), PROCESS_COLUMNS, processes_path
    )
    p = pd.read_parquet(processes_path, filters=[("source", "==", folder.source)])
    exchanges_path = folder.path / "exchanges.parquet"
    if not exchanges_path.is_file():
        raise FileNotFoundError(f"{folder.path} has processes.parquet but no exchanges.parquet")
    e = pd.read_parquet(exchanges_path)
    require_columns(e, EXCHANGE_COLUMNS, exchanges_path)
    e = e[e["process_id"].isin(p["process_id"])]
    return p, _with_uncertainty_columns(e)


def load_inventory(
    data_root: Path, source: str = DEFAULT_SOURCE, source_version: str | None = None
) -> Inventory:
    """The processes and exchanges of one inventory ``source`` release.

    sentier-inventory keeps one folder per published release, ``data/<source>-<version>/``,
    with ``sector`` as a column on the processes. Folder selection reads only each folder's
    ``metadata.json`` (``source``, ``source_version``, ``sectors``), so other sources' parquet
    is never opened. Without ``source_version`` the source must be present exactly once; with
    it, that release is read. The ``sector`` column stays on the returned frame.
    """
    base = Path(data_root) / REPO_INVENTORY / "data"
    folder = _select_folder(base, source, source_version)
    processes, exchanges = _read_folder(folder)
    return Inventory(
        processes=processes,
        exchanges=exchanges,
        source=folder.source,
        source_version=folder.source_version,
        sectors=folder.sectors,
    )
