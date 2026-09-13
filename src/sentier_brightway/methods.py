"""Read EF 3.1 methods and their global characterization factors from sentier-methods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from ._frames import codes_from_iris, data_root_error, require_columns
from .constants import METHOD_PREFIX, METHODS_FOLDER, REPO_METHODS

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
    # ef_flow_code -> EF flow name, as recorded by sentier-methods for this method; the
    # same flow may carry a slightly different name in another method's rows, and a
    # consumer combining specs should let the first one win, with the vocab's own
    # pref_label taking priority over either.
    flow_name: Mapping[str, str]


def _split_context(ctx: str | None) -> tuple[str, ...]:
    if pd.isna(ctx):
        return ()
    return tuple(part.strip() for part in str(ctx).split("/") if part.strip())


def _check_no_duplicate_global_cfs(global_cfs: pd.DataFrame, path: Path) -> None:
    dup_mask = global_cfs.duplicated(subset=["method_id", "flow"], keep=False)
    if dup_mask.any():
        pairs = list(
            global_cfs.loc[dup_mask, ["method_id", "flow"]]
            .drop_duplicates()
            .itertuples(index=False, name=None)
        )
        raise ValueError(
            f"{path}: duplicate (method_id, flow) pairs among global characterization "
            f"factors: {pairs[:5]}"
        )


def _check_no_duplicate_impact_category(methods: pd.DataFrame, path: Path) -> None:
    dups = sorted(set(methods["impact_category"][methods["impact_category"].duplicated()]))
    if dups:
        raise ValueError(f"{path}: duplicate impact_category values (used as the key): {dups[:5]}")


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
    _check_no_duplicate_impact_category(methods, methods_path)

    cfs = pd.read_parquet(cfs_path)
    require_columns(cfs, CF_COLUMNS, cfs_path)

    global_cfs = cfs[cfs["location"].isna()]
    _check_no_duplicate_global_cfs(global_cfs, cfs_path)

    ctx_map = {c: _split_context(c) for c in global_cfs["flow_context"].unique()}
    global_cfs = global_cfs.assign(
        code=codes_from_iris(global_cfs["flow"].astype(str), cfs_path),
        factor_value=global_cfs["factor_value"].astype(float),
        flow_name=global_cfs["flow_name"].astype(str),
        context=global_cfs["flow_context"].map(ctx_map),
    )

    specs = []
    for m in methods.itertuples(index=False):
        rows = global_cfs[global_cfs["method_id"] == m.method_id]
        if rows.empty:
            raise ValueError(
                f"{cfs_path}: method {m.method_id!r} has no global characterization factors"
            )
        specs.append(
            MethodSpec(
                key=(*METHOD_PREFIX, str(m.impact_category)),
                method_id=str(m.method_id),
                unit=str(m.unit),
                description=f"{m.method_name} {m.impact_category}, delivered by sentier-methods",
                cfs=tuple((str(c), float(v)) for c, v in zip(rows["code"], rows["factor_value"])),
                flow_context=MappingProxyType(dict(zip(rows["code"], rows["context"]))),
                flow_name=MappingProxyType(dict(zip(rows["code"], rows["flow_name"]))),
            )
        )
    return tuple(specs)
