import pytest

from sentier_brightway.inventory import Inventory, load_inventory
from tests.conftest import P1, P2


def test_loads_all_sectors_into_two_frames(data_root):
    inv = load_inventory(data_root)
    assert isinstance(inv, Inventory)
    assert sorted(inv.processes.process_id) == sorted([P1, P2])
    assert len(inv.exchanges) == 7


def test_missing_required_column_is_an_error(data_root):
    import pandas as pd

    path = data_root / "sentier-inventory/data/02-electricity/processes.parquet"
    pd.read_parquet(path).drop(columns=["reference_product"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="reference_product"):
        load_inventory(data_root)


def test_no_sector_folders_is_an_error(tmp_path):
    (tmp_path / "sentier-inventory" / "data").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_inventory(tmp_path)
