import math

import numpy as np
import pandas as pd
import pytest

from sentier_brightway.backtest import compare as cmp
from sentier_brightway.backtest.categories import by_short
from tests.conftest import P1, P2

LOW = "Electricity, low voltage, at grid"
MEDIUM = "Electricity, medium voltage, at grid"


def _scores():
    # Three processes: P1 and P2 match the reference on (name, location); "Widget" does not.
    # Electricity scores are per kWh and the reference is per MJ, so a value v here is
    # v / 3.6 once aligned: acid P1 0.18 -> 0.05 equals the reference; P2 3.6e-9 -> 1e-9 is
    # tiny on both sides (near-zero floor case).
    # water: P1 has a score but the reference is 0; P2/x have no score at all (NaN).
    return pd.DataFrame(
        {
            "bw_id": [1, 2, 3],
            "code": [P1, P2, "x"],
            "name": [LOW, MEDIUM, "Widget"],
            "location": ["CH", "CH", "GLO"],
            "unit": ["kilowatt hour", "kilowatt hour", "kilogram"],
            "climate": [2.0, 0.5, 1.0],
            "acid": [0.18, 3.6e-9, 0.2],
            "water": [1.0, math.nan, math.nan],
        }
    )


def _reference():
    # Electricity rows are per MJ (ours per kWh): climate P1 agrees exactly after the /3.6
    # conversion, P2's reference is 10 % higher than ours. "Other - DE" has no counterpart.
    return pd.DataFrame(
        {
            "name": [LOW, MEDIUM, "Other"],
            "location": ["CH", "CH", "DE"],
            "unit": ["MJ", "MJ", "kg"],
            "climate": [2.0 / 3.6, 0.5 / 3.6 * 1.1, 3.0],
            "acid": [0.05, 2e-9, 0.1],
            "water": [0.0, 1.0, 1.0],
        }
    )


CATS = (by_short("climate"), by_short("acid"), by_short("water"))


def test_unit_factor_table():
    assert cmp.unit_factor("kilowatt hour", "MJ") == pytest.approx(1 / 3.6)
    assert cmp.unit_factor("kilogram", "kg") == 1.0
    assert cmp.unit_factor("kilometer", "m") == pytest.approx(1 / 1000)
    assert cmp.unit_factor("normal cubic meter", "m3") == 1.0
    assert cmp.unit_factor("unit", "Item(s)") == 1.0
    assert cmp.unit_factor("hectare", "m2") == pytest.approx(1e-4)
    assert cmp.unit_factor("meter-year", "km*a") == pytest.approx(1000.0)
    assert cmp.unit_factor("kilogram", "furlong") is None
    assert cmp.unit_factor("kilogram", "MJ") is None


def test_align_matches_on_name_and_location_and_converts_units():
    scores, reference = _scores(), _reference()
    aligned = cmp.align(scores, reference, CATS)
    assert aligned.frame["resolution"].tolist() == ["mapped", "mapped", "unmatched"]
    assert list(aligned.frame.columns) == [
        "bw_id",
        "code",
        "name",
        "location",
        "unit",
        "ref_unit",
        "ref_product",
        "resolution",
        "climate_ours",
        "acid_ours",
        "water_ours",
        "climate_ref",
        "acid_ref",
        "water_ref",
    ]
    by_code = aligned.frame.set_index("code")
    p1 = by_code.loc[P1]
    assert p1["climate_ours"] == pytest.approx(2.0 / 3.6)  # converted to the table's unit
    assert p1["climate_ref"] == pytest.approx(2.0 / 3.6)
    assert p1["ref_unit"] == "MJ" and p1["unit"] == "kilowatt hour"
    assert p1["ref_product"] == f"{LOW} - CH"
    widget = by_code.loc["x"]
    assert np.isnan(widget["climate_ours"]) and np.isnan(widget["climate_ref"])
    assert widget["ref_unit"] != widget["ref_unit"]  # NaN
    assert widget["ref_product"] != widget["ref_product"]  # NaN
    assert aligned.unmatched_ref == (("Other", "DE"),)
    assert aligned.unit_skipped == {}
    # inputs untouched
    pd.testing.assert_frame_equal(scores, _scores())
    pd.testing.assert_frame_equal(reference, _reference())


def test_align_skips_unknown_unit_pairs():
    scores = _scores().assign(unit=["kilowatt hour", "furlong", "kilogram"])
    aligned = cmp.align(scores, _reference(), CATS)
    p2 = aligned.frame.set_index("code").loc[P2]
    assert p2["resolution"] == "unit_skipped"
    assert np.isnan(p2["climate_ours"])  # no factor, no converted value
    assert p2["climate_ref"] == pytest.approx(0.5 / 3.6 * 1.1)  # the reference is still kept
    assert aligned.unit_skipped == {("furlong", "MJ"): 1}
    assert aligned.unmatched_ref == (("Other", "DE"),)  # unit-skipped rows still count as found


