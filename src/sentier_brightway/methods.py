"""Read EF 3.1 methods and their global characterization factors from sentier-methods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from ._frames import data_root_error, require_columns
from .constants import FLOW_IRI_PREFIX, METHOD_PREFIX, METHODS_FOLDER, REPO_METHODS

METHOD_COLUMNS = frozenset({"method_id", "method_name", "impact_category", "unit"})
CF_COLUMNS = frozenset(
    {"method_id", "flow", "flow_name", "factor_value", "flow_context", "location"}
)


@dataclass(frozen=True)
class MethodSpec:
    key: tuple[str, ...]
    method_id: str
    unit: str
    description: str
    cfs: tuple[tuple[str, float], ...]  # (ef_flow_code, factor)
    flow_context: Mapping[str, tuple[str, ...]]  # ef_flow_code -> context path
    flow_name: Mapping[str, str]  # ef_flow_code -> EF flow name


def _split_context(ctx: object) -> tuple[str, ...]:
    if pd.isna(ctx):
        return ()
    return tuple(part.strip() for part in str(ctx).split("/") if part.strip())


def load_methods(data_root: Path) -> tuple[MethodSpec, ...]:
    folder = Path(data_root) / REPO_METHODS / "data" / METHODS_FOLDER
    methods_path = folder / "methods.parquet"
    cfs_path = folder / "characterization-factors.parquet"
    if not folder.is_dir():
        raise data_root_error("methods folder", folder)
    if not methods_path.is_file():
        raise data_root_error("methods.parquet", methods_path)
    if not cfs_path.is_file():
        raise data_root_error("characterization-factors.parquet", cfs_path)

    methods = pd.read_parquet(methods_path)
    require_columns(methods, METHOD_COLUMNS, methods_path)
    cfs = pd.read_parquet(cfs_path)
    require_columns(cfs, CF_COLUMNS, cfs_path)

    global_cfs = cfs[cfs["location"].isna()].drop_duplicates(["method_id", "flow"])
    global_cfs = global_cfs.assign(
        code=global_cfs["flow"].astype(str).str.removeprefix(FLOW_IRI_PREFIX),
        factor_value=global_cfs["factor_value"].astype(float),
    )
    specs = []
    for m in methods.itertuples(index=False):
        rows = global_cfs[global_cfs["method_id"] == m.method_id]
        specs.append(
            MethodSpec(
                key=(*METHOD_PREFIX, str(m.impact_category)),
                method_id=str(m.method_id),
                unit=str(m.unit),
                description=f"{m.method_name} {m.impact_category}, delivered by sentier-methods",
                cfs=tuple((str(c), float(v)) for c, v in zip(rows["code"], rows["factor_value"])),
                flow_context=MappingProxyType(
                    dict(zip(rows["code"], (_split_context(c) for c in rows["flow_context"])))
                ),
                flow_name=MappingProxyType(dict(zip(rows["code"], rows["flow_name"].astype(str)))),
            )
        )
    return tuple(specs)
