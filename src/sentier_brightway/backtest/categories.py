"""The 25 EF 3.1 categories: our method ids, dashboard short ids and labels, BAFU headers.

This is the single source of truth. The dashboard's ``CATS`` array is generated from it
(``as_js_cats``) and a test asserts the HTML carries exactly that text.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Category:
    short: str  # CSV column / dashboard id
    method_id: str  # sentier-methods id, also the datapackage slug source
    label: str  # dashboard column header
    xlsx_header: str  # BAFU LCIA table header (whitespace-normalised)


# Non-score columns of the scorer's frame, shared by scorer.py and compare.py (kept here so
# compare.py never imports scorer.py, whose bw2calc import must stay lazy).
META_COLUMNS = ("bw_id", "code", "name", "location", "unit")

CATEGORIES: tuple[Category, ...] = (
    Category("climate", "ef-3.1:climate-change", "Climate Change", "Climate change [kg CO2 eq]"),
    Category(
        "cc_bio",
        "ef-3.1:climate-change-biogenic",
        "CC: Biogenic",
        "Climate change (biogenic) [kg CO2 eq]",
    ),
    Category(
        "cc_fos",
        "ef-3.1:climate-change-fossil",
        "CC: Fossil",
        "Climate change (fossil) [kg CO2 eq]",
    ),
    Category(
        "cc_luc",
        "ef-3.1:climate-change-land-use-and-land-use-change",
        "CC: LULUC",
        "Climate change (land use) [kg CO2 eq]",
    ),
    Category(
        "ozone", "ef-3.1:ozone-depletion", "Ozone Depletion", "Ozone depletion [kg CFC11 eq]"
    ),
    Category(
        "radiation",
        "ef-3.1:ionising-radiation-human-health",
        "Ionising Radiation",
        "Ionising radiation (human health) [kBq U235 eq]",
    ),
    Category(
        "photo_ox",
        "ef-3.1:photochemical-ozone-formation-human-health",
        "Photochem. Oxidant",
        "Photochemical ozone formation (human health) [kg NMVOC eq]",
    ),
    Category(
        "pm",
        "ef-3.1:ef-particulate-matter",
        "Particulate Matter",
        "Particulate matter [disease incidence]",
    ),
    Category(
        "ht_nc",
        "ef-3.1:human-toxicity-non-cancer",
        "HT: Non-Carcinog.",
        "Human toxicity non-cancer [CTUh]",
    ),
    Category(
        "ht_nc_inorg",
        "ef-3.1:human-toxicity-non-cancer-inorganics",
        "HT: NC Inorg.",
        "Human toxicity non-cancer (inorganics) - [CTUh]",
    ),
    Category(
        "ht_nc_org",
        "ef-3.1:human-toxicity-non-cancer-organics",
        "HT: NC Org.",
        "Human toxicity non-cancer (organics) [CTUh]",
    ),
    Category(
        "ht_c", "ef-3.1:human-toxicity-cancer", "HT: Carcinog.", "Human toxicity cancer [CTUh]"
    ),
    Category(
        "ht_c_inorg",
        "ef-3.1:human-toxicity-cancer-inorganics",
        "HT: C Inorg.",
        "Human toxicity cancer (inorganics) [ CTUh ]",
    ),
    Category(
        "ht_c_org",
        "ef-3.1:human-toxicity-cancer-organics",
        "HT: C Org.",
        "Human toxicity cancer (organics) [CTUh]",
    ),
    Category("acid", "ef-3.1:acidification", "Acidification", "Acidification [mol H+ eq]"),
    Category(
        "e_fw",
        "ef-3.1:eutrophication-freshwater",
        "Eutro. Freshwater",
        "Eutrophication freshwater [kg P eq]",
    ),
    Category(
        "e_m", "ef-3.1:eutrophication-marine", "Eutro. Marine", "Eutrophication marine [kg N eq]"
    ),
    Category(
        "e_t",
        "ef-3.1:eutrophication-terrestrial",
        "Eutro. Terrestrial",
        "Eutrophication terrestrial [mol N eq]",
    ),
    Category(
        "ecotox",
        "ef-3.1:ecotoxicity-freshwater",
        "Ecotox. Freshwater",
        "Ecotoxicity freshwater [CTUe]",
    ),
    Category(
        "ecotox_inorg",
        "ef-3.1:ecotoxicity-freshwater-inorganics",
        "Ecotox. Inorg.",
        "Ecotoxicity freshwater (inorganics) [CTUe]",
    ),
    Category(
        "ecotox_org",
        "ef-3.1:ecotoxicity-freshwater-organics",
        "Ecotox. Org.",
        "Ecotoxicity freshwater (organics) [CTUe]",
    ),
    Category("land", "ef-3.1:land-use", "Land Use", "Land use [dimensionless (pt)]"),
    Category("water", "ef-3.1:water-use", "Water Use", "Water use [m3 world eq]"),
    Category(
        "energy",
        "ef-3.1:resource-use-fossils",
        "Energy (non-ren.)",
        "Resource use fossils [MJ (net calorific)]",
    ),
    Category(
        "mater",
        "ef-3.1:resource-use-minerals-and-metals",
        "Materials",
        "Resource use minerals and metals [kg Sb eq]",
    ),
)

_BY_SHORT = MappingProxyType({c.short: c for c in CATEGORIES})
_BY_HEADER = MappingProxyType({" ".join(c.xlsx_header.split()): c for c in CATEGORIES})


def by_short(short: str) -> Category:
    return _BY_SHORT[short]


def by_header(header: str) -> Category | None:
    """Match a BAFU column header after whitespace normalisation; None if not an EF column."""
    return _BY_HEADER.get(" ".join(str(header).split()))


def shorts() -> tuple[str, ...]:
    return tuple(c.short for c in CATEGORIES)


def method_ids() -> tuple[str, ...]:
    return tuple(c.method_id for c in CATEGORIES)


def as_js_cats() -> str:
    """The dashboard's ``const CATS = [...]`` block, one ``[short, label]`` pair per line."""
    width = max(len(c.short) for c in CATEGORIES) + 3
    lines = [
        f"  [{(chr(39) + c.short + chr(39) + ',').ljust(width)} '{c.label}']," for c in CATEGORIES
    ]
    return "const CATS = [\n" + "\n".join(lines) + "\n];"
