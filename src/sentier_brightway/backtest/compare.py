"""Join our scores with BAFU's, reconcile units, compute pct differences with the 4.0
dashboard's guards (zero reference blank, near-zero floor, fold cap), and summarise.

``Box``/``box_stats`` (the box-plot statistics the summary and ``boxes.py`` share) live
here so that ``boxes.py`` can import ``compare`` without a cycle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd

from .categories import META_COLUMNS, Category

NEAR_ZERO_FACTOR = 0.01  # of the median |reference| per category
FOLD_CAP_PCT = 1000.0
PCT_DECIMALS = 4
KEY = ("name", "location")
SECTOR_COLUMN = "sector"  # BAFU's top-level "Category"; carried onto the aligned frame
UNSPECIFIED_SECTOR = "unspecified"  # used when the reference has no sector column
MAPPED, UNMATCHED, UNIT_SKIPPED = "mapped", "unmatched", "unit_skipped"
OUTLIER_CAP = 500  # ``Box.outliers`` entries kept per box (``n_outliers`` is the full count)
WHISKER_K = 1.5  # whiskers end at the last value within q1/q3 -/+ WHISKER_K * IQR
BOX_DECIMALS = 4

# BAFU table unit spelling -> Brightway spelling (as written by sentier_brightway.units)
TABLE_UNITS = MappingProxyType(
    {
        "kg": "kilogram",
        "MJ": "megajoule",
        "kWh": "kilowatt hour",
        "Item(s)": "unit",
        "m3": "cubic meter",
        "m2": "square meter",
        "m": "meter",
        "km": "kilometer",
        "ha": "hectare",
        "h": "hour",
        "t*km": "ton kilometer",
        "p*km": "person kilometer",
        "km*a": "kilometer-year",
        "m2*a": "square meter-year",
    }
)
# (our unit, table unit normalised) -> multiply our per-unit score by this to get the
# score per table unit, e.g. per MJ = per kWh / 3.6
UNIT_FACTORS = MappingProxyType(
    {
        ("kilowatt hour", "megajoule"): 1 / 3.6,
        ("normal cubic meter", "cubic meter"): 1.0,
        ("kilometer", "meter"): 1 / 1000,
        ("hectare", "square meter"): 1e-4,
        ("meter-year", "kilometer-year"): 1000.0,
    }
)


# BAFU table location spelling -> ours (the registry's); applied to the reference side only
LOCATION_ALIASES = MappingProxyType(
    {
        "US-ERCOT": "ERCOT",
        "US-FRCC": "FRCC",
        "US-RFC": "RFC",
        "US-SERC": "SERC",
        "US-SPP": "SPP",
        "US-ASCC": "ASCC",
        "RER without CH": "Europe without Switzerland",
    }
)


def unit_factor(ours: str, table: str) -> float | None:
    """Factor turning our per-``ours`` score into per-``table`` unit; None when unknown."""
    table_norm = TABLE_UNITS.get(table, table)
    if ours == table_norm:
        return 1.0
    return UNIT_FACTORS.get((ours, table_norm))


@dataclass(frozen=True)
class Aligned:
    # META_COLUMNS + ref_unit, ref_product, sector (NaN unless a reference row was found),
    # resolution, <short>_ours (table unit), <short>_ref
    frame: pd.DataFrame
    unmatched_ref: tuple[tuple[str, str], ...]  # (name, location) of reference rows unused
    unit_skipped: Mapping[tuple[str, str], int]  # (our unit, table unit) -> count
    aliased_ref: int = 0  # reference rows whose location went through LOCATION_ALIASES


@dataclass(frozen=True)
class Compared:
    frame: pd.DataFrame  # code + one pct column per short (NaN = blank), mapped rows only
    aligned: Aligned
    thresholds: Mapping[str, float]  # short -> near-zero threshold
    suppressed: Mapping[str, Mapping[str, int]]  # short -> {near_zero, fold_capped}


@dataclass(frozen=True)
class Box:
    """Box-plot statistics of one category's finite pct values; every quantile is None
    when ``n == 0``. ``outliers`` are ``(code, pct)`` pairs sorted by |pct| descending
    (ties by code), capped at ``OUTLIER_CAP``."""

    n: int
    n_blank: int
    min: float | None
    q1: float | None
    median: float | None
    q3: float | None
    max: float | None
    lo: float | None
    hi: float | None
    n_outliers: int
    outliers: tuple[tuple[str, float], ...]


def _round_box(value: float) -> float:
    return round(float(value), BOX_DECIMALS) + 0.0  # no -0.0


def box_stats(pct: pd.Series, codes: pd.Series, cap: int = OUTLIER_CAP, n_blank: int = 0) -> Box:
    """Quartiles (linear interpolation), whisker ends and outliers of the finite values of
    ``pct``; ``codes`` labels the outliers and ``n_blank`` is passed through."""
    values = pct.to_numpy(dtype=float)
    finite = np.isfinite(values)
    vals, ids = values[finite], codes.to_numpy()[finite]
    if len(vals) == 0:
        return Box(0, n_blank, None, None, None, None, None, None, None, 0, ())
    q1, med, q3 = (float(np.percentile(vals, p)) for p in (25, 50, 75))
    iqr = q3 - q1
    inside = (vals >= q1 - WHISKER_K * iqr) & (vals <= q3 + WHISKER_K * iqr)
    out_idx = np.flatnonzero(~inside)
    order = sorted(out_idx, key=lambda i: (-abs(vals[i]), str(ids[i])))
    return Box(
        n=int(len(vals)),
        n_blank=n_blank,
        min=_round_box(vals.min()),
        q1=_round_box(q1),
        median=_round_box(med),
        q3=_round_box(q3),
        max=_round_box(vals.max()),
        lo=_round_box(vals[inside].min()),
        hi=_round_box(vals[inside].max()),
        n_outliers=int(len(out_idx)),
        outliers=tuple((str(ids[i]), _round_box(vals[i])) for i in order[:cap]),
    )


def _resolve(unit: str, ref_unit: object) -> tuple[str, float]:
    """(resolution, factor) for one row; the factor is NaN unless mapped."""
    if not isinstance(ref_unit, str):
        return UNMATCHED, math.nan
    factor = unit_factor(unit, ref_unit)
    if factor is None:
        return UNIT_SKIPPED, math.nan
    return MAPPED, factor


def _check_columns(frame: pd.DataFrame, needed: tuple[str, ...], what: str) -> None:
    missing = [c for c in needed if c not in frame.columns]
    if missing:
        raise ValueError(f"{what} frame lacks columns {missing}")


def _normalise_reference(reference: pd.DataFrame, shorts: list[str]) -> tuple[pd.DataFrame, int]:
    """Reference rows keyed the way our registry spells them: names stripped, locations
    aliased. ``ref_product`` keeps the table's own spelling. Returns the frame and the
    number of rows whose location was aliased."""
    ref = reference[[*KEY, "unit", *shorts]].rename(columns={"unit": "ref_unit"})
    sector = reference.get(SECTOR_COLUMN, UNSPECIFIED_SECTOR)
    location = ref["location"].map(lambda loc: LOCATION_ALIASES.get(loc, loc))
    aliased = int((location != ref["location"]).sum())
    ref = ref.assign(
        ref_product=ref["name"] + " - " + ref["location"],
        name=ref["name"].str.strip(),
        location=location,
        **{SECTOR_COLUMN: sector},
    )
    return ref, aliased


def align(
    scores: pd.DataFrame, reference: pd.DataFrame, categories: tuple[Category, ...]
) -> Aligned:
    """Left-join ``reference`` onto ``scores`` by (name, location) and convert our scores to
    the table's unit. Names are stripped on both sides and the reference's locations go
    through ``LOCATION_ALIASES`` before the join (ours stay as in the registry). Rows
    resolve to ``mapped``, ``unmatched`` (no reference row) or ``unit_skipped`` (reference
    found but no conversion known); ``<short>_ours`` is NaN unless mapped. The reference's
    ``sector`` column rides along (``UNSPECIFIED_SECTOR`` when the reference has none, NaN
    for unmatched rows). Neither input is modified."""
    shorts = [c.short for c in categories]
    _check_columns(scores, (*META_COLUMNS, *shorts), "scores")
    _check_columns(reference, (*KEY, "unit", *shorts), "reference")
    ref, aliased = _normalise_reference(reference, shorts)
    ours = scores[[*META_COLUMNS, *shorts]].assign(name=scores["name"].str.strip())
    try:
        merged = ours.merge(
            ref, on=list(KEY), how="left", suffixes=("_ours", "_ref"), validate="many_to_one"
        )
    except pd.errors.MergeError as exc:
        raise ValueError(f"duplicate (name, location) keys in the reference: {exc}") from exc
    resolved = [_resolve(u, r) for u, r in zip(merged["unit"], merged["ref_unit"])]
    resolution = pd.Series([r for r, _ in resolved], index=merged.index)
    factor = pd.Series([f for _, f in resolved], index=merged.index, dtype=float)
    converted = {f"{s}_ours": merged[f"{s}_ours"] * factor for s in shorts}
    out = merged.assign(resolution=resolution, **converted)
    order = [*META_COLUMNS, "ref_unit", "ref_product", SECTOR_COLUMN, "resolution"]
    order += [f"{s}_ours" for s in shorts] + [f"{s}_ref" for s in shorts]
    skipped: dict[tuple[str, str], int] = {}
    for (res, _), unit, ref_unit in zip(resolved, merged["unit"], merged["ref_unit"]):
        if res == UNIT_SKIPPED:
            skipped[(unit, ref_unit)] = skipped.get((unit, ref_unit), 0) + 1
    found = out.loc[resolution != UNMATCHED, list(KEY)]
    found_keys = set(zip(found["name"], found["location"]))
    unmatched_ref = tuple(
        sorted(
            original
            for original, key in zip(
                zip(reference["name"], reference["location"]), zip(ref["name"], ref["location"])
            )
            if key not in found_keys
        )
    )
    return Aligned(
        frame=out[order].reset_index(drop=True),
        unmatched_ref=unmatched_ref,
        unit_skipped=MappingProxyType(skipped),
        aliased_ref=aliased,
    )


def _pct(ours: pd.Series, ref: pd.Series, threshold: float) -> tuple[pd.Series, int, int]:
    """Percent difference with the guards: zero reference -> NaN; both sides below the
    threshold (reference non-zero) -> 0.0 (counted); |pct| above the fold cap -> NaN
    (counted). NaN on either side stays NaN; a rounded -0.0 becomes 0.0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (ours - ref) / ref.abs() * 100.0
    zero_ref = ref == 0
    near = (ours.abs() < threshold) & (ref.abs() < threshold) & ~zero_ref & ours.notna()
    pct = pct.mask(zero_ref, np.nan).mask(near, 0.0)
    capped = pct.abs() > FOLD_CAP_PCT
    pct = pct.mask(capped, np.nan)
    return pct.round(PCT_DECIMALS) + 0.0, int(near.sum()), int(capped.sum())  # no -0.0


