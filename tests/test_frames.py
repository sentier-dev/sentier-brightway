from pathlib import Path

import pandas as pd
import pytest

from sentier_brightway._frames import data_root_error, require_columns


def test_require_columns_passes_when_all_present():
    df = pd.DataFrame({"a": [1], "b": [2]})
    require_columns(df, frozenset({"a", "b"}), Path("somewhere.parquet"))


def test_require_columns_raises_naming_missing_columns():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="b"):
        require_columns(df, frozenset({"a", "b"}), Path("somewhere.parquet"))


def test_data_root_error_names_expected_path_and_layout():
    err = data_root_error("sector folders", Path("/tmp/x/sentier-inventory/data"))
    assert "/tmp/x/sentier-inventory/data" in str(err)
    assert "sentier-inventory" in str(err)
    assert "sentier-vocab" in str(err)
    assert isinstance(err, FileNotFoundError)
