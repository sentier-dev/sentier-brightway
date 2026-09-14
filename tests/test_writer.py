import logging

import pytest

bd = pytest.importorskip("bw2data")
bc = pytest.importorskip("bw2calc")

from sentier_brightway import writer  # noqa: E402
from sentier_brightway.bridge import load_bridge  # noqa: E402
from sentier_brightway.build import build  # noqa: E402
from sentier_brightway.constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB  # noqa: E402
from sentier_brightway.flows import load_bafu_flows, load_ef_flows  # noqa: E402
from sentier_brightway.inventory import load_inventory  # noqa: E402
from sentier_brightway.methods import load_methods  # noqa: E402
from tests.conftest import B3, P1, P1_CLIMATE_SCORE, P1_IONISING_SCORE  # noqa: E402

pytestmark = pytest.mark.bw

CLIMATE_KEY = ("sentier", "EF v3.1", "Climate change")
IONISING_KEY = ("sentier", "EF v3.1", "Ionising radiation")


@pytest.fixture
def result(data_root):
    """Curated package only: no unit-conflict warning, B3 lands in the residual database."""
    return build(
        inventory=load_inventory(data_root),
        ef_flows=load_ef_flows(data_root),
        bafu_flows=load_bafu_flows(data_root),
        bridge=load_bridge(data_root, include_nomenclature=False),
        methods=load_methods(data_root),
    )


def test_write_creates_three_databases_and_methods(bw_project, result):
    writer.write(result, project=bw_project, overwrite=False)
    assert {INVENTORY_DB, BIOSPHERE_DB, RESIDUAL_DB} <= set(bd.databases)
    assert len(bd.Database(INVENTORY_DB)) == 2
    assert len(bd.Database(RESIDUAL_DB)) == 1
    assert CLIMATE_KEY in bd.methods
    assert IONISING_KEY in bd.methods
    meta = bd.methods[CLIMATE_KEY]
    assert meta["unit"] == "kg CO2 eq"
    assert meta["sentier_method_id"] == "ef-3.1:climate-change"


def test_refusing_to_overwrite_without_flag(bw_project, result):
    writer.write(result, project=bw_project, overwrite=False)
    with pytest.raises(writer.ExistingDatabaseError, match="overwrite=True"):
        writer.write(result, project=bw_project, overwrite=False)
    writer.write(result, project=bw_project, overwrite=True)  # does not raise
    assert len(bd.Database(INVENTORY_DB)) == 2  # replaced, not duplicated


def test_get_node_resolves_process_and_residual_flow(bw_project, result):
    writer.write(result, project=bw_project, overwrite=True)
    assert writer.get_node(INVENTORY_DB, P1)["name"] == "Electricity, low voltage, at grid"
    assert writer.get_node(RESIDUAL_DB, B3)["unit"] == "megajoule"


def test_lca_score_matches_hand_computation(bw_project, result):
    writer.write(result, project=bw_project, overwrite=True)
    act = writer.get_node(INVENTORY_DB, P1)
    score = writer.score(act, CLIMATE_KEY)
    assert score == pytest.approx(P1_CLIMATE_SCORE)  # 1.0 own CO2 + 2 kWh * 0.5 kg from P2
    ion = writer.score(act, IONISING_KEY)
    assert ion == pytest.approx(P1_IONISING_SCORE)  # 2 kWh * (1000 Bq * 0.001 kBq) * 3.0


def _write_foreground(name: str = "fg") -> None:
    """A user database with one activity consuming 1 kWh of P1."""
    bd.Database(name).write(
        {
            (name, "a"): {
                "name": "consumer",
                "unit": "kilowatt hour",
                "type": "process",
                "exchanges": [
                    {"input": (name, "a"), "type": "production", "amount": 1.0},
                    {"input": (INVENTORY_DB, P1), "type": "technosphere", "amount": 1.0},
                ],
            }
        }
    )


def test_overwrite_keeps_dependent_database_scorable(bw_project, result):
    writer.write(result, project=bw_project, overwrite=False)
    _write_foreground()
    assert writer.score(writer.get_node("fg", "a"), CLIMATE_KEY) == pytest.approx(2.0)
    writer.write(result, project=bw_project, overwrite=True)  # node ids change
    assert writer.score(writer.get_node("fg", "a"), CLIMATE_KEY) == pytest.approx(2.0)


def test_partial_failure_error_names_the_recovery_step(bw_project, result, monkeypatch):
    class Boom:
        def __init__(self, name):
            self.name = name

        def write(self, data):
            raise ValueError("disk full")

    monkeypatch.setattr(bd, "Database", Boom)
    with pytest.raises(RuntimeError, match=r"failed part-way \(disk full\).*--overwrite") as info:
        writer.write(result, project=bw_project, overwrite=False)
    assert isinstance(info.value.__cause__, ValueError)
    assert bw_project in str(info.value) and INVENTORY_DB in str(info.value)


def test_score_unknown_method_raises_keyerror(bw_project, result):
    writer.write(result, project=bw_project, overwrite=False)
    act = writer.get_node(INVENTORY_DB, P1)
    with pytest.raises(KeyError, match="not installed in project"):
        writer.score(act, ("sentier", "EF v3.1", "Nope"))


def test_overwrite_refreshes_method_metadata_and_removes_orphans(bw_project, result):
    old = ("sentier", "EF v3.1", "Old")
    bd.Method(old).register(unit="stale")
    bd.Method(CLIMATE_KEY).register(unit="stale")
    bd.Method(("other", "method")).register(unit="theirs")
    writer.write(result, project=bw_project, overwrite=True)
    assert old not in bd.methods  # orphan from an older install
    assert bd.methods[CLIMATE_KEY]["unit"] == "kg CO2 eq"  # metadata refreshed
    assert ("other", "method") in bd.methods  # not ours, untouched


def test_write_logs_project_creation_and_method_progress(bw_project, result, caplog):
    caplog.set_level(logging.INFO, logger="sentier_brightway.writer")
    writer.write(result, project="fresh-project", overwrite=False)
    assert "creating Brightway project 'fresh-project'" in caplog.text
    assert "writing method 1/2" in caplog.text and "writing method 2/2" in caplog.text
    caplog.clear()
    writer.write(result, project="fresh-project", overwrite=True)
    assert "creating Brightway project" not in caplog.text
