"""Write the dashboard CSVs, the meta sidecar, the parquet bundle and the run report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .. import __version__
from .categories import Category
from .compare import FOLD_CAP_PCT, MAPPED, NEAR_ZERO_FACTOR, UNMATCHED, Aligned, Compared

BASELINE = "BAFU-2026 v1 LCIA Results (openLCA, EF 3.1)"
LEAD = ("code", "name", "mapped_to", "type", "resolution")
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
