"""Backtest of the file-mode export against BAFU's published openLCA EF 3.1 results.

``run_backtest(files_dir, xlsx, out_dir)`` scores every registry process for the 25 EF 3.1
categories, joins the BAFU LCIA table, and writes the dashboard data folder. The scorer
(``bw2calc``) is imported lazily inside ``run_backtest`` so ``import sentier_brightway``
stays cheap.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from . import compare as _compare  # the module; "compare" must stay the submodule name
from .categories import CATEGORIES, Category, by_short
from .compare import Aligned, align, summarise
from .emit import (
    write_emissions_csv,
    write_meta,
    write_parquet_bundle,
    write_run_report,
    write_vs_csv,
)
from .reference import BafuReference

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps bw2calc out of the import
    from .scorer import Scores

DEFAULT_XLSX = Path("~/dds/sources/bafu-2026/BAFU-2026 v1_LCIA Results_corrected.zip")
# The synthetic test fixture has two methods, one under a non-real ionising id; these let
# the CLI run end to end on it (hidden ``--fixture-categories`` flag).
FIXTURE_CATEGORIES: tuple[Category, ...] = (
    by_short("climate"),
    Category("radiation", "ef-3.1:ionising-radiation", "Ionising Radiation", "fixture"),
)
SUMMARY_COLUMNS = (
    "short",
    "n_compared",
    "median_diff_pct",
    "within_5pct",
    "outliers_gt5pct",
    "max_abs_diff_pct",
)

__all__ = [
    "CATEGORIES",
    "Category",
    "DEFAULT_XLSX",
    "FIXTURE_CATEGORIES",
    "BacktestResult",
    "run_backtest",
    "render_summary",
]


@dataclass(frozen=True)
class BacktestResult:
    scores: "Scores"
    summary: pd.DataFrame
    out_dir: Path
    n_mapped: int
    n_unmatched: int
    n_unit_skipped: int


def _source_pins(files_dir: Path) -> list[dict]:
    """The export manifest's source pins, or an empty list when there is no manifest."""
    manifest = files_dir / "manifest.json"
    if not manifest.is_file():
        return []
    return list(json.loads(manifest.read_text()).get("sources", []))


def _counts(scores: "Scores", reference: BafuReference, aligned: Aligned) -> dict:
    res = aligned.frame["resolution"]
    return {
        "processes": int(len(scores.frame)),
        "reference_rows": int(len(reference.frame)),
        "mapped": int((res == "mapped").sum()),
        "unmatched": int((res == "unmatched").sum()),
        "unit_skipped": int((res == "unit_skipped").sum()),
        "location_aliases_applied": aligned.aliased_ref,
        "missing_methods": list(scores.missing_methods),
        "reference_blank_cells": reference.blank_cells,
    }


def run_backtest(
    files_dir: Path | str,
    xlsx: Path | str,
    out_dir: Path | str,
    categories: tuple[Category, ...] = CATEGORIES,
    check_n: int = 3,
) -> BacktestResult:
    """Score ``files_dir`` (a file-mode export) for ``categories``, spot-check ``check_n``
    processes against the plain bw2calc loop, compare with the BAFU table at ``xlsx`` and
    write ``emissions.csv``, ``vs_bafu.csv``, ``vs_bafu_meta.json``, ``backtest/*.parquet``
    and ``run_report.json`` into ``out_dir``."""
    from .scorer import check_against_loop, score_all  # bw2calc import stays lazy

    files_dir, out_dir = Path(files_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    started = time.perf_counter()
    reference = BafuReference.from_path(xlsx)
    timings["reference_s"] = round(time.perf_counter() - started, 3)
    scores = score_all(files_dir, categories)
    timings["score_s"] = round(scores.elapsed_s, 3)
    started = time.perf_counter()
    check_against_loop(files_dir, scores, categories, n=check_n)
    timings["check_s"] = round(time.perf_counter() - started, 3)
    aligned = align(scores.frame, reference.frame, categories)
    compared = _compare.compare(aligned, categories)
    summary = summarise(compared, categories)
    write_emissions_csv(scores.frame, aligned, categories, out_dir / "emissions.csv")
    write_vs_csv(compared, categories, out_dir / "vs_bafu.csv")
    write_meta(compared, categories, out_dir / "vs_bafu_meta.json")
    write_parquet_bundle(scores.frame, compared, summary, out_dir / "backtest")
    counts = _counts(scores, reference, aligned)
    write_run_report(
        out_dir / "run_report.json", _source_pins(files_dir), scores.solver, timings, counts
    )
    return BacktestResult(
        scores=scores,
        summary=summary,
        out_dir=out_dir,
        n_mapped=counts["mapped"],
        n_unmatched=counts["unmatched"],
        n_unit_skipped=counts["unit_skipped"],
    )


def render_summary(result: BacktestResult) -> str:
    """Human-readable outcome: where it went, the match counts and one line per category."""
    table = result.summary[list(SUMMARY_COLUMNS)].to_string(
        index=False, float_format=lambda v: f"{v:.2f}"
    )
    return (
        f"Backtest written to {result.out_dir}\n"
        f"mapped {result.n_mapped}, unmatched {result.n_unmatched}, "
        f"unit skipped {result.n_unit_skipped}, solver {result.scores.solver}, "
        f"scoring {result.scores.elapsed_s:.1f} s\n{table}"
    )
