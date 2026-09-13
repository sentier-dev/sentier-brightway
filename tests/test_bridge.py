import json

import pytest

from sentier_brightway.bridge import BridgeEntry, load_bridge
from tests.conftest import B1, B2, B3, E1, E2, E3

FOLDER = "sentier-mappings/data/bafu-2026-v1__ef-3.1"


def _add_package(data_root, filename: str, order: int, entries: list[dict]) -> None:
    folder = data_root / FOLDER
    package = {"name": filename, "version": "0", "replace": entries}
    (folder / filename).write_text(json.dumps(package))
    meta = json.loads((folder / "metadata.json").read_text())
    new_item = {
        "file": filename,
        "kind": "biosphere",
        "order": order,
        "entries": len(entries),
    }
    packages = sorted(meta["packages"] + [new_item], key=lambda p: p["order"])
    (folder / "metadata.json").write_text(json.dumps({**meta, "packages": packages}))


def test_replace_entries_are_keyed_by_source_code(data_root):
    bridge = load_bridge(data_root)
    assert bridge[B1] == BridgeEntry(target_code=E1, target_unit="kilogram", conversion_factor=1.0)
    assert bridge[B2].conversion_factor == 0.001
    assert bridge[B2].target_code == E2


def test_nomenclature_package_included_by_default_and_flagged(data_root):
    bridge = load_bridge(data_root)
    assert bridge[B3].target_code == E3
    assert bridge[B3].nomenclature is True
    assert bridge[B1].nomenclature is False


def test_nomenclature_package_can_be_skipped(data_root):
    assert B3 not in load_bridge(data_root, include_nomenclature=False)


def test_earlier_package_wins_on_duplicate_source(data_root):
    _add_package(
        data_root,
        "biosphere-2-inferred.json",
        2,
        [{"source": {"code": B1, "unit": "kg"}, "target": {"code": "other", "unit": "kilogram"}}],
    )
    assert load_bridge(data_root)[B1].target_code == E1


def test_later_package_adds_new_sources(data_root):
    _add_package(
        data_root,
        "biosphere-3-matched.json",
        3,
        [{"source": {"code": "new", "unit": "kg"}, "target": {"code": "tgt", "unit": "kilogram"}}],
    )
    assert load_bridge(data_root)["new"].target_code == "tgt"


def test_listed_file_missing_is_an_error(data_root):
    (data_root / FOLDER / "biosphere-1-curated.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_bridge(data_root)


def test_no_bridge_folder_is_an_error(tmp_path):
    (tmp_path / "sentier-mappings/data").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_bridge(tmp_path)
