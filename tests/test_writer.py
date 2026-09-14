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
