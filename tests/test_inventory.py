import json

import pandas as pd
import pytest

from sentier_brightway.inventory import Inventory, load_inventory
from tests.conftest import INVENTORY_FOLDER, P1, P2, inventory_metadata

P3 = "33333333-3333-3333-3333-333333333333"


def _add_source_folder(
    data_root, source, version, processes=None, corrupt=False, sectors=("electricity",)
):
    """Another ``data/<source>-<version>/`` folder; rows default to the fixture's, relabelled."""
    folder = data_root / "sentier-inventory" / "data" / f"{source}-{version}"
    folder.mkdir()
    (folder / "metadata.json").write_text(json.dumps(inventory_metadata(source, version, sectors)))
    if corrupt:
        (folder / "processes.parquet").write_bytes(b"not a parquet file")
        (folder / "exchanges.parquet").write_bytes(b"not a parquet file")
        return folder
    src = data_root / INVENTORY_FOLDER
    proc = processes if processes is not None else pd.read_parquet(src / "processes.parquet")
    proc = proc.assign(source=source, source_version=version)
    proc.to_parquet(folder / "processes.parquet", index=False)
    ex = pd.read_parquet(src / "exchanges.parquet")
    ex[ex["process_id"].isin(proc["process_id"])].to_parquet(
        folder / "exchanges.parquet", index=False
    )
    return folder


def _rewrite_metadata(data_root, **changes):
    meta_path = data_root / INVENTORY_FOLDER / "metadata.json"
    meta = {**json.loads(meta_path.read_text()), **changes}
    meta_path.write_text(json.dumps(meta))


def test_loads_the_source_folder_into_two_frames(data_root):
    inv = load_inventory(data_root)
    assert isinstance(inv, Inventory)
    assert sorted(inv.processes.process_id) == sorted([P1, P2])
    assert len(inv.exchanges) == 8
    assert inv.source == "bafu-2026"
    assert inv.source_version == "v1"
    assert inv.sectors == ("electricity",)


def test_sector_column_is_preserved_for_callers(data_root):
    path = data_root / INVENTORY_FOLDER / "processes.parquet"
    proc = pd.read_parquet(path)
    proc.loc[proc["process_id"] == P2, "sector"] = "obsolete"
    proc.to_parquet(path, index=False)
    _rewrite_metadata(data_root, sectors=["electricity", "obsolete"])
    inv = load_inventory(data_root)
    assert "sector" in inv.processes.columns
    by_id = inv.processes.set_index("process_id")["sector"]
    assert (by_id[P1], by_id[P2]) == ("electricity", "obsolete")
    assert list(inv.processes[inv.processes["sector"] == "electricity"].process_id) == [P1]


def test_sectors_and_version_come_from_metadata(data_root):
    _rewrite_metadata(data_root, sectors=["agriculture", "electricity"], source_version="v1")
    inv = load_inventory(data_root)
    assert inv.sectors == ("agriculture", "electricity")
    assert inv.source_version == "v1"


def test_other_source_folders_are_never_opened(data_root):
    # the other folder's parquet is unreadable on purpose: a successful load proves the
    # file was never opened
    _add_source_folder(data_root, "other-1", "2025", corrupt=True)
    inv = load_inventory(data_root, source="bafu-2026")
    assert sorted(inv.processes.process_id) == sorted([P1, P2])


def test_selects_the_folder_of_the_requested_source(data_root):
    _add_source_folder(data_root, "other-1", "2025")
    other = load_inventory(data_root, source="other-1")
    assert (other.source, other.source_version) == ("other-1", "2025")
    assert set(other.processes["source"]) == {"other-1"}
    assert sorted(other.processes.process_id) == sorted([P1, P2])
    assert len(other.exchanges) == 8


def test_unknown_source_is_an_error_listing_available(data_root):
    _add_source_folder(data_root, "other-1", "2025", corrupt=True)
    with pytest.raises(ValueError, match="source='nope'") as exc_info:
        load_inventory(data_root, source="nope")
    message = str(exc_info.value)
    assert "bafu-2026/v1" in message and "other-1/2025" in message


