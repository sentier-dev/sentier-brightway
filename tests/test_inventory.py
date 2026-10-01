import json

import pandas as pd
import pytest

from sentier_brightway.inventory import Inventory, load_inventory
from tests.conftest import P1, P2

SECTOR = "sentier-inventory/data/02-electricity"


def _add_sector(data_root, name, sources, processes=None, corrupt=False):
    """A second sector folder; ``processes`` rows default to a copy of the fixture's."""
    folder = data_root / "sentier-inventory" / "data" / name
    folder.mkdir()
    (folder / "metadata.json").write_text(
        json.dumps({"sector": name.split("-", 1)[1], "rank": 9, "sources": sources})
    )
    if corrupt:
        (folder / "processes.parquet").write_bytes(b"not a parquet file")
        (folder / "exchanges.parquet").write_bytes(b"not a parquet file")
        return folder
    src = data_root / SECTOR
    proc = processes if processes is not None else pd.read_parquet(src / "processes.parquet")
    proc.to_parquet(folder / "processes.parquet", index=False)
    ex = pd.read_parquet(src / "exchanges.parquet")
    ex[ex["process_id"].isin(proc["process_id"])].to_parquet(
        folder / "exchanges.parquet", index=False
    )
    return folder


def test_loads_all_sectors_into_two_frames(data_root):
    inv = load_inventory(data_root)
    assert isinstance(inv, Inventory)
    assert sorted(inv.processes.process_id) == sorted([P1, P2])
    assert len(inv.exchanges) == 8
    assert inv.source == "bafu-2026"
    assert inv.source_version == "v1"
    assert inv.sectors == ("02-electricity",)


def test_filters_to_requested_source(data_root):
    # two sources in one folder: only the requested one survives, exchanges follow
    path = data_root / SECTOR / "processes.parquet"
    proc = pd.read_parquet(path)
    proc.loc[proc["process_id"] == P2, ["source", "source_version"]] = ["other-1", "2025"]
    proc.to_parquet(path, index=False)
    meta_path = data_root / SECTOR / "metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["sources"] = ["bafu-2026", "other-1"]
    meta_path.write_text(json.dumps(meta))

    inv = load_inventory(data_root, source="bafu-2026")
    assert list(inv.processes.process_id) == [P1]
    assert set(inv.exchanges.process_id) == {P1}
    assert inv.source_version == "v1"

    other = load_inventory(data_root, source="other-1")
    assert list(other.processes.process_id) == [P2]
    assert other.source == "other-1" and other.source_version == "2025"


def test_skips_folders_whose_metadata_lacks_source(data_root):
    # the skipped folder's parquet is unreadable on purpose: a successful load proves the
    # file was never opened
    _add_sector(data_root, "09-electronics", ["other-1"], corrupt=True)
    inv = load_inventory(data_root, source="bafu-2026")
    assert inv.sectors == ("02-electricity",)
    assert sorted(inv.processes.process_id) == sorted([P1, P2])


def test_reads_every_folder_listing_the_source(data_root):
    extra = (
        pd.read_parquet(data_root / SECTOR / "processes.parquet")
        .iloc[[0]]
        .assign(process_id="33333333-3333-3333-3333-333333333333")
    )
    _add_sector(data_root, "99-obsolete", ["bafu-2026"], processes=extra)
    inv = load_inventory(data_root)
    assert inv.sectors == ("02-electricity", "99-obsolete")
    assert len(inv.processes) == 3


def test_unknown_source_is_an_error_listing_available(data_root):
    _add_sector(data_root, "09-electronics", ["other-1"], corrupt=True)
    with pytest.raises(ValueError, match="source='nope'") as exc_info:
        load_inventory(data_root, source="nope")
    assert "bafu-2026" in str(exc_info.value) and "other-1" in str(exc_info.value)


def test_folder_without_sources_key_is_an_error(data_root):
    # 0.1.0 metadata: refuse rather than fall back to opening the parquet
    meta_path = data_root / SECTOR / "metadata.json"
    meta_path.write_text(json.dumps({"sector": "electricity", "rank": 2}))
    with pytest.raises(ValueError, match="sources") as exc_info:
        load_inventory(data_root)
    assert "02-electricity" in str(exc_info.value)


def test_folder_without_metadata_is_an_error(data_root):
    (data_root / SECTOR / "metadata.json").unlink()
    with pytest.raises(FileNotFoundError, match="metadata.json"):
        load_inventory(data_root)


def test_missing_source_column_is_an_error(data_root):
    path = data_root / SECTOR / "processes.parquet"
    pd.read_parquet(path).drop(columns=["source"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="source"):
        load_inventory(data_root)


def test_missing_required_column_is_an_error(data_root):
    path = data_root / SECTOR / "processes.parquet"
    pd.read_parquet(path).drop(columns=["reference_product"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="reference_product"):
        load_inventory(data_root)


def test_no_sector_folders_is_an_error(tmp_path):
    (tmp_path / "sentier-inventory" / "data").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_inventory(tmp_path)


def test_sector_missing_exchanges_file_is_an_error(data_root):
    path = data_root / SECTOR / "exchanges.parquet"
    path.unlink()
    with pytest.raises(FileNotFoundError, match="no exchanges.parquet") as exc_info:
        load_inventory(data_root)
    assert "02-electricity" in str(exc_info.value)


def test_uncertainty_columns_are_float64_when_absent(data_root):
    path = data_root / SECTOR / "exchanges.parquet"
    dropped = ["uncertainty_type", "loc", "scale", "minimum", "maximum"]
    pd.read_parquet(path).drop(columns=dropped).to_parquet(path, index=False)
    inv = load_inventory(data_root)
    for column in dropped:
        assert column in inv.exchanges.columns
        assert inv.exchanges[column].isna().all()
        assert inv.exchanges[column].dtype == "float64"
