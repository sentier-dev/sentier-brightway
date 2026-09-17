import json
import math

import pandas as pd
import pytest

from sentier_brightway.backtest import boxes
from sentier_brightway.backtest.categories import by_short
from sentier_brightway.backtest.compare import align, compare
from tests.conftest import P1, P2
from tests.test_backtest_compare import CATS, _reference, _scores


def _compared():
    return compare(align(_scores(), _reference(), CATS), CATS)


def test_box_stats_by_hand():
    s = pd.Series([-8.0, -1.0, 0.0, 0.5, 1.0, 2.0, 40.0])
    b = boxes.box_stats(s, codes=pd.Series(list("abcdefg")))
    assert b.n == 7 and b.median == 0.5
    assert b.q1 == -0.5 and b.q3 == 1.5  # pandas linear interpolation
    assert (b.lo, b.hi) == (-1.0, 2.0)  # 1.5 IQR = 3 -> fence [-3.5, 4.5]
    assert (b.min, b.max) == (-8.0, 40.0)
    assert b.outliers == (("g", 40.0), ("a", -8.0))  # by |pct| desc
    assert b.n_outliers == 2 and b.n_blank == 0


def test_box_stats_empty_and_nan():
    b = boxes.box_stats(pd.Series([math.nan, math.nan]), codes=pd.Series(["a", "b"]), n_blank=2)
    assert b.n == 0 and b.median is None and b.outliers == ()
    assert b.n_blank == 2 and b.n_outliers == 0
    assert (b.min, b.q1, b.q3, b.max, b.lo, b.hi) == (None,) * 6


def test_box_stats_ignores_nan_and_counts_finite_only():
    s = pd.Series([math.nan, 1.0, 3.0, math.nan])
    b = boxes.box_stats(s, codes=pd.Series(list("abcd")), n_blank=2)
    assert b.n == 2 and b.median == 2.0 and b.n_blank == 2
    assert (b.lo, b.hi) == (1.0, 3.0) and b.outliers == ()


def test_outlier_cap_and_tiebreak():
    vals = pd.Series([100.0] * 3 + [0.0] * 20)
    codes = pd.Series([f"c{i}" for i in range(23)])
    b = boxes.box_stats(vals, codes, cap=2)
    assert b.n_outliers == 3 and [c for c, _ in b.outliers] == ["c0", "c1"]


def test_box_stats_rounds_to_four_decimals():
    b = boxes.box_stats(pd.Series([1.23456789, 1.23456789]), codes=pd.Series(["a", "b"]))
    assert b.median == 1.2346 and b.min == 1.2346


def test_box_is_frozen():
    b = boxes.box_stats(pd.Series([1.0]), codes=pd.Series(["a"]))
    with pytest.raises(Exception):
        b.n = 5  # type: ignore[misc]


def test_payload_has_all_and_sectors():
    payload = boxes.boxes_payload(_compared(), CATS)
    assert payload["sectors"][0] == "all"
    assert set(payload["sectors"]) == {"all", "electricity"}  # only mapped rows count
    assert payload["categories"] == [c.short for c in CATS]
    assert set(payload["boxes"]) == {"all", "electricity"}
    climate = payload["boxes"]["all"]["climate"]
    assert climate["n"] == 2 and climate["n_blank"] == 0
    assert climate["median"] == pytest.approx(-100 / 22, abs=1e-3)
    assert set(climate) == {
        "n",
        "n_blank",
        "min",
        "q1",
        "median",
        "q3",
        "max",
        "lo",
        "hi",
        "n_outliers",
        "outliers",
    }
    assert isinstance(climate["outliers"], list)
    assert payload["boxes"]["all"]["acid"]["n_blank"] == 0  # both floored to 0.0, not blank
    water = payload["boxes"]["all"]["water"]
    assert water["n"] == 0 and water["n_blank"] == 2 and water["median"] is None  # zero ref
    assert payload["boxes"]["electricity"]["climate"] == climate


def test_payload_splits_by_sector():
    reference = _reference().assign(sector=["electricity", "heat", "chemicals"])
    compared = compare(align(_scores(), reference, CATS), CATS)
    payload = boxes.boxes_payload(compared, CATS)
    assert payload["sectors"] == ["all", "electricity", "heat"]
    assert payload["boxes"]["heat"]["climate"]["n"] == 1
    assert payload["boxes"]["heat"]["climate"]["median"] == pytest.approx(-100 / 11, abs=1e-3)
    assert payload["boxes"]["electricity"]["climate"]["median"] == 0.0


def test_payload_is_deterministic_json():
    a = json.dumps(boxes.boxes_payload(_compared(), CATS), sort_keys=True)
    b = json.dumps(boxes.boxes_payload(_compared(), CATS), sort_keys=True)
    assert a == b


def test_worst_rows_sorted_and_capped():
    compared = _compared()
    rows = boxes.worst_rows(compared, by_short("climate"), n=1)
    assert len(rows) == 1
    assert set(rows[0]) == {"code", "name", "location", "sector", "unit", "ours", "ref", "pct"}
    assert rows[0]["code"] == P2  # |-9.09| > 0 for P1
    assert rows[0]["name"] == "Electricity, medium voltage, at grid"
    assert rows[0]["location"] == "CH" and rows[0]["sector"] == "electricity"
    assert rows[0]["unit"] == "MJ"
    assert rows[0]["ours"] == pytest.approx(0.5 / 3.6)
    assert rows[0]["ref"] == pytest.approx(0.5 / 3.6 * 1.1)
    assert rows[0]["pct"] == pytest.approx(-100 / 11, abs=1e-3)
    both = boxes.worst_rows(compared, by_short("climate"))
    assert [r["code"] for r in both] == [P2, P1]


def test_worst_rows_skip_blank_pct_and_break_ties_by_code():
    compared = _compared()
    assert boxes.worst_rows(compared, by_short("water")) == []  # every pct is blank
    acid = boxes.worst_rows(compared, by_short("acid"))  # both 0.0 -> tie -> by code
    assert [r["code"] for r in acid] == sorted([P1, P2])


def test_worst_rows_values_are_plain_floats():
    for row in boxes.worst_rows(_compared(), by_short("climate")):
        assert type(row["ours"]) is float and type(row["ref"]) is float
        assert type(row["pct"]) is float
        assert row["pct"] == round(row["pct"], 4)
    assert "-0.0" not in json.dumps(boxes.worst_rows(_compared(), by_short("acid")))
