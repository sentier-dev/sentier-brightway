"""Write the dashboard CSVs, the box-plot JSON, the worst-N lists, the meta sidecar, the
parquet bundle and the run report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .._version import __version__
from .boxes import WORST_N, boxes_payload, worst_rows
from .categories import Category, shorts
from .compare import FOLD_CAP_PCT, MAPPED, NEAR_ZERO_FACTOR, UNMATCHED, Aligned, Compared

BASELINE = "BAFU-2026 v1 LCIA Results (openLCA, EF 3.1)"
EMISSIONS_CSV = "emissions.csv"  # absolute scores; read by dashboard/backtest_dashboard.html
VS_BAFU_CSV = "vs_bafu.csv"  # pct vs BAFU; read by the dashboard
VS_BAFU_META = "vs_bafu_meta.json"
OUTLIER_REASONS = "outlier_reasons.json"  # per-category notes; header (i) + cell tooltip
BOXES_JSON = "boxes.json"  # box-plot statistics per sector and category; the page's main view
WORST_DIR = "worst"  # <short>.json: the WORST_N rows with the largest |pct| per category
BACKTEST_DIR = "backtest"  # parquet bundle folder
RUN_REPORT = "run_report.json"
SCORE_FORMAT = "%.10g"  # absolute scores: plain or scientific, 10 significant digits
PCT_FORMAT = "%.4f"  # pct columns are rounded to 4 decimals by compare()


def _display(frame: pd.DataFrame) -> pd.Series:
    """The dashboard's row label: ``"<name> - <location>"`` of our process."""
    return frame["name"] + " - " + frame["location"]


def write_emissions_csv(
    scores: pd.DataFrame, aligned: Aligned, categories: tuple[Category, ...], path: Path
) -> None:
    """One row per process with absolute scores: the value converted to the table's unit
    for mapped rows, our raw score (our unit) for unmatched and unit-skipped rows.
    NaN cells are written blank."""
    a = aligned.frame
    raw = scores.set_index("code").loc[a["code"]]
    mapped = (a["resolution"] == MAPPED).to_numpy()
    columns = {
        "code": a["code"].to_numpy(),
        "name": _display(a).to_numpy(),
        "mapped_to": a["ref_product"].fillna("").to_numpy(),
        "type": "",
        "resolution": a["resolution"].to_numpy(),
    }
    for cat in categories:
        converted = a[f"{cat.short}_ours"].to_numpy()
        columns[cat.short] = pd.Series(converted).where(mapped, raw[cat.short].to_numpy())
    pd.DataFrame(columns).to_csv(path, index=False, float_format=SCORE_FORMAT, na_rep="")


def write_vs_csv(compared: Compared, categories: tuple[Category, ...], path: Path) -> None:
    """Percent differences for mapped rows, with the reference product and unit."""
    a = compared.aligned.frame.set_index("code").loc[compared.frame["code"]]
    columns = {
        "code": compared.frame["code"].to_numpy(),
        "name": _display(a).to_numpy(),
        "mapped_to": a["ref_product"].to_numpy(),
        "type": "",
        "resolution": MAPPED,
        "name_ref": a["ref_product"].to_numpy(),
        "mapped_to_ref": a["ref_unit"].to_numpy(),
    }
    for cat in categories:
        columns[cat.short] = compared.frame[cat.short].to_numpy()
    pd.DataFrame(columns).to_csv(path, index=False, float_format=PCT_FORMAT, na_rep="")


def write_boxes(compared: Compared, categories: tuple[Category, ...], path: Path) -> None:
    """``boxes.json``: the box-plot statistics of every category, for all mapped rows and
    per sector. Compact, keys sorted, so the file is small and byte-identical across runs."""
    payload = {"baseline": BASELINE, **boxes_payload(compared, categories)}
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def write_worst(compared: Compared, categories: tuple[Category, ...], folder: Path) -> None:
    """``worst/<short>.json``: the ``WORST_N`` mapped rows with the largest |pct| per
    category (finite pct only), sorted by |pct| descending then code."""
    folder.mkdir(parents=True, exist_ok=True)
    for cat in categories:
        rows = worst_rows(compared, cat, n=WORST_N)
        text = json.dumps(rows, indent=1, ensure_ascii=False) + "\n"
        (folder / f"{cat.short}.json").write_text(text, encoding="utf-8")


def _pairs(frame: pd.DataFrame) -> list[list[str]]:
    return [[str(n), str(loc)] for n, loc in zip(frame["name"], frame["location"])]


