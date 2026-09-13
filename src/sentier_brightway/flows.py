"""Read elementary-flow terms from sentier-vocab, split by upstream source."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._frames import data_root_error, require_columns
from .constants import BAFU_SOURCE_IRI, EF_SOURCE_IRI, FLOW_IRI_PREFIX, REPO_VOCAB

SHARD_COLUMNS = frozenset(
    {"iri", "pref_label", "source", "compartment", "sub_compartment", "cas_number"}
)


def _read_all_shards(data_root: Path) -> pd.DataFrame:
    folder = Path(data_root) / REPO_VOCAB / "data" / "elementary-flows"
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise data_root_error("elementary-flow shards", folder)
    shards = []
    for file in files:
        shard = pd.read_parquet(file)
        require_columns(shard, SHARD_COLUMNS, file)
        shards.append(shard)
    return pd.concat(shards, ignore_index=True)


def _categories(compartment: pd.Series, sub_compartment: pd.Series) -> list[tuple[str, ...]]:
    comp = compartment.astype(object).where(compartment.notna(), None)
    sub = sub_compartment.astype(object).where(sub_compartment.notna(), None)
    return [tuple(p for p in (c, s) if p is not None) for c, s in zip(comp, sub)]


def _codes(iri: pd.Series) -> pd.Series:
    bad = iri[~iri.str.startswith(FLOW_IRI_PREFIX)]
    if not bad.empty:
        raise ValueError(f"flow iri does not start with {FLOW_IRI_PREFIX!r}: {bad.iloc[0]!r}")
    return iri.str.removeprefix(FLOW_IRI_PREFIX)


def _flows_for(data_root: Path, source_iri: str) -> pd.DataFrame:
    df = _read_all_shards(data_root)
    sel = df[df["source"] == source_iri]
    if sel.empty:
        raise ValueError(f"no elementary flows with source == {source_iri!r} in sentier-vocab")
    code = _codes(sel["iri"].astype(str))
    out = pd.DataFrame(
        {
            "code": code,
            "name": sel["pref_label"].astype(str),
            "categories": _categories(sel["compartment"], sel["sub_compartment"]),
            "cas_number": sel["cas_number"].astype(object).where(sel["cas_number"].notna(), None),
        }
    )
    duplicates = sorted(out["code"][out["code"].duplicated()].unique())
    if duplicates:
        raise ValueError(f"duplicate flow codes: {duplicates[:5]}")
    return out.reset_index(drop=True)


def load_ef_flows(data_root: Path) -> pd.DataFrame:
    """EF 3.1 flows: columns ``code, name, categories, cas_number``."""
    return _flows_for(data_root, EF_SOURCE_IRI)


def load_bafu_flows(data_root: Path) -> pd.DataFrame:
    """BAFU-2026 flows: same columns; ``categories`` = (compartment, sub_compartment)."""
    return _flows_for(data_root, BAFU_SOURCE_IRI)
