import pandas as pd
import pytest

from sentier_brightway.bridge import load_bridge
from sentier_brightway.build import build
from sentier_brightway.constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB
from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from sentier_brightway.inventory import load_inventory
from sentier_brightway.methods import load_methods
from sentier_brightway.registry import Registry, build_registry, load_registry, write_registry
from tests.conftest import B3, E1, P1, P2


@pytest.fixture
def registry(data_root) -> Registry:
    result = build(
        inventory=load_inventory(data_root),
        ef_flows=load_ef_flows(data_root),
        bafu_flows=load_bafu_flows(data_root),
        bridge=load_bridge(data_root, include_nomenclature=False),
        methods=load_methods(data_root),
    )
    return build_registry(result)


def test_ids_are_contiguous_processes_first(registry):
    assert sorted(registry.processes.bw_id) == [1, 2]
    bio_ids = sorted(registry.biosphere.bw_id)
    assert bio_ids == [3, 4, 5]  # E1, E2 in ef-3.1-biosphere, B3 in residual
    assert set(registry.biosphere.database) == {BIOSPHERE_DB, RESIDUAL_DB}
    assert registry.processes.set_index("code").loc[P1, "database"] == INVENTORY_DB


def test_exchanges_reference_ids_and_keep_types(registry):
    ex = registry.exchanges
    assert len(ex) == 8
    p1 = registry.processes.set_index("code").loc[P1, "bw_id"]
    p2 = registry.processes.set_index("code").loc[P2, "bw_id"]
    mine = ex[ex.process_bw_id == p1]
    assert set(mine.type) == {"production", "technosphere", "biosphere"}
    assert mine[mine.type == "technosphere"].input_bw_id.iloc[0] == p2
    residual = mine[mine.input_code == B3].iloc[0]
    assert residual.input_database == RESIDUAL_DB and residual.amount == 5.0


def test_methods_and_cfs_point_at_biosphere_ids(registry):
    assert set(registry.methods.method_id) == {
        "ef-3.1:climate-change",
        "ef-3.1:ionising-radiation",
    }
    assert registry.methods.set_index("method_id").loc["ef-3.1:climate-change", "method_key"] == (
        "sentier|EF v3.1|Climate change"
    )
    cf = registry.characterization_factors
    e1 = registry.biosphere.set_index("code").loc[E1, "bw_id"]
    row = cf[(cf.method_id == "ef-3.1:climate-change") & (cf.flow_bw_id == e1)].iloc[0]
    assert row.factor == 1.0 and row.flow_database == BIOSPHERE_DB


def test_write_and_load_round_trip(registry, tmp_path):
    write_registry(registry, tmp_path / "registry")
    loaded = load_registry(tmp_path / "registry")
    for name in ("processes", "biosphere", "exchanges", "methods", "characterization_factors"):
        pd.testing.assert_frame_equal(
            getattr(registry, name).reset_index(drop=True),
            getattr(loaded, name).reset_index(drop=True),
        )


def test_categories_are_joined_with_double_colon(registry):
    assert (
        registry.biosphere.set_index("code").loc[B3, "categories"]
        == "emissions to air::unspecified"
    )


def test_exchange_dtypes_are_fixed_regardless_of_content(registry):
    ex = registry.exchanges
    for col in ("loc", "scale", "minimum", "maximum", "amount"):
        assert ex[col].dtype == "float64"
    assert str(ex["uncertainty_type"].dtype) == "Int64"
    assert str(ex["negative"].dtype) == "boolean"


def test_negative_flag_marks_only_the_negative_row(registry, tmp_path):
    write_registry(registry, tmp_path / "registry")
    loaded = load_registry(tmp_path / "registry")
    ex = loaded.exchanges
    p2 = loaded.processes.set_index("code").loc[P2, "bw_id"]
    negative_rows = ex[ex.negative.fillna(False)]
    assert len(negative_rows) == 1
    row = negative_rows.iloc[0]
    assert row.process_bw_id == p2 and row.input_code == B3 and row.amount == -2.0
    assert ex.negative.isna().sum() == len(ex) - 1


def test_biosphere_type_is_emission_or_natural_resource(registry):
    assert set(registry.biosphere.type) <= {"emission", "natural resource"}


def test_load_registry_missing_column_raises(registry, tmp_path):
    folder = tmp_path / "registry"
    write_registry(registry, folder)
    path = folder / "processes.parquet"
    pd.read_parquet(path).drop(columns=["production_amount"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="processes.parquet"):
        load_registry(folder)


def test_load_registry_missing_table_raises(registry, tmp_path):
    folder = tmp_path / "registry"
    write_registry(registry, folder)
    (folder / "biosphere.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        load_registry(folder)
