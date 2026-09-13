"""Map BAFU and bridge unit spellings onto the names Brightway (bw2io) uses."""

from __future__ import annotations

from types import MappingProxyType

_UNITS = MappingProxyType(
    {
        "kg": "kilogram",
        "kilogram": "kilogram",
        "kWh": "kilowatt hour",
        "MJ": "megajoule",
        "kBq": "kilo Becquerel",
        "Bq": "Becquerel",
        "m3": "cubic meter",
        "tkm": "ton kilometer",
        "p": "unit",
        "unit": "unit",
        "m2": "square meter",
        "km": "kilometer",
        "m2a": "square meter-year",
        "my": "meter-year",
        "Nm3": "normal cubic meter",
        "m": "meter",
        "ha": "hectare",
        "hr": "hour",
        "personkm": "person kilometer",
        "m3y": "cubic meter-year",
        "kmy": "kilometer-year",
    }
)


def normalize_unit(unit: str | None) -> str:
    """Return the Brightway spelling of ``unit``; unknown spellings pass through unchanged."""
    if not isinstance(unit, str):
        return ""
    return _UNITS.get(unit, unit)
