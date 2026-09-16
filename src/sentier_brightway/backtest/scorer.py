"""Score every process for every category with one adjoint solve per category.

score(j, m) = c_mᵀ B A⁻¹ e_j = (A⁻ᵀ Bᵀ c_m)_j, so solving Aᵀ X = Bᵀ C once (C = per-flow
factors, one column per category) gives all scores. Matrices and index dictionaries come
from a stock ``bw2calc.LCA`` built on the file-mode datapackages; the solve uses pypardiso
when importable and scipy's SuperLU otherwise, and is verified by its residual.
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
from ..registry import load_registry
from .categories import META_COLUMNS, Category

CHARACTERIZATION = "characterization_matrix"
RESIDUAL_TOL = 1e-8  # relative residual ||Aᵀx - w|| / ||w|| accepted per category
LOOP_REL_TOL = 1e-6  # adjoint vs plain-loop relative tolerance
LOOP_ABS_FRACTION = 1e-9  # absolute floor as a fraction of the column's largest magnitude


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
    """Per-flow factors aligned to the biosphere matrix rows.

    Flows the method characterises but the inventory never emits are expected (often more
    than 90 % of a method's rows) and skipped; repeated flow ids are summed."""
    flow_ids = _vector_resource(dp, "indices")["row"].astype(np.int64)
    data = _vector_resource(dp, "data")
    rows = lca.dicts.biosphere
    known = np.fromiter(rows.keys(), dtype=np.int64, count=len(rows))
    positions = np.fromiter(rows.values(), dtype=np.int64, count=len(rows))
    present = np.isin(flow_ids, known)
    order = np.argsort(known)
    lookup = order[np.searchsorted(known[order], flow_ids[present])]
    c = np.zeros(lca.biosphere_matrix.shape[0])
    np.add.at(c, positions[lookup], data[present])
    return c


def _check_residual(
    solved: sp.spmatrix, x: np.ndarray, rhs: np.ndarray, shorts: tuple[str, ...]
) -> None:
    """Raise if any column's relative residual of ``solved @ x = rhs`` exceeds
    ``RESIDUAL_TOL``; pypardiso returns garbage silently on a singular system."""
    tiny = np.finfo(float).tiny
    residual = np.linalg.norm(solved @ x - rhs, axis=0) / np.maximum(
        np.linalg.norm(rhs, axis=0), tiny
    )
    worst = int(residual.argmax())
    if residual[worst] > RESIDUAL_TOL:
        raise RuntimeError(
            f"adjoint solve residual {residual[worst]:.3g} > {RESIDUAL_TOL:g} "
            f"for category {shorts[worst]!r}"
        )


def _solve_transposed(
    a: sp.spmatrix, rhs: np.ndarray, shorts: tuple[str, ...]
) -> tuple[np.ndarray, str]:
    """Solve ``aᵀ x = rhs`` for a dense 2-D ``rhs``; pypardiso if installed, else SuperLU.
    ``shorts`` names the columns of ``rhs`` in the residual error."""
    at = a.T.tocsc()
    try:
        import pypardiso  # type: ignore[import-not-found]
    except ImportError:
        from scipy.sparse.linalg import splu

        x, solver = splu(at).solve(rhs), "scipy"
    else:
        x, solver = np.asarray(pypardiso.spsolve(at.tocsr(), rhs)).reshape(rhs.shape), "pypardiso"
    _check_residual(at, x, rhs, shorts)
    return x, solver


def _load_methods(
    files_dir: Path, categories: tuple[Category, ...]
) -> tuple[list[tuple[Category, bwp.Datapackage]], tuple[str, ...]]:
    present, missing = [], []
    for cat in categories:
        try:
            present.append((cat, load_method_datapackage(files_dir, cat.method_id)))
        except KeyError:
            missing.append(cat.method_id)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"method datapackage for {cat.method_id!r} is unreadable: {exc}"
            ) from exc
    if not present:
        raise ValueError("no method datapackage found for any requested category")
    return present, tuple(missing)


def _build_lca(files_dir: Path, method_dp: bwp.Datapackage, any_id: int) -> bc.LCA:
    """Matrices and dictionaries only; no throwaway solve when bw2calc allows it."""
    lca = bc.LCA({any_id: 1.0}, data_objs=[load_inventory_datapackage(files_dir), method_dp])
    if hasattr(lca, "load_lci_data"):
        lca.load_lci_data()
    else:  # pragma: no cover - older bw2calc
        lca.lci()
    return lca


