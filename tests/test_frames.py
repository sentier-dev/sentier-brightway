from pathlib import Path

import pandas as pd
import pytest

from sentier_brightway._frames import codes_from_iris, data_root_error, require_columns


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


def test_codes_from_iris_strips_the_prefix():
    iri = pd.Series(["https://vocab.sentier.dev/flows/abc", "https://vocab.sentier.dev/flows/def"])
    codes = codes_from_iris(iri, Path("somewhere.parquet"))
    assert list(codes) == ["abc", "def"]


def test_codes_from_iris_raises_naming_path_and_bad_value():
    iri = pd.Series(["https://vocab.sentier.dev/flows/abc", "urn:uuid:def"])
    with pytest.raises(ValueError, match="somewhere.parquet") as exc_info:
        codes_from_iris(iri, Path("somewhere.parquet"))
    assert "urn:uuid:def" in str(exc_info.value)
