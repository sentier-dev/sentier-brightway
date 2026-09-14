"""Shared helpers for validating and locating flat Sentier data frames."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import FLOW_IRI_PREFIX


def require_columns(df: pd.DataFrame, required: frozenset[str], path: Path) -> None:
    """Raise ``ValueError`` naming any of ``required`` missing from ``df.columns``."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns {missing}")


def codes_from_iris(iri: pd.Series, path: Path) -> pd.Series:
    """Strip ``FLOW_IRI_PREFIX`` from a series of flow IRIs, or raise ``ValueError`` naming
    ``path`` and the first offending value if any IRI does not start with it."""
    bad = iri[~iri.str.startswith(FLOW_IRI_PREFIX)]
    if not bad.empty:
        raise ValueError(
            f"{path}: flow iri does not start with {FLOW_IRI_PREFIX!r}: {bad.iloc[0]!r}"
        )
    return iri.str.removeprefix(FLOW_IRI_PREFIX)


def data_root_error(kind: str, expected: Path) -> FileNotFoundError:
    """Build a consistent error for a data root that does not hold the expected ``kind``."""
    return FileNotFoundError(
        f"no {kind} found; expected {expected}; --data-root (or $SENTIER_DATA_ROOT) must "
        "point at the folder that contains the sentier-inventory, sentier-vocab, "
        "sentier-methods and sentier-mappings checkouts"
    )