def _product_rows(lca: bc.LCA, bw_ids: np.ndarray) -> np.ndarray:
    mapping = lca.dicts.product
    absent = [int(i) for i in bw_ids if int(i) not in mapping]
    if absent:
        raise ValueError(f"registry processes not in technosphere: {absent[:10]}")
    return np.fromiter((mapping[int(i)] for i in bw_ids), dtype=np.int64, count=len(bw_ids))


def score_all(files_dir: Path | str, categories: tuple[Category, ...]) -> Scores:
    """Scores of 1 unit of every registry process for every category, via one adjoint
    solve. Categories whose method datapackage is absent get a NaN column and are listed
    in ``missing_methods``; ``ValueError`` if none is present or no category is given."""
    if not categories:
        raise ValueError("no categories requested")
    files_dir = Path(files_dir)
    started = time.perf_counter()
    registry = load_registry(files_dir / REGISTRY_DIR)
    present, missing = _load_methods(files_dir, categories)
    bw_ids = registry.processes["bw_id"].to_numpy(dtype=np.int64)
    lca = _build_lca(files_dir, present[0][1], int(bw_ids[0]))
    rows = _product_rows(lca, bw_ids)
    a, b = lca.technosphere_matrix, lca.biosphere_matrix
    rhs = np.column_stack([b.T @ _characterization_vector(dp, lca) for _, dp in present])
    x, solver = _solve_transposed(a, rhs, tuple(cat.short for cat, _ in present))
    values = np.full((len(bw_ids), len(categories)), math.nan)
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
    rel: float = LOOP_REL_TOL,
) -> None:
    """Recompute ``n`` random processes with the plain bw2calc demand loop; raise on mismatch.

    Tolerances: the plain loop solves ``A x = e_j`` with scipy's forward solver, which is the
    less accurate side (scipy and pardiso have been seen to disagree by up to 1.5e-7 relative
    on small scores), hence ``rel = 1e-6`` by default. Each category also gets an absolute
    floor of ``LOOP_ABS_FRACTION`` times the largest magnitude in its column, so scores near
    zero are judged against the category's scale rather than their own tiny value.
    Categories listed in ``scores.missing_methods`` (NaN columns) are skipped; a category
    without a column in ``scores.frame`` is a ``ValueError``."""
    absent = [cat.short for cat in categories if cat.short not in scores.frame.columns]
    if absent:
        raise ValueError(f"categories without a scores column: {absent}")
    checked = [cat for cat in categories if cat.method_id not in scores.missing_methods]
    floors = {
        cat.short: LOOP_ABS_FRACTION * float(np.nanmax(np.abs(scores.frame[cat.short])))
        for cat in checked
    }
    rng = random.Random(seed)
    sample = scores.frame.sample(n=min(n, len(scores.frame)), random_state=rng.randrange(2**32))
    bw_ids = [int(i) for i in sample["bw_id"]]
    methods = [(cat, load_method_datapackage(files_dir, cat.method_id)) for cat in checked]
    loop = _loop_scores(load_inventory_datapackage(files_dir), [dp for _, dp in methods], bw_ids)
    for k, (cat, _) in enumerate(methods):
        for code, ours, ref in zip(sample["code"], sample[cat.short], loop[:, k]):
            if not math.isclose(float(ours), float(ref), rel_tol=rel, abs_tol=floors[cat.short]):
                raise RuntimeError(
                    f"adjoint score {float(ours)!r} != bw2calc loop {float(ref)!r} "
                    f"for {code} / {cat.method_id}"
                )


def _loop_scores(
    inventory: bwp.Datapackage, methods: list[bwp.Datapackage], bw_ids: list[int]
) -> np.ndarray:
    """Plain ``bw2calc`` scores, shape ``(len(bw_ids), len(methods))``: one LCA whose
    technosphere and biosphere are built once, one forward ``lci`` per demand and
    ``switch_method`` (characterization matrix only) per method."""
    lca = bc.LCA({bw_ids[0]: 1.0}, data_objs=[inventory, methods[0]])
    out = np.empty((len(bw_ids), len(methods)))
    for i, bw_id in enumerate(bw_ids):
        lca.lci(demand={bw_id: 1.0})
        for k, method in enumerate(methods):
            lca.switch_method([method])
            lca.lcia()
            out[i, k] = lca.score
    return out
