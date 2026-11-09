"""Read elementary-flow terms from sentier-vocab, split by upstream source.

sentier-vocab keeps every term of one source release in ``terms/<release>[-NN].parquet``,
all term types mixed: the ``type`` column says which rows are elementary flows, and the
flow facets (compartment, sub-compartment, CAS number) sit in the JSON ``attributes``
column.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ._frames import codes_from_iris, data_root_error, require_columns
from .constants import DEFAULT_SOURCE, EF_SOURCE_IRI, REPO_VOCAB, source_iri

TERMS_FOLDER = "terms"
FLOW_TYPE = "elementary-flow"
TERM_COLUMNS = frozenset({"iri", "type", "pref_label", "source", "attributes"})


def _read_flow_terms(folder: Path) -> pd.DataFrame:
    """The elementary-flow rows of every term file in ``folder``."""
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise data_root_error("vocab term files", folder)
    frames = []
    for file in files:
        require_columns(pd.DataFrame(columns=pq.read_schema(file).names), TERM_COLUMNS, file)
        frames.append(
            pd.read_parquet(
                file, columns=sorted(TERM_COLUMNS), filters=[("type", "==", FLOW_TYPE)]
            )
        )
    return pd.concat(frames, ignore_index=True)


def _attributes(column: pd.Series) -> list[dict]:
    return [json.loads(value) if isinstance(value, str) and value else {} for value in column]


def _flows_for(data_root: Path, source_iri: str) -> pd.DataFrame:
    folder = Path(data_root) / REPO_VOCAB / TERMS_FOLDER
    df = _read_flow_terms(folder)
    sel = df[df["source"] == source_iri]
    if sel.empty:
        raise ValueError(f"no elementary flows with source == {source_iri!r} in sentier-vocab")
    code = codes_from_iris(sel["iri"].astype(str), folder)
    attributes = _attributes(sel["attributes"])
    out = pd.DataFrame(
        {
            "code": code,
            "name": sel["pref_label"].astype(str),
            "categories": pd.Series(
                [
                    tuple(
                        part
                        for part in (a.get("compartment"), a.get("sub_compartment"))
                        if part is not None
                    )
                    for a in attributes
                ],
                index=sel.index,
                dtype=object,
            ),
            "cas_number": pd.Series(
                [a.get("cas_number") for a in attributes], index=sel.index, dtype=object
            ),
        }
    )
    duplicates = sorted(out["code"][out["code"].duplicated()].unique())
    if duplicates:
        raise ValueError(f"duplicate flow codes: {duplicates[:5]}")
    return out.reset_index(drop=True)


def load_ef_flows(data_root: Path) -> pd.DataFrame:
    """EF 3.1 flows: columns ``code, name, categories, cas_number``."""
    return _flows_for(data_root, EF_SOURCE_IRI)


def load_source_flows(data_root: Path, source: str = DEFAULT_SOURCE) -> pd.DataFrame:
    """Flows of one inventory source (vocab Source IRI slug == inventory ``source`` id):
    same columns; ``categories`` = (compartment, sub_compartment)."""
    return _flows_for(data_root, source_iri(source))


def load_bafu_flows(data_root: Path) -> pd.DataFrame:
    """BAFU-2026 flows; kept for compatibility, same as ``load_source_flows(root)``."""
    return load_source_flows(data_root, DEFAULT_SOURCE)