def write_meta(compared: Compared, categories: tuple[Category, ...], path: Path) -> None:
    """Sidecar the dashboard reads for the guard thresholds and the unmatched lists."""
    a = compared.aligned
    unmatched_ours = a.frame[a.frame["resolution"] == UNMATCHED]
    meta = {
        "baseline": BASELINE,
        "n_common": int(len(compared.frame)),
        "near_zero_factor": NEAR_ZERO_FACTOR,
        "fold_cap_pct": FOLD_CAP_PCT,
        "thresholds": {c.short: float(compared.thresholds[c.short]) for c in categories},
        "suppressed": {c.short: dict(compared.suppressed[c.short]) for c in categories},
        "unmatched_ours": _pairs(unmatched_ours),
        "unmatched_ref": [list(key) for key in a.unmatched_ref],
        "unit_skipped": {f"{ours} -> {table}": n for (ours, table), n in a.unit_skipped.items()},
        "location_aliases_applied": a.aliased_ref,
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


_CHROMIUM_NOTE = (
    "BAFU treats unspecified 'Chromium' as Cr(III) (no cancer factor); EF 3.1's own "
    "'Chromium' flow carries the Cr(VI) factors and sentier-mappings keeps the faithful "
    "mapping by decision (2026-09-14), so this category is expected to be roughly 1.3x "
    "(total) and 2x (inorganics) BAFU's."
)
# Documentation, not data: the known, accepted systematic deviations per category. The
# page reads ``{short: {short, long, tag, not_a_bug, count, impact_level}}``; ``count: 0``
# with ``impact_level`` renders as a library-wide note behind the header (i). Categories
# without a note are simply absent.
OUTLIER_NOTES: dict[str, dict] = {
    "ht_c": {
        "short": "Unspecified 'Chromium' scored as Cr(VI) (EF 3.1 flow), BAFU uses Cr(III).",
        "long": _CHROMIUM_NOTE,
        "tag": "chromium_speciation",
        "not_a_bug": True,
        "count": 0,
        "impact_level": True,
    },
    "ht_c_inorg": {
        "short": "Unspecified 'Chromium' scored as Cr(VI) (EF 3.1 flow), BAFU uses Cr(III).",
        "long": _CHROMIUM_NOTE,
        "tag": "chromium_speciation",
        "not_a_bug": True,
        "count": 0,
        "impact_level": True,
    },
    "water": {
        "short": "Global water-use factors only in v0.1; regionalised flows deviate.",
        "long": (
            "Regionalised EF water-use factors are not installed in v0.1 (global factors "
            "only); AU/ID/CH resource flows deviate for that reason."
        ),
        "tag": "no_regionalised_factors",
        "not_a_bug": True,
        "count": 0,
        "impact_level": True,
    },
    "radiation": {
        "short": "Radon-222 [low pop., long-term] per Bq instead of per kBq on BAFU's side.",
        "long": (
            "Radon-222 [low pop., long-term] appears to be characterised per Bq instead of "
            "per kBq on BAFU's side for a few processes."
        ),
        "tag": "reference_unit_scale",
        "not_a_bug": True,
        "count": 0,
        "impact_level": True,
    },
}


def write_outlier_reasons(path: Path) -> None:
    """The fixed, code-owned category notes the dashboard shows behind the header (i)."""
    unknown = set(OUTLIER_NOTES) - set(shorts())
    if unknown:
        raise ValueError(f"outlier notes for unknown categories: {sorted(unknown)}")
    path.write_text(json.dumps(OUTLIER_NOTES, indent=2, ensure_ascii=False))


def write_parquet_bundle(
    scores: pd.DataFrame, compared: Compared, summary: pd.DataFrame, folder: Path
) -> None:
    """``scores``, ``reference`` (aligned, our unit reconciled), ``diff_pct`` (long) and
    ``summary`` parquet files for downstream analysis."""
    folder.mkdir(parents=True, exist_ok=True)
    shorts = [c for c in compared.frame.columns if c != "code"]
    scores.to_parquet(folder / "scores.parquet", index=False)
    ref_cols = [
        "code",
        "name",
        "location",
        "sector",
        "ref_unit",
        "resolution",
        *[f"{s}_ref" for s in shorts],
    ]
    compared.aligned.frame[ref_cols].to_parquet(folder / "reference.parquet", index=False)
    long = compared.frame.melt(id_vars="code", var_name="short", value_name="pct")
    long.to_parquet(folder / "diff_pct.parquet", index=False)
    summary.to_parquet(folder / "summary.parquet", index=False)


def write_run_report(
    path: Path, pins: list[dict], solver: str, timings: dict, counts: dict
) -> None:
    """Provenance: version, source pins, solver, timings and row counts of one run."""
    report = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sentier_brightway_version": __version__,
        "baseline": BASELINE,
        "sources": list(pins),
        "solver": solver,
        "timings_s": dict(timings),
        "counts": dict(counts),
    }
    path.write_text(json.dumps(report, indent=2))
