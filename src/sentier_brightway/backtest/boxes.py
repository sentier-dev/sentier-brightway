"""Box-plot statistics per sector and category, and the worst-N rows per category, over
the compared pct frame. Pure functions of ``Compared``; ``emit.py`` serialises them.

``Box``/``box_stats`` are defined in ``compare.py`` (the summary uses them too) and
re-exported here.
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from .categories import UNSPECIFIED_SECTOR, Category
from .compare import (  # noqa: F401  (re-exported)
    BOX_DECIMALS,
    OUTLIER_CAP,
    SECTOR_COLUMN,
    SECTOR_OUTLIER_CAP,
    SIGNIFICANT,
    WHISKER_K,
    Box,
    Compared,
    box_stats,
)

ALL_SECTORS = "all"
WORST_N = 200
WORST_KEYS = ("code", "name", "location", "sector", "unit", "ours", "ref", "pct")  # row schema


def _mapped_meta(compared: Compared) -> pd.DataFrame:
    """The aligned rows behind ``compared.frame`` (same order), indexed like it, with a
    string ``sector`` (blank -> ``UNSPECIFIED_SECTOR``)."""
    meta = compared.aligned.frame.set_index("code").loc[compared.frame["code"]]
    sector = meta[SECTOR_COLUMN].where(meta[SECTOR_COLUMN].notna(), UNSPECIFIED_SECTOR)
    sector = sector.astype(str).str.strip().replace("", UNSPECIFIED_SECTOR)
    return meta.assign(**{SECTOR_COLUMN: sector}).reset_index()


def _sorted_sectors(sector: pd.Series) -> list[str]:
    """Distinct sector labels, case-insensitive order ("Others" sorts among the o's), the
    original spelling as a stable tie-break."""
    return sorted(set(sector), key=lambda s: (s.casefold(), s))


def _box_dict(box: Box) -> dict:
    payload = asdict(box)
    payload["outliers"] = [list(pair) for pair in box.outliers]
    return payload


def boxes_payload(compared: Compared, categories: tuple[Category, ...]) -> dict:
    """``{"sectors", "categories", "boxes": {sector: {short: box}}}`` with ``"all"`` first;
    sectors are the distinct sector values of the mapped rows, sorted case-insensitively
    (``_sorted_sectors``). The ``"all"`` boxes
    keep up to ``OUTLIER_CAP`` outliers, a named sector's up to ``SECTOR_OUTLIER_CAP``."""
    meta = _mapped_meta(compared)
    sectors = [ALL_SECTORS, *_sorted_sectors(meta[SECTOR_COLUMN])]
    codes = compared.frame["code"]
    boxes: dict[str, dict[str, dict]] = {}
    for sector in sectors:
        mask = (
            np.ones(len(meta), dtype=bool)
            if sector == ALL_SECTORS
            else (meta[SECTOR_COLUMN] == sector).to_numpy()
        )
        cap = OUTLIER_CAP if sector == ALL_SECTORS else SECTOR_OUTLIER_CAP
        per_category: dict[str, dict] = {}
        for cat in categories:
            pct = compared.frame[cat.short][mask]
            n_blank = int(pct.isna().sum())
            box = box_stats(pct, codes[mask], cap=cap, n_blank=n_blank)
            per_category[cat.short] = _box_dict(box)
        boxes[sector] = per_category
    return {
        "sectors": sectors,
        "categories": [c.short for c in categories],
        "boxes": boxes,
    }


def _plain(value: float) -> float:
    return float(f"{float(value):.{SIGNIFICANT}g}") + 0.0


def worst_rows(compared: Compared, cat: Category, n: int = WORST_N) -> list[dict]:
    """The ``n`` mapped rows with the largest |pct| for ``cat`` (finite pct only), sorted by
    |pct| descending then code; ``ours``/``ref`` are in the table's unit."""
    meta = _mapped_meta(compared)
    pct = compared.frame[cat.short].to_numpy(dtype=float)
    finite = np.flatnonzero(np.isfinite(pct))
    codes = compared.frame["code"].to_numpy()
    order = sorted(finite, key=lambda i: (-abs(pct[i]), str(codes[i])))[:n]
    ours = meta[f"{cat.short}_ours"].to_numpy(dtype=float)
    ref = meta[f"{cat.short}_ref"].to_numpy(dtype=float)
    return [
        dict(
            zip(
                WORST_KEYS,
                (
                    str(codes[i]),
                    str(meta["name"].iloc[i]),
                    str(meta["location"].iloc[i]),
                    str(meta[SECTOR_COLUMN].iloc[i]),
                    str(meta["ref_unit"].iloc[i]),
                    _plain(ours[i]),
                    _plain(ref[i]),
                    round(float(pct[i]), BOX_DECIMALS) + 0.0,
                ),
            )
        )
        for i in order
    ]
