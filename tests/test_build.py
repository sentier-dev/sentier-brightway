import math
import warnings

import pytest

from sentier_brightway.bridge import load_bridge
from sentier_brightway.build import BuildResult, _node_type, _uncertainty, build, build_inventory
from sentier_brightway.constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB
from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from sentier_brightway.inventory import Inventory, load_inventory
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
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the curated package alone has no unit conflicts
        return _build(data_root, include_nomenclature=False)


def test_nomenclature_default_relinks_b3_and_empties_residual(data_root):
    with pytest.warns(UserWarning, match="1 EF flows are targeted with conflicting units"):
        full = _build(data_root, include_nomenclature=True)
    assert full.coverage.unit_conflicts == 1
    assert full.biosphere[(BIOSPHERE_DB, E1)]["unit"] == "kilogram"  # first package wins
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
    assert result.biosphere[(BIOSPHERE_DB, E1)]["type"] == "emission"
    assert result.biosphere[(BIOSPHERE_DB, E1)]["CAS number"] == "124-38-9"
    assert "CAS number" not in node
    assert result.coverage.unit_conflicts == 0


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
    assert "negative" not in residual


def test_negative_lognormal_is_flagged_with_loc_as_stored(result):
    by_input = {e["input"]: e for e in result.inventory[(INVENTORY_DB, P2)]["exchanges"]}
    heat = by_input[(RESIDUAL_DB, B3)]
    assert heat["amount"] == -2.0 and heat["negative"] is True
    assert heat["loc"] == pytest.approx(0.6931)  # ln(|amount|), untouched
    assert "negative" not in by_input[(BIOSPHERE_DB, E2)]  # positive lognormal


def test_coverage_numbers(result):
    cov = result.coverage
    assert (cov.flows_used, cov.flows_mapped) == (3, 2)
    assert (cov.exchange_rows, cov.exchange_rows_mapped) == (5, 3)
    assert cov.residual_by_compartment == (("emissions to air", 1),)
    assert cov.processes == 2 and cov.methods == 2 and cov.flows_nomenclature == 0


def test_method_cfs_point_at_biosphere_keys(result):
    climate = next(m for m in result.methods if m.key[-1] == "Climate change")
    assert climate.cfs == (((BIOSPHERE_DB, E1), 1.0),)


# --- uncertainty helper --------------------------------------------------------------------


def test_uncertainty_lognormal_factor_one_keeps_loc():
    out = _uncertainty(2.0, 0.5, 0.1, None, None, factor=1.0, amount=1.6487)
    assert out == {"uncertainty type": 2, "loc": 0.5, "scale": 0.1}


def test_uncertainty_lognormal_factor_shifts_loc_only():
    out = _uncertainty(2.0, 6.9078, 0.2, None, None, factor=0.001, amount=1.0)
    assert out["loc"] == pytest.approx(6.9078 + math.log(0.001))
    assert out["scale"] == 0.2 and "minimum" not in out and "maximum" not in out


def test_uncertainty_normal_scales_all_fields():
    out = _uncertainty(3.0, 10.0, 2.0, 5.0, 15.0, factor=0.5, amount=5.0)
    assert out == {"uncertainty type": 3, "loc": 5.0, "scale": 1.0, "minimum": 2.5, "maximum": 7.5}


def test_uncertainty_negative_flag_only_for_positive_only_distributions():
    assert _uncertainty(2.0, 0.0, 0.1, None, None, factor=1.0, amount=-1.0)["negative"] is True
    assert "negative" not in _uncertainty(3.0, -1.0, 0.1, None, None, factor=1.0, amount=-1.0)
    assert _uncertainty(None, None, None, None, None, factor=1.0, amount=-1.0) == {}


# --- node type -----------------------------------------------------------------------------


def test_node_type_from_first_category():
    assert _node_type(("Resources", "in ground")) == "natural resource"
    assert _node_type(("natural resource", "in ground")) == "natural resource"
    assert _node_type(("Raw materials",)) == "natural resource"
    assert _node_type(("Emissions", "Emissions to air")) == "emission"
    assert _node_type(()) == "emission"


def test_node_type_land_use_is_natural_resource():
    assert _node_type(("Land use", "...")) == "natural resource"


# --- fail fast and optional fields (frames edited in-test) ---------------------------------


def _inventory(data_root) -> Inventory:
    from sentier_brightway.inventory import load_inventory

    return load_inventory(data_root)


def test_dangling_technosphere_link_is_an_error(data_root):
    inv = _inventory(data_root)
    ex = inv.exchanges.copy()
    ex.loc[ex["flow_type"] == "technosphere", "flow"] = "ghost-process"
    with pytest.raises(ValueError, match="ghost-process") as exc_info:
        build_inventory(Inventory(inv.processes, ex), {})
    assert P1 in str(exc_info.value)


def test_process_without_production_exchange_is_an_error(data_root):
    inv = _inventory(data_root)
    ex = inv.exchanges[
        ~((inv.exchanges["process_id"] == P2) & (inv.exchanges["flow_type"] == "production"))
    ]
    with pytest.raises(ValueError, match=P2):
        build_inventory(Inventory(inv.processes, ex), {})


def test_process_without_any_exchanges_gets_an_empty_list(data_root):
    inv = _inventory(data_root)
    ex = inv.exchanges[inv.exchanges["process_id"] != P2]
    nodes = build_inventory(Inventory(inv.processes, ex), {})
    assert nodes[(INVENTORY_DB, P2)]["exchanges"] == []


def test_process_without_comment_column_has_no_comment_key(data_root):
    inv = _inventory(data_root)
    nodes = build_inventory(Inventory(inv.processes.drop(columns=["comment"]), inv.exchanges), {})
    assert "comment" not in nodes[(INVENTORY_DB, P1)]
    assert "comment" in build_inventory(inv, {})[(INVENTORY_DB, P1)]
