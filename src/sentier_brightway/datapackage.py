"""bw_processing datapackages from the ``Registry``, plus a bw2data-free scoring helper.

Layout under the ``bw_package`` folder::

    bw_package/bafu-2026/                 technosphere + biosphere vectors (one datapackage)
    bw_package/methods/<method_slug>/     one characterization datapackage per method

Semantics follow bw2calc: technosphere *inputs* carry ``flip=True`` (bw2calc negates them
when building the matrix); production, biosphere and characterization rows are not flipped
(no flip vector is written for those); characterization rows sit on the diagonal
``(flow_bw_id, flow_bw_id)``.

v0.1 exports static vectors only: the registry's ``uncertainty_type``/``loc``/``scale``/
``minimum``/``maximum``/``negative`` columns are NOT written, so Monte Carlo runs on these
datapackages see fixed amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import bw_processing as bwp
import numpy as np
import pandas as pd

from .constants import INVENTORY_DB
from .registry import Registry, load_registry

INVENTORY_DIR = INVENTORY_DB
METHODS_DIR = "methods"
REGISTRY_DIR = "registry"
PACKAGE_DIR = "bw_package"
TECHNOSPHERE_TYPES = ("production", "technosphere")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class DatapackagePaths:
    inventory: Path
    methods: Mapping[str, Path]  # method_id -> folder


def method_slug(method_id: str) -> str:
    """``ef-3.1:climate-change`` -> ``ef-3.1__climate-change``; anything else outside
    ``[A-Za-z0-9._-]`` becomes ``_`` so the slug is a safe folder name."""
    return _UNSAFE.sub("_", method_id.replace(":", "__"))


def _indices(rows: pd.Series, cols: pd.Series) -> np.ndarray:
    arr = np.empty(len(rows), dtype=bwp.INDICES_DTYPE)
    arr["row"] = rows.to_numpy(dtype="int64")
    arr["col"] = cols.to_numpy(dtype="int64")
    return arr


def _new_datapackage(folder: Path, name: str):
    folder.mkdir(parents=True, exist_ok=True)
    return bwp.create_datapackage(
        fs=bwp.generic_directory_filesystem(dirpath=folder), name=name, id_=name
    )


def _check_exchange_ids(registry: Registry) -> None:
    known = set(registry.processes["bw_id"]) | set(registry.biosphere["bw_id"])
    ex = registry.exchanges
    for column in ("input_bw_id", "process_bw_id"):
        dangling = sorted(set(ex[column]) - known)
        if dangling:
            raise ValueError(f"exchanges.{column} not in registry nodes: {dangling[:10]}")


def _write_inventory(registry: Registry, folder: Path) -> None:
    dp = _new_datapackage(folder, INVENTORY_DB)
    ex = registry.exchanges
    techno = ex[ex["type"].isin(TECHNOSPHERE_TYPES)]
    dp.add_persistent_vector(
        matrix="technosphere_matrix",
        name=f"{INVENTORY_DB}-technosphere",
        indices_array=_indices(techno["input_bw_id"], techno["process_bw_id"]),
        data_array=techno["amount"].to_numpy(dtype="float64"),
        flip_array=(techno["type"] == "technosphere").to_numpy(dtype=bool),
    )
    bio = ex[ex["type"] == "biosphere"]
    dp.add_persistent_vector(
        matrix="biosphere_matrix",
        name=f"{INVENTORY_DB}-biosphere",
        indices_array=_indices(bio["input_bw_id"], bio["process_bw_id"]),
        data_array=bio["amount"].to_numpy(dtype="float64"),
    )
    dp.finalize_serialization()


def _write_method(rows: pd.DataFrame, method_id: str, folder: Path) -> None:
    if rows.empty:
        raise ValueError(f"method {method_id!r} has no characterization factors")
    slug = method_slug(method_id)
    dp = _new_datapackage(folder, slug)
    dp.add_persistent_vector(
        matrix="characterization_matrix",
        name=f"{slug}-characterization",
        indices_array=_indices(rows["flow_bw_id"], rows["flow_bw_id"]),
        data_array=rows["factor"].to_numpy(dtype="float64"),
    )
    dp.finalize_serialization()


def write_datapackages(registry: Registry, root: Path) -> DatapackagePaths:
    """Write the inventory datapackage and one per method under ``root`` (the ``bw_package``
    folder). Raises ``ValueError`` before writing anything if an exchange references a
    ``bw_id`` missing from the registry or a method has no characterization factors."""
    root = Path(root)
    _check_exchange_ids(registry)
    cfs = registry.characterization_factors
    method_ids = list(registry.methods["method_id"])
    missing = [m for m in method_ids if m not in set(cfs["method_id"])]
    if missing:
        raise ValueError(f"methods without characterization factors: {missing}")
    _write_inventory(registry, root / INVENTORY_DIR)
    methods = {}
    for method_id in method_ids:
        folder = root / METHODS_DIR / method_slug(method_id)
        _write_method(cfs[cfs["method_id"] == method_id], method_id, folder)
        methods[method_id] = folder
    return DatapackagePaths(inventory=root / INVENTORY_DIR, methods=methods)


def load_inventory_datapackage(out_dir: Path):
    folder = Path(out_dir) / PACKAGE_DIR / INVENTORY_DIR
    return bwp.load_datapackage(bwp.generic_directory_filesystem(dirpath=folder))


def load_method_datapackage(out_dir: Path, method_id: str):
    folder = Path(out_dir) / PACKAGE_DIR / METHODS_DIR / method_slug(method_id)
    if not folder.is_dir():
        raise KeyError(f"no datapackage for method {method_id!r} under {folder.parent}")
    return bwp.load_datapackage(bwp.generic_directory_filesystem(dirpath=folder))


def score(out_dir: Path, process_code: str, method_id: str) -> float:
    """LCIA score of 1 unit of ``process_code`` with stock bw2calc; no bw2data project.

    ``out_dir`` is the folder holding ``registry/`` and ``bw_package/``."""
    import bw2calc as bc

    registry = load_registry(Path(out_dir) / REGISTRY_DIR)
    matches = registry.processes[registry.processes["code"] == process_code]
    if matches.empty:
        raise KeyError(f"process code {process_code!r} not in registry")
    bw_id = int(matches["bw_id"].iloc[0])
    lca = bc.LCA(
        {bw_id: 1.0},
        data_objs=[
            load_inventory_datapackage(out_dir),
            load_method_datapackage(out_dir, method_id),
        ],
    )
    lca.lci()
    lca.lcia()
    return float(lca.score)
