import json

import pytest

from sentier_brightway import files
from sentier_brightway.bridge import load_bridge
from sentier_brightway.build import build
from sentier_brightway.constants import BRIDGE_FOLDER, CITATION
from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from sentier_brightway.inventory import load_inventory
from sentier_brightway.methods import load_methods


@pytest.fixture
def result(data_root):
    return build(
        inventory=load_inventory(data_root),
        ef_flows=load_ef_flows(data_root),
        bafu_flows=load_bafu_flows(data_root),
        bridge=load_bridge(data_root),
        methods=load_methods(data_root),
    )


def test_folder_layout(result, data_root, tmp_path):
    out = files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
    assert (out / "registry/processes.parquet").is_file()
    assert (out / "registry/characterization-factors.parquet").is_file()
    assert (out / "mappings/bafu-2026-v1__ef-3.1/metadata.json").is_file()
    assert (out / "mappings/bafu-2026-v1__ef-3.1/biosphere-1-curated.json").is_file()
    assert (out / "bw_package/bafu-2026/datapackage.json").is_file()
    assert (out / "manifest.json").is_file()


def test_manifest_content(result, data_root, tmp_path):
    out = files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["layout_version"] == files.LAYOUT_VERSION
    assert manifest["citation"] == CITATION
    assert manifest["coverage"]["processes"] == 2
    assert manifest["counts"] == {"processes": 2, "biosphere": 3, "exchanges": 8, "methods": 2}
    assert "created" in manifest and "sentier_brightway_version" in manifest
    assert manifest["bridge_folder"] == BRIDGE_FOLDER
    assert manifest["bridge_packages"] == [
        "biosphere-1-curated.json",
        "biosphere-4-nomenclature.json",
    ]
    assert len(manifest["sources"]) == 4
    for source in manifest["sources"]:
        assert set(source) == {"name", "repo", "ref"}


def test_datapackages_can_be_skipped(result, data_root, tmp_path):
    out = files.write_files(
        result, data_root=data_root, out_dir=tmp_path / "out", datapackages=False
    )
    assert not (out / "bw_package").exists()
    assert (out / "registry/processes.parquet").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["datapackages"] is False


def test_refuses_non_empty_out_dir_without_overwrite(result, data_root, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "junk").write_text("x")
    with pytest.raises(files.ExistingOutputError):
        files.write_files(result, data_root=data_root, out_dir=out)
    files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert not (out / "junk").exists()


def test_missing_bridge_folder_raises(result, data_root, tmp_path):
    import shutil

    shutil.rmtree(data_root / "sentier-mappings")
    with pytest.raises(FileNotFoundError):
        files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
