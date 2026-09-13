import pandas as pd


def test_fixture_layout(data_root):
    assert (data_root / "sentier-inventory/data/02-electricity/exchanges.parquet").is_file()
    assert (data_root / "sentier-vocab/data/elementary-flows/air-01.parquet").is_file()
    assert (data_root / "sentier-methods/data/01-ef-3.1/methods.parquet").is_file()
    assert (
        data_root / "sentier-mappings/data/bafu-2026-v1__ef-3.1/biosphere-1-curated.json"
    ).is_file()
    ex = pd.read_parquet(data_root / "sentier-inventory/data/02-electricity/exchanges.parquet")
    assert len(ex) == 7