def test_two_releases_of_one_source_need_a_version(data_root):
    extra = pd.read_parquet(data_root / INVENTORY_FOLDER / "processes.parquet").iloc[[0]]
    _add_source_folder(data_root, "bafu-2026", "v2", processes=extra)
    with pytest.raises(ValueError, match="several") as exc_info:
        load_inventory(data_root)
    message = str(exc_info.value)
    assert "bafu-2026/v1" in message and "bafu-2026/v2" in message
    assert "source_version" in message


def test_version_pin_selects_the_right_folder(data_root):
    extra = pd.read_parquet(data_root / INVENTORY_FOLDER / "processes.parquet").iloc[[0]]
    _add_source_folder(data_root, "bafu-2026", "v2", processes=extra)
    v1 = load_inventory(data_root, source_version="v1")
    v2 = load_inventory(data_root, source_version="v2")
    assert (v1.source_version, len(v1.processes)) == ("v1", 2)
    assert (v2.source_version, len(v2.processes)) == ("v2", 1)
    assert set(v2.processes["source_version"]) == {"v2"}


def test_unknown_version_is_an_error_listing_available(data_root):
    with pytest.raises(ValueError, match="source_version='v9'") as exc_info:
        load_inventory(data_root, source_version="v9")
    assert "bafu-2026/v1" in str(exc_info.value)


def test_rows_of_another_source_in_the_folder_are_dropped(data_root):
    # metadata says bafu-2026; a stray other-1 row contradicts it and is not materialised
    path = data_root / INVENTORY_FOLDER / "processes.parquet"
    proc = pd.read_parquet(path)
    proc.loc[proc["process_id"] == P2, ["source", "source_version"]] = ["other-1", "2025"]
    proc.to_parquet(path, index=False)
    inv = load_inventory(data_root)
    assert list(inv.processes.process_id) == [P1]
    assert set(inv.exchanges.process_id) == {P1}
    assert inv.source_version == "v1"


def test_sector_metadata_without_source_key_is_an_error(data_root):
    # 0.2.0 sector-folder metadata: refuse rather than fall back to opening the parquet
    meta_path = data_root / INVENTORY_FOLDER / "metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "sector": "electricity",
                "rank": 2,
                "schema_version": "0.2.0",
                "sources": ["bafu-2026"],
            }
        )
    )
    with pytest.raises(ValueError, match="0.3.0") as exc_info:
        load_inventory(data_root)
    assert "bafu-2026-v1" in str(exc_info.value)


def test_metadata_without_sectors_list_is_an_error(data_root):
    meta_path = data_root / INVENTORY_FOLDER / "metadata.json"
    meta = json.loads(meta_path.read_text())
    del meta["sectors"]
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="sectors"):
        load_inventory(data_root)


def test_folder_without_metadata_is_an_error(data_root):
    (data_root / INVENTORY_FOLDER / "metadata.json").unlink()
    with pytest.raises(FileNotFoundError, match="metadata.json"):
        load_inventory(data_root)


@pytest.mark.parametrize("column", ["source", "sector", "source_version", "reference_product"])
def test_missing_required_column_is_an_error(data_root, column):
    path = data_root / INVENTORY_FOLDER / "processes.parquet"
    pd.read_parquet(path).drop(columns=[column]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match=column):
        load_inventory(data_root)


def test_no_source_folders_is_an_error(tmp_path):
    (tmp_path / "sentier-inventory" / "data").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="source folders"):
        load_inventory(tmp_path)


def test_missing_data_folder_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="source folders"):
        load_inventory(tmp_path)


def test_missing_exchanges_file_is_an_error(data_root):
    (data_root / INVENTORY_FOLDER / "exchanges.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="no exchanges.parquet") as exc_info:
        load_inventory(data_root)
    assert "bafu-2026-v1" in str(exc_info.value)


def test_uncertainty_columns_are_float64_when_absent(data_root):
    path = data_root / INVENTORY_FOLDER / "exchanges.parquet"
    dropped = ["uncertainty_type", "loc", "scale", "minimum", "maximum"]
    pd.read_parquet(path).drop(columns=dropped).to_parquet(path, index=False)
    inv = load_inventory(data_root)
    for column in dropped:
        assert column in inv.exchanges.columns
        assert inv.exchanges[column].isna().all()
        assert inv.exchanges[column].dtype == "float64"
