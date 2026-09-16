"""Score every process for every category with one adjoint solve per category.

score(j, m) = c_mᵀ B A⁻¹ e_j = (A⁻ᵀ Bᵀ c_m)_j, so solving Aᵀ X = Bᵀ C once (C = per-flow
factors, one column per category) gives all scores. Matrices and index dictionaries come
from a stock ``bw2calc.LCA`` built on the file-mode datapackages; the solve uses pypardiso
when importable and scipy's SuperLU otherwise.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

import bw2calc as bc
import bw_processing as bwp
import numpy as np
import pandas as pd
import scipy.sparse as sp

from ..datapackage import REGISTRY_DIR, load_inventory_datapackage, load_method_datapackage
from ..datapackage import score as loop_score
from ..registry import load_registry
from .categories import Category

META_COLUMNS = ("bw_id", "code", "name", "location", "unit")
CHARACTERIZATION = "characterization_matrix"


@dataclass(frozen=True)
class Scores:
    frame: pd.DataFrame  # META_COLUMNS + one float column per category short
    values: np.ndarray  # (n_processes, n_categories), NaN where the method is missing
    solver: str
    elapsed_s: float
    missing_methods: tuple[str, ...]


def _vector_resource(dp: bwp.Datapackage, kind: str) -> np.ndarray:
    """The ``characterization_matrix`` vector's ``indices`` or ``data`` array, found by its
    resource metadata rather than by name (bw_processing normalises names)."""
    names = [
        r["name"]
        for r in dp.resources
        if r.get("matrix") == CHARACTERIZATION and r.get("kind") == kind
    ]
    if len(names) != 1:
        raise ValueError(f"expected one {CHARACTERIZATION} {kind} resource, found {names}")
    array, _ = dp.get_resource(names[0])
    return array


def _characterization_vector(dp: bwp.Datapackage, lca: bc.LCA) -> np.ndarray:
    """Per-flow factors aligned to the biosphere matrix rows (0 for flows not in it)."""
    indices = _vector_resource(dp, "indices")
    data = _vector_resource(dp, "data")
    c = np.zeros(lca.biosphere_matrix.shape[0])
    rows = lca.dicts.biosphere
    for flow_id, value in zip(indices["row"], data):
        if int(flow_id) in rows:
            c[rows[int(flow_id)]] += float(value)
    return c


def _solve_transposed(a: sp.spmatrix, rhs: np.ndarray) -> tuple[np.ndarray, str]:
    """Solve ``aᵀ x = rhs`` for a dense 2-D ``rhs``; pypardiso if installed, else SuperLU."""
    at = a.T.tocsc()
    try:
        import pypardiso  # type: ignore[import-not-found]
    except ImportError:
        from scipy.sparse.linalg import splu

        return splu(at).solve(rhs), "scipy"
    return np.asarray(pypardiso.spsolve(at.tocsr(), rhs)).reshape(rhs.shape), "pypardiso"


def _load_methods(
    files_dir: Path, categories: tuple[Category, ...]
) -> tuple[list[tuple[Category, bwp.Datapackage]], tuple[str, ...]]:
    present, missing = [], []
    for cat in categories:
        try:
            present.append((cat, load_method_datapackage(files_dir, cat.method_id)))
        except KeyError:
            missing.append(cat.method_id)
    if not present:
        raise ValueError("no method datapackage found for any requested category")
    return present, tuple(missing)


def score_all(files_dir: Path | str, categories: tuple[Category, ...]) -> Scores:
    """Scores of 1 unit of every registry process for every category, via one adjoint
    solve. Categories whose method datapackage is absent get a NaN column and are listed
    in ``missing_methods``; ``ValueError`` if none is present."""
    files_dir = Path(files_dir)
    started = time.perf_counter()
    registry = load_registry(files_dir / REGISTRY_DIR)
    present, missing = _load_methods(files_dir, categories)
    any_id = int(registry.processes["bw_id"].iloc[0])
    lca = bc.LCA({any_id: 1.0}, data_objs=[load_inventory_datapackage(files_dir), present[0][1]])
    lca.lci()
    a, b = lca.technosphere_matrix, lca.biosphere_matrix
    rhs = np.column_stack([b.T @ _characterization_vector(dp, lca) for _, dp in present])
    x, solver = _solve_transposed(a, rhs)
    product_rows = lca.dicts.product
    rows = np.fromiter((product_rows[int(i)] for i in registry.processes["bw_id"]), dtype=np.int64)
    values = np.full((len(registry.processes), len(categories)), math.nan)
    column_of = {cat.short: k for k, (cat, _) in enumerate(present)}
    for j, cat in enumerate(categories):
        if cat.short in column_of:
            values[:, j] = x[rows, column_of[cat.short]]
    frame = registry.processes[list(META_COLUMNS)].reset_index(drop=True).copy()
    for j, cat in enumerate(categories):
        frame[cat.short] = values[:, j]
    return Scores(
        frame=frame,
        values=values,
        solver=solver,
        elapsed_s=time.perf_counter() - started,
        missing_methods=missing,
    )


def check_against_loop(
    files_dir: Path | str,
    scores: Scores,
    categories: tuple[Category, ...],
    n: int = 3,
    seed: int = 0,
    rel: float = 1e-8,
) -> None:
    """Recompute ``n`` random processes with the plain bw2calc demand loop; raise on mismatch."""
    rng = random.Random(seed)
    codes = rng.sample(list(scores.frame["code"]), k=min(n, len(scores.frame)))
    indexed = scores.frame.set_index("code")
    for code in codes:
        for cat in categories:
            if cat.method_id in scores.missing_methods:
                continue
            ours = float(indexed.loc[code, cat.short])
            ref = loop_score(files_dir, code, cat.method_id)
            if not math.isclose(ours, ref, rel_tol=rel, abs_tol=1e-15):
                raise RuntimeError(
                    f"adjoint score {ours!r} != bw2calc loop {ref!r} for {code} / {cat.method_id}"
                )
