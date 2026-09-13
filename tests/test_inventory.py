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


def test_sector_missing_exchanges_file_is_an_error(data_root):
    path = data_root / "sentier-inventory/data/02-electricity/exchanges.parquet"
    path.unlink()
    with pytest.raises(FileNotFoundError, match="no exchanges.parquet") as exc_info:
        load_inventory(data_root)
    assert "02-electricity" in str(exc_info.value)


def test_uncertainty_columns_are_float64_when_absent(data_root):
    path = data_root / "sentier-inventory/data/02-electricity/exchanges.parquet"
    import pandas as pd

    dropped = ["uncertainty_type", "loc", "scale", "minimum", "maximum"]
    pd.read_parquet(path).drop(columns=dropped).to_parquet(path, index=False)
    inv = load_inventory(data_root)
    for column in dropped:
        assert column in inv.exchanges.columns
        assert inv.exchanges[column].isna().all()
        assert inv.exchanges[column].dtype == "float64"
