import pytest

from sentier_brightway.units import normalize_unit, required_scale_factor


def test_known_bafu_spellings():
    assert normalize_unit("kg") == "kilogram"
    assert normalize_unit("kWh") == "kilowatt hour"
    assert normalize_unit("kBq") == "kilo Becquerel"
    assert normalize_unit("Bq") == "Becquerel"
    assert normalize_unit("p") == "unit"
    assert normalize_unit("m2a") == "square meter-year"


def test_bridge_area_time_spelling():
    assert normalize_unit("m2*a") == "square meter-year"


def test_bridge_target_spellings_pass_through():
    assert normalize_unit("kilogram") == "kilogram"


def test_unknown_unit_is_returned_unchanged():
    assert normalize_unit("furlong") == "furlong"


def test_none_becomes_empty_string():
    assert normalize_unit(None) == ""


def test_nan_becomes_empty_string():
    assert normalize_unit(float("nan")) == ""


@pytest.mark.parametrize(
    "source,target,factor",
    [
        ("Bq", "kBq", 0.001),
        ("kBq", "Bq", 1000.0),
        ("km", "m", 1000.0),
        ("m", "km", 0.001),
        ("kWh", "MJ", 3.6),
        ("MJ", "kWh", 1 / 3.6),
        ("ha", "m2", 10000.0),
        ("m2", "ha", 0.0001),
    ],
)
def test_magnitude_changes_are_required_in_both_directions(source, target, factor):
    assert required_scale_factor(source, target) == pytest.approx(factor, rel=1e-12)


@pytest.mark.parametrize(
    "source,target", [("kg", "kg"), ("Bq", "Bq"), ("kg", "MJ"), ("Nm3", "m3"), ("furlong", "m")]
)
def test_no_factor_without_a_known_magnitude_change(source, target):
    assert required_scale_factor(source, target) is None
