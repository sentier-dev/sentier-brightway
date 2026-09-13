"""Shared helpers for validating and locating flat Sentier data frames."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def require_columns(df: pd.DataFrame, required: frozenset[str], path: Path) -> None:
    """Raise ``ValueError`` naming any of ``required`` missing from ``df.columns``."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns {missing}")


def data_root_error(kind: str, expected: Path) -> FileNotFoundError:
    """Build a consistent error for a data root that does not hold the expected ``kind``."""
    return FileNotFoundError(
        f"no {kind} found; expected {expected}; --data-root must point at the folder that "
        "contains the sentier-inventory, sentier-vocab, sentier-methods and sentier-mappings "
        "checkouts"
    )
