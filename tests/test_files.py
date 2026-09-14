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
    with pytest.raises(files.ExistingOutputError, match=r"\(CLI: --overwrite\)"):
        files.write_files(result, data_root=data_root, out_dir=out)
    assert (out / "junk").is_file()


def test_overwrite_refuses_folder_that_is_not_a_previous_export(result, data_root, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "junk").write_text("x")
    with pytest.raises(files.ExistingOutputError, match="does not look like a previous"):
        files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert (out / "junk").is_file()
    (out / "manifest.json").write_text("not json")  # a manifest that does not parse
    with pytest.raises(files.ExistingOutputError, match="does not look like a previous"):
        files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    (out / "manifest.json").write_text(json.dumps({"something": 1}))  # no layout_version
    with pytest.raises(files.ExistingOutputError, match="does not look like a previous"):
        files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert (out / "junk").is_file()


def test_overwrite_replaces_a_previous_export(result, data_root, tmp_path):
    out = files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
    (out / "stale.txt").write_text("x")
    with pytest.raises(files.ExistingOutputError):
        files.write_files(result, data_root=data_root, out_dir=out)
    files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert not (out / "stale.txt").exists()
    assert (out / "manifest.json").is_file()


def test_refuses_file_as_out_dir(result, data_root, tmp_path):
    out = tmp_path / "out"
    out.write_text("x")
    with pytest.raises(files.ExistingOutputError, match="is a file"):
        files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert out.read_text() == "x"


def test_refuses_symlink_as_out_dir(result, data_root, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    out = tmp_path / "out"
    out.symlink_to(target)
    with pytest.raises(files.ExistingOutputError, match="is a symlink"):
        files.write_files(result, data_root=data_root, out_dir=out, overwrite=True)
    assert out.is_symlink() and target.is_dir()


def test_manifest_records_nomenclature_choice_and_applied_packages(result, data_root, tmp_path):
    out = files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["include_nomenclature"] is True
    assert manifest["bridge_packages"] == [
        "biosphere-1-curated.json",
        "biosphere-4-nomenclature.json",
    ]
    out = files.write_files(
        result, data_root=data_root, out_dir=tmp_path / "out2", include_nomenclature=False
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["include_nomenclature"] is False
    assert manifest["bridge_packages"] == ["biosphere-1-curated.json"]
    # the nomenclature package is still copied verbatim, it just was not applied
    assert (out / "mappings" / BRIDGE_FOLDER / "biosphere-4-nomenclature.json").is_file()


def test_manifest_pin_errors_surface(result, data_root, tmp_path, monkeypatch):
    def boom():
        raise ValueError("bad manifest")

    monkeypatch.setattr(files, "load_packaged_manifest", boom)
    with pytest.raises(ValueError, match="bad manifest"):
        files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")


def test_missing_bridge_folder_raises(result, data_root, tmp_path):
    import shutil

    shutil.rmtree(data_root / "sentier-mappings")
    with pytest.raises(FileNotFoundError):
        files.write_files(result, data_root=data_root, out_dir=tmp_path / "out")
