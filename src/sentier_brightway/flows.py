"""Read elementary-flow terms from sentier-vocab, split by upstream source."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import BAFU_SOURCE_IRI, EF_SOURCE_IRI, FLOW_IRI_PREFIX, REPO_VOCAB

_KEEP = ["code", "name", "categories", "cas_number"]


def _read_all_shards(data_root: Path) -> pd.DataFrame:
    folder = Path(data_root) / REPO_VOCAB / "data" / "elementary-flows"
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no elementary-flow shards under {folder}")
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


def _categories(row: pd.Series) -> tuple[str, ...]:
    parts = (row.get("compartment"), row.get("sub_compartment"))
    return tuple(str(p) for p in parts if not pd.isna(p) and str(p) not in ("", "None", "nan"))


def _flows_for(data_root: Path, source_iri: str) -> pd.DataFrame:
    df = _read_all_shards(data_root)
    sel = df[df["source"] == source_iri]
    if sel.empty:
        raise ValueError(f"no elementary flows with source == {source_iri!r} in sentier-vocab")
    out = pd.DataFrame(
        {
            "code": sel["iri"].astype(str).str.removeprefix(FLOW_IRI_PREFIX),
            "name": sel["pref_label"].astype(str),
            "categories": [_categories(r) for _, r in sel.iterrows()],
            "cas_number": sel["cas_number"].where(sel["cas_number"].notna(), None),
        }
    )
    return out.drop_duplicates("code").reset_index(drop=True)[_KEEP]


def load_ef_flows(data_root: Path) -> pd.DataFrame:
    """EF 3.1 flows: columns ``code, name, categories, cas_number``."""
    return _flows_for(data_root, EF_SOURCE_IRI)


def load_bafu_flows(data_root: Path) -> pd.DataFrame:
    """BAFU-2026 flows: same columns; ``categories`` = (compartment, sub_compartment)."""
    return _flows_for(data_root, BAFU_SOURCE_IRI)