def _threshold(ref: pd.Series) -> float:
    return NEAR_ZERO_FACTOR * float(ref.abs().median()) if ref.notna().any() else 0.0


def compare(aligned: Aligned, categories: tuple[Category, ...]) -> Compared:
    """Percent differences (ours vs reference, in the table's unit) for mapped rows."""
    mapped = aligned.frame[aligned.frame["resolution"] == MAPPED].reset_index(drop=True)
    columns: dict[str, pd.Series] = {"code": mapped["code"]}
    thresholds: dict[str, float] = {}
    suppressed: dict[str, Mapping[str, int]] = {}
    for cat in categories:
        ref = mapped[f"{cat.short}_ref"]
        thr = _threshold(ref)
        pct, near, capped = _pct(mapped[f"{cat.short}_ours"], ref, thr)
        columns[cat.short] = pct
        thresholds[cat.short] = thr
        suppressed[cat.short] = MappingProxyType({"near_zero": near, "fold_capped": capped})
    return Compared(
        frame=pd.DataFrame(columns),
        aligned=aligned,
        thresholds=MappingProxyType(thresholds),
        suppressed=MappingProxyType(suppressed),
    )


def _or_nan(value: float | None) -> float:
    return math.nan if value is None else value


def _summary_row(cat: Category, compared: Compared, n_skipped: int) -> dict:
    box = box_stats(compared.frame[cat.short], compared.frame["code"])
    pct = compared.frame[cat.short]
    pct = pct[np.isfinite(pct)]
    n = int(len(pct))
    return {
        "short": cat.short,
        "method_id": cat.method_id,
        "n_compared": n,
        "mean_diff_pct": float(pct.mean()) if n else math.nan,
        "median_diff_pct": float(pct.median()) if n else math.nan,
        "q1_diff_pct": _or_nan(box.q1),
        "q3_diff_pct": _or_nan(box.q3),
        "std_diff_pct": float(pct.std()) if n > 1 else math.nan,
        "within_1pct": int((pct.abs() <= 1).sum()),
        "within_5pct": int((pct.abs() <= 5).sum()),
        "outliers_gt5pct": int((pct.abs() > 5).sum()),
        "max_abs_diff_pct": float(pct.abs().max()) if n else math.nan,
        "whisker_lo": _or_nan(box.lo),
        "whisker_hi": _or_nan(box.hi),
        "n_outliers": box.n_outliers,
        "n_near_zero_floored": compared.suppressed[cat.short]["near_zero"],
        "n_fold_capped": compared.suppressed[cat.short]["fold_capped"],
        "n_unit_skipped": n_skipped,
    }


def summarise(compared: Compared, categories: tuple[Category, ...]) -> pd.DataFrame:
    """One row per category over the finite pct values (quartiles, whisker ends and the
    outlier count as in ``box_stats``); ``n_unit_skipped`` is the number of unit-skipped
    processes and is repeated on every row."""
    n_skipped = int((compared.aligned.frame["resolution"] == UNIT_SKIPPED).sum())
    return pd.DataFrame([_summary_row(cat, compared, n_skipped) for cat in categories])
