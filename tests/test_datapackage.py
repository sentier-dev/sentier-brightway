import json

import numpy as np
import pandas as pd
import pytest

from sentier_brightway import datapackage as dpk
from sentier_brightway.bridge import load_bridge
from sentier_brightway.build import build
from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from sentier_brightway.inventory import load_inventory
from sentier_brightway.methods import load_methods
from sentier_brightway.registry import Registry, build_registry, write_registry
from tests.conftest import CLIMATE, IONISING, P1, P1_CLIMATE_SCORE, P1_IONISING_SCORE


@pytest.fixture
def registry(data_root):
    result = build(
        inventory=load_inventory(data_root),
        ef_flows=load_ef_flows(data_root),
        bafu_flows=load_bafu_flows(data_root),
        bridge=load_bridge(data_root),
        methods=load_methods(data_root),
    )
    return build_registry(result)


@pytest.fixture
def out_dir(registry, tmp_path):
    write_registry(registry, tmp_path / "registry")
    dpk.write_datapackages(registry, tmp_path / "bw_package")
    return tmp_path


def test_method_slug():
    assert dpk.method_slug("ef-3.1:climate-change") == "ef-3.1__climate-change"
    assert dpk.method_slug("a b/c") == "a_b_c"


def test_layout_and_slugs(out_dir):
    assert (out_dir / "bw_package/bafu-2026/datapackage.json").is_file()
    assert (out_dir / "bw_package/methods/ef-3.1__climate-change/datapackage.json").is_file()
    assert (out_dir / "bw_package/methods/ef-3.1__ionising-radiation/datapackage.json").is_file()
    meta = json.loads((out_dir / "bw_package/bafu-2026/datapackage.json").read_text())
    matrices = {r["matrix"] for r in meta["resources"] if "matrix" in r}
    assert matrices == {"technosphere_matrix", "biosphere_matrix"}


def test_write_returns_paths(registry, tmp_path):
    paths = dpk.write_datapackages(registry, tmp_path / "bw_package")
    assert paths.inventory == tmp_path / "bw_package" / "bafu-2026"
    assert set(paths.methods) == {CLIMATE, IONISING}
    assert paths.methods[CLIMATE] == tmp_path / "bw_package" / "methods" / "ef-3.1__climate-change"


def test_inputs_are_flipped_production_is_not(out_dir):
    inv = dpk.load_inventory_datapackage(out_dir)
    flip_res = [
        r for r in inv.resources if r["matrix"] == "technosphere_matrix" and r["kind"] == "flip"
    ]
    assert len(flip_res) == 1
    flip, _ = inv.get_resource(flip_res[0]["name"])
    assert flip.dtype == bool
    assert len(flip) == 3  # P1 production, P1 <- P2, P2 production
    assert flip.sum() == 1  # only the technosphere input P1 <- P2
    # bw_processing drops an all-False flip vector: no flip resource means nothing flipped
    bio = [r for r in inv.resources if r["matrix"] == "biosphere_matrix"]
    assert {r["kind"] for r in bio} == {"indices", "data"}
    assert all(r["nrows"] == 5 for r in bio)


def test_characterization_rows_are_diagonal(out_dir):
    method = dpk.load_method_datapackage(out_dir, CLIMATE)
    idx_res = next(r for r in method.resources if r["kind"] == "indices")
    indices, _ = method.get_resource(idx_res["name"])
    assert idx_res["matrix"] == "characterization_matrix"
    assert len(indices) == 1  # curated CF only: DE-specific row dropped upstream
    assert (indices["row"] == indices["col"]).all()


@pytest.mark.bw
def test_score_matches_db_mode(out_dir):
    pytest.importorskip("bw2calc")
    assert dpk.score(out_dir, P1, CLIMATE) == pytest.approx(P1_CLIMATE_SCORE)
    assert dpk.score(out_dir, P1, IONISING) == pytest.approx(P1_IONISING_SCORE)


@pytest.mark.bw
def test_unknown_process_or_method_is_an_error(out_dir):
    pytest.importorskip("bw2calc")
    with pytest.raises(KeyError, match="not-a-code"):
        dpk.score(out_dir, "not-a-code", CLIMATE)
    with pytest.raises(KeyError, match="ef-3.1:nope"):
        dpk.score(out_dir, P1, "ef-3.1:nope")


def _with_exchanges(registry: Registry, exchanges: pd.DataFrame) -> Registry:
    return Registry(
        processes=registry.processes,
        biosphere=registry.biosphere,
        exchanges=exchanges,
        methods=registry.methods,
        characterization_factors=registry.characterization_factors,
    )


def test_dangling_exchange_id_is_an_error(registry, tmp_path):
    bad = registry.exchanges.copy()
    bad.loc[bad.index[0], "input_bw_id"] = 9999
    with pytest.raises(ValueError, match="9999"):
        dpk.write_datapackages(_with_exchanges(registry, bad), tmp_path / "bw_package")
    bad = registry.exchanges.copy()
    bad.loc[bad.index[0], "process_bw_id"] = 8888
    with pytest.raises(ValueError, match="8888"):
        dpk.write_datapackages(_with_exchanges(registry, bad), tmp_path / "bw_package")


def test_method_without_factors_is_an_error(registry, tmp_path):
    cfs = registry.characterization_factors
    trimmed = Registry(
        processes=registry.processes,
        biosphere=registry.biosphere,
        exchanges=registry.exchanges,
        methods=registry.methods,
        characterization_factors=cfs[cfs["method_id"] != IONISING],
    )
    with pytest.raises(ValueError, match=IONISING):
        dpk.write_datapackages(trimmed, tmp_path / "bw_package")


def test_amounts_are_float64(out_dir):
    inv = dpk.load_inventory_datapackage(out_dir)
    for res in inv.resources:
        if res["kind"] == "data":
            data, _ = inv.get_resource(res["name"])
            assert data.dtype == np.float64