def test_align_rejects_duplicate_reference_keys():
    reference = pd.concat([_reference(), _reference().iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        cmp.align(_scores(), reference, CATS)


def test_compare_pct_and_guards():
    compared = cmp.compare(cmp.align(_scores(), _reference(), CATS), CATS)
    assert compared.frame["code"].tolist() == [P1, P2]  # mapped rows only
    pct = compared.frame.set_index("code")
    assert pct.loc[P1, "climate"] == pytest.approx(0.0)
    assert pct.loc[P2, "climate"] == pytest.approx(-100 / 11, abs=1e-3)  # 0.5 vs 0.55
    # acid: mapped refs are [0.05, 2e-9] -> median 0.0250000010 -> threshold 2.5e-4;
    # P1 0.05 vs 0.05 is exactly equal (0.0, not floored); P2 1e-9 vs 2e-9 are both below
    # the threshold and the reference is not 0 -> floored to 0.0 and counted once.
    # Without the floor P2 would read -50 %.
    assert compared.thresholds["acid"] == pytest.approx(2.5e-4, rel=1e-6)
    assert pct.loc[P1, "acid"] == 0.0
    assert pct.loc[P2, "acid"] == 0.0
    assert compared.suppressed["acid"] == {"near_zero": 1, "fold_capped": 0}
    assert compared.suppressed["climate"] == {"near_zero": 0, "fold_capped": 0}
    # water: P1 has ours 1.0 but a zero reference -> blank; P2 has no score -> blank.
    assert np.isnan(pct.loc[P1, "water"])
    assert np.isnan(pct.loc[P2, "water"])
    assert compared.suppressed["water"] == {"near_zero": 0, "fold_capped": 0}


def test_fold_cap_blanks_and_counts():
    # P2 climate 25 vs 0.1528 -> +16,264 % > 1,000 % cap -> blank and counted.
    scores = _scores().assign(climate=[2.0, 0.5 * 50, 1.0])
    compared = cmp.compare(cmp.align(scores, _reference(), CATS), CATS)
    pct = compared.frame.set_index("code")
    assert np.isnan(pct.loc[P2, "climate"])
    assert pct.loc[P1, "climate"] == pytest.approx(0.0)
    assert compared.suppressed["climate"] == {"near_zero": 0, "fold_capped": 1}


def test_summary_schema():
    compared = cmp.compare(cmp.align(_scores(), _reference(), CATS), CATS)
    summary = cmp.summarise(compared, CATS)
    assert list(summary.columns) == [
        "short",
        "method_id",
        "n_compared",
        "mean_diff_pct",
        "median_diff_pct",
        "std_diff_pct",
        "within_1pct",
        "within_5pct",
        "outliers_gt5pct",
        "max_abs_diff_pct",
        "n_near_zero_floored",
        "n_fold_capped",
        "n_unit_skipped",
    ]
    assert summary["short"].tolist() == ["climate", "acid", "water"]
    assert summary["method_id"].tolist() == [c.method_id for c in CATS]
    climate = summary.set_index("short").loc["climate"]
    assert climate["n_compared"] == 2
    assert climate["within_1pct"] == 1 and climate["within_5pct"] == 1
    assert climate["outliers_gt5pct"] == 1
    assert climate["median_diff_pct"] == pytest.approx(-100 / 22, abs=1e-3)
    assert climate["max_abs_diff_pct"] == pytest.approx(100 / 11, abs=1e-3)
    acid = summary.set_index("short").loc["acid"]
    assert acid["n_compared"] == 2 and acid["n_near_zero_floored"] == 1
    assert acid["std_diff_pct"] == 0.0
    water = summary.set_index("short").loc["water"]
    assert water["n_compared"] == 0 and np.isnan(water["median_diff_pct"])
    assert np.isnan(water["std_diff_pct"]) and np.isnan(water["max_abs_diff_pct"])
    assert (summary["n_unit_skipped"] == 0).all()


def test_summary_counts_unit_skipped_on_every_row():
    scores = _scores().assign(unit=["kilowatt hour", "furlong", "kilogram"])
    compared = cmp.compare(cmp.align(scores, _reference(), CATS), CATS)
    summary = cmp.summarise(compared, CATS)
    assert (summary["n_unit_skipped"] == 1).all()
    assert summary.set_index("short").loc["climate", "n_compared"] == 1


def test_align_applies_reference_location_aliases():
    scores = _scores().assign(location=["ERCOT", "Europe without Switzerland", "GLO"])
    reference = _reference().assign(location=["US-ERCOT", "RER without CH", "DE"])
    aligned = cmp.align(scores, reference, CATS)
    assert aligned.frame["resolution"].tolist() == ["mapped", "mapped", "unmatched"]
    assert aligned.frame["location"].tolist() == ["ERCOT", "Europe without Switzerland", "GLO"]
    # the dashboard's "mapped_to" keeps the reference's own spelling
    assert aligned.frame["ref_product"].iloc[0] == f"{LOW} - US-ERCOT"
    assert aligned.aliased_ref == 2
    assert aligned.unmatched_ref == (("Other", "DE"),)
    assert cmp.LOCATION_ALIASES["US-SERC"] == "SERC"


def test_align_strips_names_on_both_sides():
    scores = _scores().assign(name=[LOW + " ", MEDIUM, "Widget"])
    reference = _reference().assign(name=[LOW, MEDIUM + "  ", "Other"])
    aligned = cmp.align(scores, reference, CATS)
    assert aligned.frame["resolution"].tolist() == ["mapped", "mapped", "unmatched"]
    assert aligned.frame["name"].tolist() == [LOW, MEDIUM, "Widget"]
    assert aligned.aliased_ref == 0
    assert aligned.unmatched_ref == (("Other", "DE"),)
