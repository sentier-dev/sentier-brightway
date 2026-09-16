import pathlib

import pandas as pd
import pytest

from sentier_brightway.backtest.categories import (
    CATEGORIES,
    as_js_cats,
    by_header,
    by_short,
    method_ids,
)

REAL_METHODS_PARQUET = pathlib.Path(
    "/home/laurenz/dds/sentier-methods/data/01-ef-3.1/methods.parquet"
)


def test_twenty_five_unique_categories():
    assert len(CATEGORIES) == 25
    assert len({c.short for c in CATEGORIES}) == 25
    assert len({c.method_id for c in CATEGORIES}) == 25
    assert len({c.xlsx_header for c in CATEGORIES}) == 25


def test_order_starts_with_climate_family():
    assert [c.short for c in CATEGORIES[:4]] == ["climate", "cc_bio", "cc_fos", "cc_luc"]


def test_lookup_and_method_ids():
    assert by_short("water").method_id == "ef-3.1:water-use"
    assert method_ids()[0] == "ef-3.1:climate-change"


def test_by_header_returns_none_for_unknown():
    assert by_header("Not an EF column") is None


def test_by_header_matches_with_extra_whitespace():
    assert by_header("Human  toxicity cancer (inorganics)   [ CTUh ]") is by_short("ht_c_inorg")


def test_js_cats_renders_one_line_per_category():
    js = as_js_cats()
    assert js.startswith("const CATS = [\n")
    assert js.rstrip().endswith("];")
    assert js.count("\n  ['") == 25
    assert "  ['ht_c_inorg',   'HT: C Inorg.']," in js


def test_real_method_ids_exist():
    if not REAL_METHODS_PARQUET.is_file():
        pytest.skip("real sentier-methods checkout not available")
    ids = set(pd.read_parquet(REAL_METHODS_PARQUET)["method_id"])
    assert set(method_ids()) == ids
