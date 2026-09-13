from sentier_brightway.units import normalize_unit


def test_known_bafu_spellings():
    assert normalize_unit("kg") == "kilogram"
    assert normalize_unit("kWh") == "kilowatt hour"
    assert normalize_unit("kBq") == "kilo Becquerel"
    assert normalize_unit("Bq") == "Becquerel"
    assert normalize_unit("p") == "unit"
    assert normalize_unit("m2a") == "square meter-year"


def test_bridge_target_spellings_pass_through():
    assert normalize_unit("kilogram") == "kilogram"


def test_unknown_unit_is_returned_unchanged():
    assert normalize_unit("furlong") == "furlong"


def test_none_becomes_empty_string():
    assert normalize_unit(None) == ""
