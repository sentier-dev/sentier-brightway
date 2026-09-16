"""Synthetic Sentier data root shaped like the ~/dds checkout."""

from __future__ import annotations

import atexit
import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Point bw2data at a throwaway directory before it can be imported anywhere (a bare
# ``import bw2data`` already opens ``projects.db`` in the default location).
_bw_tmp = tempfile.mkdtemp(prefix="sentier-bw-")
os.environ.setdefault("BRIGHTWAY2_DIR", _bw_tmp)
atexit.register(shutil.rmtree, _bw_tmp, True)

P1 = "11111111-1111-1111-1111-111111111111"
P2 = "22222222-2222-2222-2222-222222222222"
B1 = "b1b1b1b1-0000-5000-8000-000000000001"  # CO2, mapped to E1
B2 = "b2b2b2b2-0000-5000-8000-000000000002"  # U-238 in Bq, mapped to E2 with cf 0.001
# B3: only in the nomenclature package, so it resolves to the residual database by default
B3 = "b3b3b3b3-0000-5000-8000-000000000003"
E1 = "e1e1e1e1-0000-4000-8000-000000000001"
E2 = "e2e2e2e2-0000-4000-8000-000000000002"
E3 = "e3e3e3e3-0000-4000-8000-000000000003"  # EF flow with no factor; nomenclature target of B3
# B4: nomenclature entry onto E1 with a *different* unit (kBq vs kilogram) and no exchange
# rows, so it exercises the bridge unit-conflict warning without touching any score
B4 = "b4b4b4b4-0000-5000-8000-000000000004"
FLOWS = "https://vocab.sentier.dev/flows/"
CLIMATE = "ef-3.1:climate-change"
IONISING = "ef-3.1:ionising-radiation"
P1_CLIMATE_SCORE = 2.0  # 1.0 own CO2 + 2 kWh x 0.5 kg
P1_IONISING_SCORE = 6.0  # 2 kWh x 1000 Bq x 0.001 x 3.0


def _write_inventory(root: Path) -> None:
    sector = root / "sentier-inventory" / "data" / "02-electricity"
    sector.mkdir(parents=True)
    processes = pd.DataFrame(
        {
            "process_id": [P1, P2],
            "name": ["Electricity, low voltage, at grid", "Electricity, medium voltage, at grid"],
            "reference_product": ["Electricity, low voltage", "Electricity, medium voltage"],
            "reference_unit": ["kWh", "kWh"],
            "reference_amount": [1.0, 1.0],
            "location": ["CH", "CH"],
            "process_type": ["unit", "unit"],
            "technology": ["grid", "grid"],
            "comment": ["BAFU category: electricity", "BAFU category: electricity"],
        }
    )
    exchanges = pd.DataFrame(
        [
            # process_id, flow, flow_name, flow_type, direction, amount, unit,
            # location, utype, loc, scale
            (
                P1,
                P1,
                "Electricity, low voltage",
                "production",
                "output",
                1.0,
                "kWh",
                "CH",
                None,
                None,
                None,
            ),
            (
                P1,
                P2,
                "Electricity, medium voltage",
                "technosphere",
                "input",
                2.0,
                "kWh",
                "CH",
                2.0,
                0.6931,
                0.1,
            ),
            (
                P1,
                B1,
                "Carbon dioxide, fossil",
                "biosphere",
                "output",
                1.0,
                "kg",
                None,
                2.0,
                0.0,
                0.1,
            ),
            (P1, B3, "Heat, waste", "biosphere", "output", 5.0, "MJ", None, None, None, None),
            (
                P2,
                P2,
                "Electricity, medium voltage",
                "production",
                "output",
                1.0,
                "kWh",
                "CH",
                None,
                None,
                None,
            ),
            (
                P2,
                B1,
                "Carbon dioxide, fossil",
                "biosphere",
                "output",
                0.5,
                "kg",
                None,
                None,
                None,
                None,
            ),
            (P2, B2, "Uranium-238", "biosphere", "output", 1000.0, "Bq", None, 2.0, 6.9078, 0.2),
            # negative lognormal: BAFU stores loc = ln(|amount|); no CF impact via B3
            (P2, B3, "Heat, waste", "biosphere", "output", -2.0, "MJ", None, 2.0, 0.6931, 0.1),
        ],
        columns=[
            "process_id",
            "flow",
            "flow_name",
            "flow_type",
            "direction",
            "amount",
            "unit",
            "location",
            "uncertainty_type",
            "loc",
            "scale",
        ],
    )
    exchanges["minimum"] = None
    exchanges["maximum"] = None
    # The real minimum/maximum columns are all-null ``string`` dtype (not float64); match that
    # so pd.NA, not float NaN, is what readers and builders actually see.
    exchanges["minimum"] = exchanges["minimum"].astype("string")
    exchanges["maximum"] = exchanges["maximum"].astype("string")
    processes.to_parquet(sector / "processes.parquet", index=False)
    exchanges.to_parquet(sector / "exchanges.parquet", index=False)
    (sector / "metadata.json").write_text(json.dumps({"sector": "electricity", "rank": 2}))


def _vocab_frame(rows: list[dict]) -> pd.DataFrame:
    cols = [
        "compartment",
        "sub_compartment",
        "cas_number",
        "formula",
        "iri",
        "pref_label",
        "source",
    ]
    return pd.DataFrame(rows, columns=cols)


def _write_vocab(root: Path) -> None:
    folder = root / "sentier-vocab" / "data" / "elementary-flows"
    folder.mkdir(parents=True)
    ef = "https://vocab.sentier.dev/sources/ef-3.1"
    bafu = "https://vocab.sentier.dev/sources/bafu-2026"
    _vocab_frame(
        [
            dict(
                compartment="air",
                sub_compartment=None,
                cas_number="124-38-9",
                formula="CO2",
                iri=FLOWS + E1,
                pref_label="carbon dioxide (fossil)",
                source=ef,
            ),
            dict(
                compartment="water",
                sub_compartment=None,
                cas_number=None,
                formula=None,
                iri=FLOWS + E2,
                pref_label="uranium-238",
                source=ef,
            ),
        ]
    ).to_parquet(folder / "air-01.parquet", index=False)
    _vocab_frame(
        [
            dict(
                compartment="emissions to air",
                sub_compartment="unspecified",
                cas_number="124-38-9",
                formula=None,
                iri=FLOWS + B1,
                pref_label="Carbon dioxide, fossil",
                source=bafu,
            ),
            dict(
                compartment="emissions to water",
                sub_compartment="lake",
                cas_number=None,
                formula=None,
                iri=FLOWS + B2,
                pref_label="Uranium-238",
                source=bafu,
            ),
            dict(
                compartment="emissions to air",
                sub_compartment="unspecified",
                cas_number=None,
                formula=None,
                iri=FLOWS + B3,
                pref_label="Heat, waste",
                source=bafu,
            ),
        ]
    ).to_parquet(folder / "emissions-to-air.parquet", index=False)


def _write_methods(root: Path) -> None:
    folder = root / "sentier-methods" / "data" / "01-ef-3.1"
    folder.mkdir(parents=True)
    pd.DataFrame(
        {
            "method_id": [CLIMATE, IONISING],
            "method_name": ["EF v3.1", "EF v3.1"],
            "impact_category": ["Climate change", "Ionising radiation"],
            "unit": ["kg CO2 eq", "kBq U235 eq"],
            "methodology": ["EF", "EF"],
            "source": ["jrc", "jrc"],
            "datasource": ["ef-3.1", "ef-3.1"],
        }
    ).to_parquet(folder / "methods.parquet", index=False)
    pd.DataFrame(
        [
            (
                CLIMATE,
                "Climate change",
                FLOWS + E1,
                "carbon dioxide (fossil)",
                1.0,
                "kg CO2 eq",
                "Emissions / Emissions to air / Emissions to air, unspecified",
                None,
            ),
            (
                CLIMATE,
                "Climate change",
                FLOWS + E1,
                "carbon dioxide (fossil)",
                2.0,
                "kg CO2 eq",
                "Emissions / Emissions to air / Emissions to air, unspecified",
                "DE",
            ),
            (
                IONISING,
                "Ionising radiation",
                FLOWS + E2,
                "uranium-238",
                3.0,
                "kBq U235 eq",
                "Emissions / Emissions to water / Emissions to water, unspecified",
                None,
            ),
        ],
        columns=[
            "method_id",
            "impact_category",
            "flow",
            "flow_name",
            "factor_value",
            "unit",
            "flow_context",
            "location",
        ],
    ).to_parquet(folder / "characterization-factors.parquet", index=False)
    (folder / "metadata.json").write_text(json.dumps({"datasource": "ef-3.1", "rank": 1}))


def _write_bridge(root: Path) -> None:
    folder = root / "sentier-mappings" / "data" / "bafu-2026-v1__ef-3.1"
    folder.mkdir(parents=True)
    package = {
        "name": "bafu-2026-v1__ef-3.1-biosphere-curated",
        "version": "0.5.0",
        "replace": [
            {
                "source": {
                    "name": "Carbon dioxide, fossil",
                    "code": B1,
                    "unit": "kg",
                    "context": ["emissions to air", "unspecified"],
                },
                "target": {
                    "name": "carbon dioxide (fossil)",
                    "code": E1,
                    "unit": "kilogram",
                    "context": ["Emissions", "Emissions to air", "Emissions to air, unspecified"],
                },
            },
            {
                "source": {
                    "name": "Uranium-238",
                    "code": B2,
                    "unit": "Bq",
                    "context": ["emissions to water", "lake"],
                },
                "target": {
                    "name": "uranium-238",
                    "code": E2,
                    "unit": "kBq",
                    "context": [
                        "Emissions",
                        "Emissions to water",
                        "Emissions to water, unspecified",
                    ],
                },
                "conversion_factor": 0.001,
            },
        ],
    }
    (folder / "biosphere-1-curated.json").write_text(json.dumps(package))
    nomenclature = {
        "name": "bafu-2026-v1__ef-3.1-biosphere-nomenclature",
        "version": "0.1.0",
        "replace": [
            {
                "source": {
                    "name": "Heat, waste",
                    "code": B3,
                    "unit": "MJ",
                    "context": ["emissions to air", "unspecified"],
                },
                "target": {
                    "name": "heat, waste",
                    "code": E3,
                    "unit": "megajoule",
                    "context": ["Emissions", "Emissions to air", "Emissions to air, unspecified"],
                },
            },
            {
                "source": {
                    "name": "Carbon dioxide, fossil, activity",
                    "code": B4,
                    "unit": "kBq",
                    "context": ["emissions to air", "unspecified"],
                },
                "target": {
                    "name": "carbon dioxide (fossil)",
                    "code": E1,
                    "unit": "kBq",
                    "context": ["Emissions", "Emissions to air", "Emissions to air, unspecified"],
                },
            },
        ],
    }
    (folder / "biosphere-4-nomenclature.json").write_text(json.dumps(nomenclature))
    (folder / "metadata.json").write_text(
        json.dumps(
            {
                "source": "bafu-2026-v1",
                "target": "ef-3.1",
                "schema_version": "0.2.0",
                "packages": [
                    {
                        "file": "biosphere-1-curated.json",
                        "kind": "biosphere",
                        "order": 1,
                        "entries": 2,
                        "title": "curated",
                    },
                    {
                        "file": "biosphere-4-nomenclature.json",
                        "kind": "biosphere",
                        "order": 4,
                        "entries": 2,
                        "title": "nomenclature",
                    },
                ],
            }
        )
    )


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "dds"
    _write_inventory(root)
    _write_vocab(root)
    _write_methods(root)
    _write_bridge(root)
    return root


@pytest.fixture
def bw_project(tmp_path: Path) -> str:
    """An isolated Brightway base directory under ``tmp_path``; never the user's real one.

    Only tests marked ``bw`` use it; they ``importorskip`` bw2data themselves first."""
    bd = pytest.importorskip("bw2data")
    bd.config.is_test = True  # no tqdm bars
    base = tmp_path / "bw"
    base.mkdir()
    (base / "logs").mkdir()
    name = "sentier-brightway-test"
    kwargs = {"base_dir": base, "base_logs_dir": base / "logs"}
    accepted = inspect.signature(bd.projects.change_base_directories).parameters
    if {"project_name", "update"} <= set(accepted):
        kwargs.update(project_name=name, update=False)
    bd.projects.change_base_directories(**kwargs)
    bd.projects.set_current(name)
    print(f"bw2data project dir: {bd.projects.dir}")
    assert Path(bd.projects.dir).is_relative_to(base)
    return name


BAFU_SHEET = "BAFU_2026 v1"
# fixture references, per MJ for the two electricity processes (ours are per kWh):
REF_P1_CLIMATE_PER_MJ = P1_CLIMATE_SCORE / 3.6
REF_P2_CLIMATE_PER_MJ = 0.5 / 3.6
REF_P1_IONISING_PER_MJ = P1_IONISING_SCORE / 3.6
REF_P2_IONISING_PER_MJ = 3.0 / 3.6
MOJIBAKE_NAME = "WÃƒÂ¤rme, ab Kessel - CH"  # decodes to "Wärme, ab Kessel - CH"


@pytest.fixture
def bafu_xlsx(tmp_path: Path) -> Path:
    """A tiny BAFU 'LCIA Results' workbook: 2 header rows, all 25 EF headers, 3 processes."""
    import openpyxl

    from sentier_brightway.backtest.categories import CATEGORIES

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = BAFU_SHEET
    families = [None, None, None, None, "IPCC 2021", "EF 3.1"] + [None] * 24
    header = ["Product", "Category", "Sub-category", "Unit", "GWP 100 [kg CO2-eq]"] + [
        c.xlsx_header for c in CATEGORIES
    ]
    ws.append(families)
    ws.append(header)
    idx = {c.short: 5 + i for i, c in enumerate(CATEGORIES)}

    def row(product, unit, climate, ionising):
        values = [product, "electricity", "grid", unit, climate] + [None] * 25
        values[idx["climate"]] = climate
        values[idx["radiation"]] = ionising
        values[idx["acid"]] = 0.0  # zero reference -> blank pct
        return values

    ws.append(
        row(
            "Electricity, low voltage, at grid - CH",
            "MJ",
            REF_P1_CLIMATE_PER_MJ,
            REF_P1_IONISING_PER_MJ,
        )
    )
    ws.append(
        row(
            "Electricity, medium voltage, at grid - CH",
            "MJ",
            REF_P2_CLIMATE_PER_MJ,
            REF_P2_IONISING_PER_MJ,
        )
    )
    ws.append(row(MOJIBAKE_NAME, "MJ", 0.1, 0.2))  # not in our data -> unmatched_ref
    path = tmp_path / "bafu_lcia.xlsx"
    wb.save(path)
    return path
