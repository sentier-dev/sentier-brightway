"""Read BAFU's published 'LCIA Results' workbook into a frame keyed by (name, location)."""

from __future__ import annotations

import math
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .categories import CATEGORIES, UNSPECIFIED_SECTOR, by_header, shorts

SHEET = "BAFU_2026 v1"
PRODUCT_COL, SECTOR_COL, UNIT_COL = 0, 1, 3
SECTOR_PLACEHOLDERS = frozenset({"#n/a", "n/a", "-"})  # compared lower-cased, stripped
EF_FAMILY = "EF 3.1"


def demojibake(text: str) -> str:
    """The table double-encodes non-ASCII names ('ä' arrives as 'ÃƒÂ¤'); undo that.

    Most bytes round-trip through cp1252, but some (e.g. the second byte of 'ÖBB' or 'ß')
    only exist in latin-1, so fall back to it when cp1252 can't encode a character."""
    for _ in range(2):
        try:
            raw = text.encode("cp1252")
        except UnicodeEncodeError:
            try:
                raw = text.encode("latin-1")
            except UnicodeEncodeError:
                return text
        try:
            fixed = raw.decode("utf-8")
        except UnicodeDecodeError:
            return text
        if fixed == text:
            return text
        text = fixed
    return text


def split_product(product: str) -> tuple[str, str]:
    """``"<name> - <location>"`` split on the LAST separator (names may contain ' - ')."""
    name, sep, location = product.rpartition(" - ")
    if not sep:
        raise ValueError(f"product without ' - <location>' suffix: {product!r}")
    return name.strip(), location.strip()


def _xlsx_path(path: Path, tmp: Path) -> Path:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith(".xlsx")]
            if len(members) != 1:
                raise ValueError(f"{path} must contain exactly one .xlsx, found {members}")
            return Path(zf.extract(members[0], tmp))
    return path


@dataclass(frozen=True)
class BafuReference:
    frame: pd.DataFrame  # columns: name, location, sector, unit, <25 shorts> (NaN when blank)
    blank_cells: int
    source: str

    @classmethod
    def from_path(cls, path: Path | str) -> "BafuReference":
        import openpyxl

        path = Path(path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"BAFU reference not found: {path}")
        with tempfile.TemporaryDirectory() as tmp:
            xlsx = _xlsx_path(path, Path(tmp))
            wb = openpyxl.load_workbook(xlsx, read_only=True)
            try:
                if SHEET not in wb.sheetnames:
                    raise ValueError(f"{path}: sheet {SHEET!r} not found, have {wb.sheetnames}")
                ws = wb[SHEET]
                rows = ws.iter_rows(values_only=True)
                families, header = next(rows), next(rows)
                columns = _ef_columns(families, header, path)
                records, blanks, seen = [], 0, set()
                for row in rows:
                    if not row[PRODUCT_COL]:
                        continue
                    product = demojibake(str(row[PRODUCT_COL]).strip())
                    if product in seen:
                        raise ValueError(f"duplicate product in {path}: {product!r}")
                    seen.add(product)
                    name, location = split_product(product)
                    unit = row[UNIT_COL]
                    if unit is None:
                        raise ValueError(f"{path}: blank unit for {product!r}")
                    record = {
                        "name": name,
                        "location": location,
                        "sector": _sector(row[SECTOR_COL]),
                        "unit": str(unit).strip(),
                    }
                    for short, i in columns.items():
                        value = row[i] if i < len(row) else None
                        if value is None:
                            blanks += 1
                            record[short] = math.nan
                        else:
                            try:
                                record[short] = float(value)
                            except (TypeError, ValueError):
                                raise ValueError(
                                    f"{path}: non-numeric score {value!r} for "
                                    f"{product!r} / {short}"
                                ) from None
                    records.append(record)
            finally:
                wb.close()
        frame = pd.DataFrame(records, columns=["name", "location", "sector", "unit", *shorts()])
        return cls(frame=frame, blank_cells=blanks, source=str(path))


def _sector(value: object) -> str:
    """The table's top-level ``Category`` cell as a stripped string, or ``UNSPECIFIED_SECTOR``
    for blank cells and the placeholders in ``SECTOR_PLACEHOLDERS`` (case-insensitive)."""
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in SECTOR_PLACEHOLDERS:
        return UNSPECIFIED_SECTOR
    return text


def _ef_columns(families, header, path: Path) -> dict[str, int]:
    """short -> column index for the 25 EF 3.1 headers; every category must be present."""
    if header[PRODUCT_COL] != "Product" or header[UNIT_COL] != "Unit":
        raise ValueError(f"unexpected header layout in {path}: {list(header[:4])}")
    family, found = None, {}
    for i, (fam, name) in enumerate(zip(families, header)):
        family = fam or family
        if family == EF_FAMILY and name:
            cat = by_header(name)
            if cat is not None:
                found[cat.short] = i
    missing = [c.xlsx_header for c in CATEGORIES if c.short not in found]
    if missing:
        raise ValueError(f"{path}: EF 3.1 columns missing: {missing}")
    return found
