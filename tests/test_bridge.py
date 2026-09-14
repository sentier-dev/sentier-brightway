import json

import pytest

from sentier_brightway.bridge import BridgeEntry, applied_packages, load_bridge
from tests.conftest import B1, B2, B3, E1, E2, E3

FOLDER = "sentier-mappings/data/bafu-2026-v1__ef-3.1"


def _add_package(
    data_root, filename: str, order: int, entries: list[dict], kind="biosphere"
) -> None:
    folder = data_root / FOLDER
    package = {"name": filename, "version": "0", "replace": entries}
    (folder / filename).write_text(json.dumps(package))
    meta = json.loads((folder / "metadata.json").read_text())
    new_item = {
        "file": filename,
        "kind": kind,
        "order": order,
        "entries": len(entries),
    }
    packages = sorted(meta["packages"] + [new_item], key=lambda p: p["order"])
    (folder / "metadata.json").write_text(json.dumps({**meta, "packages": packages}))


def _write_metadata(data_root, packages: list[dict], schema_version: str | None = "0.2.0") -> None:
    meta = {"source": "bafu-2026-v1", "target": "ef-3.1", "packages": packages}
    if schema_version is not None:
        meta["schema_version"] = schema_version
    (data_root / FOLDER / "metadata.json").write_text(json.dumps(meta))


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


# --- item 1: only ``replace`` entries relink -------------------------------------------


def test_update_only_entries_contribute_nothing(data_root):
    folder = data_root / FOLDER
    filename = "biosphere-5-update-only.json"
    package = {
        "name": filename,
        "version": "0",
        "update": [
            {
                "source": {"code": "new", "unit": "kg"},
                "target": {"code": "new", "unit": "kilogram"},
            }
        ],
    }
    (folder / filename).write_text(json.dumps(package))
    meta = json.loads((folder / "metadata.json").read_text())
    new_item = {"file": filename, "kind": "biosphere", "order": 5, "entries": 1}
    meta["packages"] = sorted(meta["packages"] + [new_item], key=lambda p: p["order"])
    (folder / "metadata.json").write_text(json.dumps(meta))
    assert "new" not in load_bridge(data_root)


# --- item 2: validate external data at the boundary -------------------------------------


def test_entry_missing_source_code_is_an_error(data_root):
    _add_package(
        data_root,
        "biosphere-2-bad.json",
        2,
        [{"source": {"unit": "kg"}, "target": {"code": "tgt", "unit": "kilogram"}}],
    )
    with pytest.raises(ValueError, match="missing source.code"):
        load_bridge(data_root)


def test_entry_missing_target_code_is_an_error(data_root):
    _add_package(
        data_root,
        "biosphere-2-bad.json",
        2,
        [{"source": {"code": "new", "unit": "kg"}, "target": {"unit": "kilogram"}}],
    )
    with pytest.raises(ValueError, match="missing target.code"):
        load_bridge(data_root)


def test_null_conversion_factor_defaults_to_one(data_root):
    _add_package(
        data_root,
        "biosphere-2-null-cf.json",
        2,
        [
            {
                "source": {"code": "new", "unit": "kg"},
                "target": {"code": "tgt", "unit": "kilogram"},
                "conversion_factor": None,
            }
        ],
    )
    assert load_bridge(data_root)["new"].conversion_factor == 1.0


def test_package_entry_missing_order_is_an_error(data_root):
    folder = data_root / FOLDER
    meta = json.loads((folder / "metadata.json").read_text())
    meta["packages"].append({"file": "biosphere-1-curated.json", "kind": "biosphere"})
    (folder / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="order"):
        load_bridge(data_root)


def test_package_entry_missing_file_is_an_error(data_root):
    folder = data_root / FOLDER
    meta = json.loads((folder / "metadata.json").read_text())
    meta["packages"].append({"kind": "biosphere", "order": 9})
    (folder / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="file"):
        load_bridge(data_root)


def test_corrupt_metadata_json_is_an_error(data_root):
    (data_root / FOLDER / "metadata.json").write_text("{not json")
    with pytest.raises(ValueError, match="metadata.json"):
        load_bridge(data_root)


def test_corrupt_package_json_is_an_error(data_root):
    (data_root / FOLDER / "biosphere-1-curated.json").write_text("{not json")
    with pytest.raises(ValueError, match="biosphere-1-curated.json"):
        load_bridge(data_root)


# --- item 3: target.location captured but unused for linking ----------------------------


def test_target_location_is_captured_when_present(data_root):
    _add_package(
        data_root,
        "biosphere-2-regional.json",
        2,
        [
            {
                "source": {"code": "new", "unit": "kg"},
                "target": {"code": "tgt", "unit": "kilogram", "location": "AT"},
            }
        ],
    )
    assert load_bridge(data_root)["new"].target_location == "AT"


def test_target_location_defaults_to_none(data_root):
    assert load_bridge(data_root)[B1].target_location is None


# --- item 4: structural errors -----------------------------------------------------------


def test_missing_metadata_json_is_an_error(data_root):
    (data_root / FOLDER / "metadata.json").unlink()
    with pytest.raises(FileNotFoundError):
        load_bridge(data_root)


def test_non_biosphere_kind_is_skipped(data_root):
    _add_package(
        data_root,
        "other-2.json",
        2,
        [{"source": {"code": "new", "unit": "kg"}, "target": {"code": "tgt", "unit": "kilogram"}}],
        kind="technosphere",
    )
    assert "new" not in load_bridge(data_root)


def test_empty_packages_list_is_an_error(data_root):
    _write_metadata(data_root, packages=[])
    with pytest.raises(ValueError, match="no biosphere packages"):
        load_bridge(data_root)


def test_duplicate_file_listing_is_an_error(data_root):
    folder = data_root / FOLDER
    meta = json.loads((folder / "metadata.json").read_text())
    meta["packages"].append(
        {"file": "biosphere-1-curated.json", "kind": "biosphere", "order": 9, "entries": 2}
    )
    (folder / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="biosphere-1-curated.json"):
        load_bridge(data_root)


# --- item 5: schema_version major check ---------------------------------------------------


def test_unsupported_schema_major_version_is_an_error(data_root):
    folder = data_root / FOLDER
    meta = json.loads((folder / "metadata.json").read_text())
    meta["schema_version"] = "1.0.0"
    (folder / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="1.0.0"):
        load_bridge(data_root)


def test_applied_packages_lists_what_load_bridge_applies(data_root):
    assert applied_packages(data_root, include_nomenclature=True) == (
        "biosphere-1-curated.json",
        "biosphere-4-nomenclature.json",
    )
    assert applied_packages(data_root, include_nomenclature=False) == ("biosphere-1-curated.json",)
