"""Tests for sentier_brightway.flow_lists: the FOODTURE xlsx of BAFU flows as they land
in Brightway. The ``flow_root`` fixture extends the shared synthetic data root with one
unmapped used flow (B5), the nomenclature target E3 in the EF vocab, and a coverage.json."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from sentier_brightway import flow_lists as fl
from sentier_brightway.bridge import load_bridge
from sentier_brightway.flows import load_ef_flows, load_source_flows
from sentier_brightway.inventory import Inventory, load_inventory
from sentier_brightway.methods import load_methods
from tests.conftest import B1, B2, B3, CLIMATE, E1, E2, E3, FLOWS, INVENTORY_FOLDER, IONISING, P2

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


# ------------------------------------------------------------------ load_coverage


def test_load_coverage_flattens_rows_and_shortens_package(flow_root):
    cov = fl.load_coverage(flow_root)
    assert list(cov.columns) == list(fl.COVERAGE_COLUMNS)
    assert len(cov) == 4
    by = cov.set_index("bafu_code")
    assert by.loc[B1, "package"] == "curated"
    assert by.loc[B3, "package"] == "nomenclature"
    assert by.loc[B5, "package"] == ""
    assert by.loc[B5, "status"] == "unmapped"
    assert by.loc[B5, "reason"] == "no_ef_flow"
    assert by.loc[B2, "bafu_sub_compartment"] == "lake"
    assert by.loc[B2, "caveats"] == "unit converted Bq to kBq"
    assert by.loc[B1, "tier"] == "1"
    assert by.loc[B1, "caveats"] == ""


def test_load_coverage_rejects_unknown_status(flow_root):
    path = flow_root / BRIDGE_DIR / "coverage.json"
    body = json.loads(path.read_text())
    body["coverage"][0]["status"] = "maybe"
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="maybe"):
        fl.load_coverage(flow_root)


def test_load_coverage_rejects_missing_source_code(flow_root):
    path = flow_root / BRIDGE_DIR / "coverage.json"
    body = json.loads(path.read_text())
    del body["coverage"][1]["source"]["code"]
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="coverage.json"):
        fl.load_coverage(flow_root)


def test_load_coverage_missing_file_names_the_path(data_root):
    with pytest.raises(FileNotFoundError, match="coverage.json"):
        fl.load_coverage(data_root)


# ------------------------------------------------------------------ EF side


def test_ef_flow_table_prefers_cf_context_and_falls_back_to_methods(flow_root):
    table = fl.ef_flow_table(load_ef_flows(flow_root), load_methods(flow_root))
    by = table.set_index("code")
    assert by.loc[E1, "name"] == "carbon dioxide (fossil)"
    assert by.loc[E1, "context"] == "Emissions / Emissions to air / Emissions to air, unspecified"
    assert by.loc[E1, "cas"] == "124-38-9"
    assert by.loc[E3, "context"] == "air"  # vocab only: no CF row for E3
    assert by.loc[E3, "cas"] == ""


def test_ef_flow_table_includes_cf_only_flows(flow_root):
    ef = load_ef_flows(flow_root)
    ef = ef[ef["code"] != E2]  # pretend vocab lacks E2; the methods table still knows it
    by = fl.ef_flow_table(ef, load_methods(flow_root)).set_index("code")
    assert by.loc[E2, "name"] == "uranium-238"
    assert by.loc[E2, "context"].startswith("Emissions / Emissions to water")


def test_methods_per_flow_counts_only_global_factors(flow_root):
    per = fl.methods_per_flow(load_methods(flow_root))
    assert per[E1] == (CLIMATE,)
    assert per[E2] == (IONISING,)
    assert E3 not in per


# ------------------------------------------------------------------ bafu_to_ef


def _inputs(root: Path) -> dict:
    inv = load_inventory(root)
    methods = load_methods(root)
    return dict(
        coverage=fl.load_coverage(root),
        bridge=load_bridge(root),
        ef_table=fl.ef_flow_table(load_ef_flows(root), methods),
        bafu_flows=load_source_flows(root),
        exchanges=inv.exchanges,
        methods=methods,
        source=inv.source,
    )


def test_bafu_to_ef_one_row_per_coverage_row_with_ef_fields(flow_root):
    df = fl.build_bafu_to_ef(**_inputs(flow_root))
    assert list(df.columns) == list(fl.BAFU_TO_EF_COLUMNS)
    assert len(df) == 4 and df["bafu_code"].is_unique
    by = df.set_index("bafu_code")
    b1 = by.loc[B1]
    assert b1["ef_uuid"] == E1 and b1["ef_name"] == "carbon dioxide (fossil)"
    assert b1["ef_unit"] == "kilogram" and b1["conversion_factor"] == 1.0
    assert b1["ef_context"] == "Emissions / Emissions to air / Emissions to air, unspecified"
    assert b1["ef_cas"] == "124-38-9" and b1["bafu_cas"] == "124-38-9"
    assert b1["exchange_count"] == 2
    assert b1["ef_methods_with_factor"] == 1
    assert b1["brightway_database"] == "ef-3.1-biosphere" and b1["brightway_code"] == E1
    assert by.loc[B2, "conversion_factor"] == 0.001
    assert by.loc[B2, "bafu_cas"] == ""


def test_bafu_to_ef_nomenclature_row_has_zero_methods(flow_root):
    by = fl.build_bafu_to_ef(**_inputs(flow_root)).set_index("bafu_code")
    assert by.loc[B3, "package"] == "nomenclature"
    assert by.loc[B3, "ef_uuid"] == E3 and by.loc[B3, "ef_methods_with_factor"] == 0
    assert by.loc[B3, "exchange_count"] == 2


def test_bafu_to_ef_unmapped_row_goes_to_residual(flow_root):
    by = fl.build_bafu_to_ef(**_inputs(flow_root)).set_index("bafu_code")
    b5 = by.loc[B5]
    assert b5["status"] == "unmapped" and b5["ef_uuid"] == "" and b5["ef_name"] == ""
    assert b5["ef_methods_with_factor"] == 0
    assert b5["brightway_database"] == "bafu-2026-residual" and b5["brightway_code"] == B5
    assert b5["reason"] == "no_ef_flow" and b5["exchange_count"] == 1


def test_bafu_to_ef_sorted_by_compartment_then_name(flow_root):
    df = fl.build_bafu_to_ef(**_inputs(flow_root))
    keys = list(zip(df["bafu_compartment"], df["bafu_sub_compartment"], df["bafu_name"]))
    assert keys == sorted(keys)


def test_bafu_to_ef_rejects_mapped_row_missing_from_bridge(flow_root):
    kw = _inputs(flow_root)
    kw["bridge"] = {k: v for k, v in kw["bridge"].items() if k != B2}
    with pytest.raises(ValueError, match=B2):
        fl.build_bafu_to_ef(**kw)


def test_bafu_to_ef_rejects_unmapped_row_present_in_bridge(flow_root):
    kw = _inputs(flow_root)
    kw["coverage"].loc[kw["coverage"]["bafu_code"] == B2, "status"] = "unmapped"
    with pytest.raises(ValueError, match=B2):
        fl.build_bafu_to_ef(**kw)


def test_bafu_to_ef_rejects_coverage_set_different_from_used_flows(flow_root):
    kw = _inputs(flow_root)
    kw["coverage"] = kw["coverage"][kw["coverage"]["bafu_code"] != B5]
    with pytest.raises(ValueError, match=B5):
        fl.build_bafu_to_ef(**kw)


def test_bafu_to_ef_rejects_target_unknown_to_ef_table(flow_root):
    kw = _inputs(flow_root)
    kw["ef_table"] = kw["ef_table"][kw["ef_table"]["code"] != E3]
    with pytest.raises(ValueError, match=E3):
        fl.build_bafu_to_ef(**kw)


def test_bafu_to_ef_rejects_duplicate_coverage_code(flow_root):
    kw = _inputs(flow_root)
    kw["coverage"] = pd.concat([kw["coverage"], kw["coverage"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        fl.build_bafu_to_ef(**kw)


# ------------------------------------------------------------------ ef_flows, processes


def test_ef_flows_distinct_targets_with_counts_and_methods(flow_root):
    kw = _inputs(flow_root)
    b2e = fl.build_bafu_to_ef(**kw)
    df = fl.build_ef_flows(b2e, kw["bridge"], kw["methods"])
    assert list(df.columns) == list(fl.EF_FLOWS_COLUMNS)
    assert sorted(df["ef_uuid"]) == sorted([E1, E2, E3]) and df["ef_uuid"].is_unique
    by = df.set_index("ef_uuid")
    assert by.loc[E1, "bafu_source_count"] == 1  # B4 is in the bridge but unused
    assert by.loc[E1, "exchange_count"] == 2
    assert by.loc[E1, "ef_unit"] == "kilogram"  # first bridge unit wins, like the build
    assert by.loc[E1, "ef_methods"] == CLIMATE and by.loc[E1, "ef_methods_with_factor"] == 1
    assert by.loc[E3, "ef_methods"] == "" and by.loc[E3, "ef_methods_with_factor"] == 0
    keys = list(zip(df["ef_context"], df["ef_name"]))
    assert keys == sorted(keys)


def test_processes_sheet(flow_root):
    df = fl.build_processes(load_inventory(flow_root))
    assert list(df.columns) == list(fl.PROCESS_COLUMNS)
    assert len(df) == 2 and df["code"].is_unique
    assert set(df["brightway_database"]) == {"bafu-2026"}
    assert df.iloc[0]["name"] == "Electricity, low voltage, at grid"
    assert df.iloc[0]["unit"] == "kWh" and df.iloc[0]["sector"] == "electricity"


def test_processes_rejects_duplicate_code(flow_root):
    inv = load_inventory(flow_root)
    dup = pd.concat([inv.processes, inv.processes.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        fl.build_processes(Inventory(processes=dup, exchanges=inv.exchanges, source=inv.source))


# ------------------------------------------------------------------ provenance


def _git(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "HOME": str(cwd),
        "PATH": "/usr/bin:/bin",
    }
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def test_repo_pins_sha_dirty_and_unknown(tmp_path):
    root = tmp_path / "dds"
    for repo in ("sentier-inventory", "sentier-vocab", "sentier-methods"):
        d = root / repo
        d.mkdir(parents=True)
        _git(d, "init", "-q")
        (d / "f").write_text("x")
        _git(d, "add", "f")
        _git(d, "commit", "-q", "-m", "init")
    (root / "sentier-vocab" / "f").write_text("changed")  # dirty tree
    (root / "sentier-mappings").mkdir()  # not a git repo
    pins = {p.repo: p for p in fl.repo_pins(root)}
    assert list(pins) == [
        "sentier-inventory",
        "sentier-vocab",
        "sentier-methods",
        "sentier-mappings",
    ]
    assert pins["sentier-inventory"].sha == _git(root / "sentier-inventory", "rev-parse", "HEAD")
    assert pins["sentier-inventory"].dirty is False
    assert pins["sentier-vocab"].dirty is True
    assert pins["sentier-vocab"].label.endswith("+dirty")
    assert pins["sentier-mappings"].sha == "unknown" and pins["sentier-mappings"].dirty is False
