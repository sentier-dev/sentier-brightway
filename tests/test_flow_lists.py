"""Tests for sentier_brightway.flow_lists: the FOODTURE xlsx of BAFU flows as they land
in Brightway. The ``flow_root`` fixture extends the shared synthetic data root with one
unmapped used flow (B5), the nomenclature target E3 in the EF vocab, and a coverage.json."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

# flow_lists import added in Task 2
from sentier_brightway.bridge import load_bridge
from sentier_brightway.flows import load_ef_flows, load_source_flows
from sentier_brightway.inventory import load_inventory
from tests.conftest import B1, B2, B3, E3, FLOWS, INVENTORY_FOLDER, P2

B5 = "b5b5b5b5-0000-5000-8000-000000000005"  # used by P2, no EF counterpart (unmapped)
EF_SOURCE = "https://vocab.sentier.dev/sources/ef-3.1"
BAFU_SOURCE = "https://vocab.sentier.dev/sources/bafu-2026"
BRIDGE_DIR = "sentier-mappings/data/bafu-2026-v1__ef-3.1"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_flow_lists.py"


def _coverage_row(name, code, unit, context, status, **extra):
    row = {
        "source": {"name": name, "code": code, "unit": unit, "context": context},
        "status": status,
    }
    row.update(extra)
    return row


COVERAGE = {
    "name": "bafu-2026-v1__ef-3.1-coverage",
    "version": "0.1.0",
    "coverage": [
        _coverage_row(
            "Carbon dioxide, fossil",
            B1,
            "kg",
            ["emissions to air", "unspecified"],
            "mapped",
            package="biosphere-1-curated",
            tier=1,
            placement="exact",
        ),
        _coverage_row(
            "Uranium-238",
            B2,
            "Bq",
            ["emissions to water", "lake"],
            "mapped",
            package="biosphere-1-curated",
            caveats=["unit converted Bq to kBq"],
        ),
        _coverage_row(
            "Heat, waste",
            B3,
            "MJ",
            ["emissions to air", "unspecified"],
            "mapped",
            package="biosphere-4-nomenclature",
            characterised=False,
        ),
        _coverage_row(
            "Acidity, unspecified",
            B5,
            "kg",
            ["emissions to air", "unspecified"],
            "unmapped",
            reason="no_ef_flow",
            detail="no EF 3.1 flow matches by name or CAS",
        ),
    ],
}


def _append_parquet(path: Path, row: dict) -> None:
    df = pd.read_parquet(path)
    extra = pd.DataFrame([row], columns=df.columns)
    for col in df.columns:
        extra[col] = extra[col].astype(df[col].dtype, errors="ignore")
    pd.concat([df, extra], ignore_index=True).to_parquet(path, index=False)


@pytest.fixture
def flow_root(data_root: Path) -> Path:
    vocab = data_root / "sentier-vocab" / "data" / "elementary-flows"
    _append_parquet(
        vocab / "air-01.parquet",
        dict(
            compartment="air",
            sub_compartment=None,
            cas_number=None,
            formula=None,
            iri=FLOWS + E3,
            pref_label="heat, waste",
            source=EF_SOURCE,
        ),
    )
    _append_parquet(
        vocab / "emissions-to-air.parquet",
        dict(
            compartment="emissions to air",
            sub_compartment="unspecified",
            cas_number=None,
            formula=None,
            iri=FLOWS + B5,
            pref_label="Acidity, unspecified",
            source=BAFU_SOURCE,
        ),
    )
    _append_parquet(
        data_root / INVENTORY_FOLDER / "exchanges.parquet",
        dict(
            process_id=P2,
            flow=B5,
            flow_name="Acidity, unspecified",
            flow_type="biosphere",
            direction="output",
            amount=0.1,
            unit="kg",
            location=None,
            uncertainty_type=None,
            loc=None,
            scale=None,
            minimum=None,
            maximum=None,
        ),
    )
    (data_root / BRIDGE_DIR / "coverage.json").write_text(json.dumps(COVERAGE))
    return data_root


# ------------------------------------------------------------------ fixture


def test_fixture_has_four_used_flows_and_the_nomenclature_target(flow_root):
    inv = load_inventory(flow_root)
    bio = inv.exchanges[inv.exchanges["flow_type"] == "biosphere"]
    assert set(bio["flow"]) == {B1, B2, B3, B5}
    assert E3 in set(load_ef_flows(flow_root)["code"])
    assert B5 in set(load_source_flows(flow_root)["code"])
    assert B5 not in load_bridge(flow_root)
