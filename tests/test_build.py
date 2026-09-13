import math

import pytest

from sentier_brightway.bridge import load_bridge
from sentier_brightway.build import BuildResult, build
from sentier_brightway.constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB
from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from sentier_brightway.inventory import load_inventory
from sentier_brightway.methods import load_methods
from tests.conftest import B3, E1, E2, E3, P1, P2


def _build(data_root, include_nomenclature: bool) -> BuildResult:
    return build(
        inventory=load_inventory(data_root),
        ef_flows=load_ef_flows(data_root),
        bafu_flows=load_bafu_flows(data_root),
        bridge=load_bridge(data_root, include_nomenclature=include_nomenclature),
        methods=load_methods(data_root),
    )


@pytest.fixture
def result(data_root) -> BuildResult:
    """Curated package only, so B3 exercises the residual path."""
    return _build(data_root, include_nomenclature=False)


def test_nomenclature_default_relinks_b3_and_empties_residual(data_root):
    full = _build(data_root, include_nomenclature=True)
    assert full.residual == {}
    assert (BIOSPHERE_DB, E3) in full.biosphere
    assert full.biosphere[(BIOSPHERE_DB, E3)]["unit"] == "megajoule"
    by_input = {e["input"]: e for e in full.inventory[(INVENTORY_DB, P1)]["exchanges"]}
    assert by_input[(BIOSPHERE_DB, E3)]["amount"] == 5.0
    assert (full.coverage.flows_mapped, full.coverage.flows_nomenclature) == (3, 1)
    assert full.coverage.residual_by_compartment == ()


def test_biosphere_nodes_cover_vocab_cf_and_bridge_targets(result):
    assert set(result.biosphere) == {(BIOSPHERE_DB, E1), (BIOSPHERE_DB, E2)}
    node = result.biosphere[(BIOSPHERE_DB, E2)]
    assert node["type"] == "emission"
    assert node["unit"] == "kilo Becquerel"  # from the bridge target unit
    assert node["categories"] == (
        "Emissions",
        "Emissions to water",
        "Emissions to water, unspecified",
    )
    assert result.biosphere[(BIOSPHERE_DB, E1)]["unit"] == "kilogram"


def test_residual_holds_only_unmapped_flows_used_in_exchanges(result):
    assert set(result.residual) == {(RESIDUAL_DB, B3)}
    node = result.residual[(RESIDUAL_DB, B3)]
    assert node["name"] == "Heat, waste"
    assert node["categories"] == ("emissions to air", "unspecified")
    assert node["unit"] == "megajoule"


def test_process_node_fields(result):
    p1 = result.inventory[(INVENTORY_DB, P1)]
    assert p1["name"] == "Electricity, low voltage, at grid"
    assert p1["reference product"] == "Electricity, low voltage"
    assert p1["unit"] == "kilowatt hour"
    assert p1["location"] == "CH"
    assert p1["type"] == "process"
    assert p1["production amount"] == 1.0


def test_exchanges_are_relinked_with_conversion_factor(result):
    by_input = {e["input"]: e for e in result.inventory[(INVENTORY_DB, P2)]["exchanges"]}
    assert by_input[(INVENTORY_DB, P2)]["type"] == "production"
    assert by_input[(BIOSPHERE_DB, E1)]["amount"] == 0.5
    u238 = by_input[(BIOSPHERE_DB, E2)]
    assert u238["amount"] == pytest.approx(1.0)  # 1000 Bq * 0.001
    assert u238["unit"] == "kilo Becquerel"
    assert u238["uncertainty type"] == 2
    assert u238["loc"] == pytest.approx(6.9078 + math.log(0.001))
    assert u238["scale"] == pytest.approx(0.2)


def test_technosphere_and_residual_exchanges(result):
    by_input = {e["input"]: e for e in result.inventory[(INVENTORY_DB, P1)]["exchanges"]}
    techno = by_input[(INVENTORY_DB, P2)]
    assert techno["type"] == "technosphere" and techno["amount"] == 2.0
    assert techno["uncertainty type"] == 2 and techno["loc"] == pytest.approx(0.6931)
    residual = by_input[(RESIDUAL_DB, B3)]
    assert residual["type"] == "biosphere" and residual["amount"] == 5.0
    assert "uncertainty type" not in residual


def test_coverage_numbers(result):
    cov = result.coverage
    assert (cov.flows_used, cov.flows_mapped) == (3, 2)
    assert (cov.exchange_rows, cov.exchange_rows_mapped) == (4, 3)
    assert cov.residual_by_compartment == (("emissions to air", 1),)
    assert cov.processes == 2 and cov.methods == 2 and cov.flows_nomenclature == 0


def test_method_cfs_point_at_biosphere_keys(result):
    climate = next(m for m in result.methods if m.key[-1] == "Climate change")
    assert climate.cfs == (((BIOSPHERE_DB, E1), 1.0),)
