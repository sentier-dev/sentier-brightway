import zipfile

import openpyxl
import pytest

from sentier_brightway.backtest.categories import CATEGORIES
from sentier_brightway.backtest.reference import BafuReference, demojibake, split_product
from tests.conftest import BAFU_SHEET, REF_P1_CLIMATE_PER_MJ


def test_split_product_on_last_separator():
    assert split_product("Electricity, low voltage, at grid - CH") == (
        "Electricity, low voltage, at grid",
        "CH",
    )
    assert split_product("Cotton fibres, at farm - US") == ("Cotton fibres, at farm", "US")
    assert split_product("Some - thing - RER") == ("Some - thing", "RER")


def test_split_product_without_location_raises():
    with pytest.raises(ValueError):
        split_product("NoLocation")


def test_demojibake_variants():
    assert demojibake("WÃƒÂ¤rme") == "Wärme"
    assert demojibake("ÃƒÂ–BB") == "ÖBB"
    assert demojibake("ÃƒÂŸ") == "ß"
    assert demojibake("plain") == "plain"


def test_reads_headers_units_and_scores(bafu_xlsx):
    ref = BafuReference.from_path(bafu_xlsx)
    assert list(ref.frame.columns[:3]) == ["name", "location", "unit"]
    assert len(ref.frame) == 3
    row = ref.frame.set_index(["name", "location"]).loc[
        ("Electricity, low voltage, at grid", "CH")
    ]
    assert row["unit"] == "MJ"
    assert row["climate"] == pytest.approx(REF_P1_CLIMATE_PER_MJ)
    assert row["acid"] == 0.0
    assert row["water"] != row["water"]  # NaN for blank cells
    assert ref.blank_cells > 0
    assert "Wärme, ab Kessel" in set(ref.frame["name"])


def test_zip_input_is_accepted(bafu_xlsx, tmp_path):
    z = tmp_path / "ref.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(bafu_xlsx, "BAFU-2026 v1_LCIA Results/x.xlsx")
    assert len(BafuReference.from_path(z).frame) == 3


def test_zip_with_two_xlsx_raises(bafu_xlsx, tmp_path):
    z = tmp_path / "ref.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(bafu_xlsx, "a.xlsx")
        zf.write(bafu_xlsx, "b.xlsx")
    with pytest.raises(ValueError):
        BafuReference.from_path(z)


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        BafuReference.from_path(tmp_path / "nope.xlsx")


def test_duplicate_product_is_an_error(bafu_xlsx):
    wb = openpyxl.load_workbook(bafu_xlsx)
    ws = wb.active
    ws.append([c.value for c in ws[3]])
    wb.save(bafu_xlsx)
    with pytest.raises(ValueError, match="duplicate"):
        BafuReference.from_path(bafu_xlsx)


def test_missing_ef_header_is_an_error(bafu_xlsx):
    wb = openpyxl.load_workbook(bafu_xlsx)
    ws = wb.active
    ws.cell(row=2, column=6).value = "Not an EF column"
    wb.save(bafu_xlsx)
    with pytest.raises(ValueError, match="Climate change"):
        BafuReference.from_path(bafu_xlsx)


def test_wrong_sheet_name_is_an_error(bafu_xlsx):
    wb = openpyxl.load_workbook(bafu_xlsx)
    ws = wb.active
    ws.title = "Some Other Sheet"
    wb.save(bafu_xlsx)
    with pytest.raises(ValueError, match=BAFU_SHEET):
        BafuReference.from_path(bafu_xlsx)


def test_non_numeric_score_raises(bafu_xlsx):
    wb = openpyxl.load_workbook(bafu_xlsx)
    ws = wb.active
    ws.cell(row=3, column=6).value = "n/a"  # climate column, first data row
    wb.save(bafu_xlsx)
    with pytest.raises(ValueError, match="non-numeric"):
        BafuReference.from_path(bafu_xlsx)


def test_blank_unit_cell_raises_naming_product(bafu_xlsx):
    wb = openpyxl.load_workbook(bafu_xlsx)
    ws = wb.active
    ws.cell(row=3, column=4).value = None  # unit column, first data row
    wb.save(bafu_xlsx)
    with pytest.raises(ValueError) as exc_info:
        BafuReference.from_path(bafu_xlsx)
    assert "None" not in str(exc_info.value)
    assert "Electricity, low voltage, at grid - CH" in str(exc_info.value)


def test_forward_fill_ignores_family_after_ef_block(tmp_path):
    """A second family block after EF 3.1 whose header text collides with an EF header must
    not steal the column: the reader keeps the index from the true EF 3.1 family."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = BAFU_SHEET
    families = [None, None, None, None, "EF 3.1"] + [None] * 24 + ["Other Family"]
    header = (
        ["Product", "Category", "Sub-category", "Unit"]
        + [c.xlsx_header for c in CATEGORIES]
        + [CATEGORIES[0].xlsx_header]
    )  # colliding "Climate change [kg CO2 eq]" in a new family
    ws.append(families)
    ws.append(header)
    ws.append(
        ["Electricity, low voltage, at grid - CH", "electricity", "grid", "MJ"]
        + [1.0] * 25
        + [999.0]
    )
    path = tmp_path / "collision.xlsx"
    wb.save(path)
    ref = BafuReference.from_path(path)
    assert ref.frame.iloc[0]["climate"] == 1.0
