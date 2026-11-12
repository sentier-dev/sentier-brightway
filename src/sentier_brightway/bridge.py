"""Read the ordered ``bafu-2026-v1 -> ef-3.1`` randonneur packages from sentier-mappings.

Only ``replace`` entries relink a source flow to a different target flow. A randonneur
``update`` entry edits fields on the *same* flow (for example a unit-spelling
normalisation) and names no new target to relink to, so it is ignored here.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from ._frames import data_root_error
from .constants import BRIDGE_FOLDER, NOMENCLATURE_KIND_ORDER, REPO_MAPPINGS
from .units import normalize_unit, required_scale_factor

SUPPORTED_SCHEMA_MAJOR = "0"


@dataclass(frozen=True)
class BridgeEntry:
    target_code: str
    target_unit: str
    conversion_factor: float = 1.0
    nomenclature: bool = False  # target EF flow carries no factor in any EF 3.1 method
    # captured for completeness; not used for linking in v0.1 because regionalized CFs
    # are skipped by the methods reader, so a located target is equivalent to the global one
    target_location: str | None = None
    source_unit: str | None = None
    # where the entry was read ("<package path> entry <i>"), so a later refusal can name it
    origin: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        factor = self.conversion_factor
        # bools and text are refused outright; anything else must convert to a float, so a
        # bad factor is a ValueError (which cli.main reports), never a TypeError or OverflowError
        if isinstance(factor, (bool, str, bytes, bytearray)):
            raise ValueError("conversion_factor must be positive and finite")
        try:
            factor = float(factor)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("conversion_factor must be positive and finite") from exc
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("conversion_factor must be positive and finite")
        expected = required_scale_factor(self.source_unit, self.target_unit)
        if expected is not None and not math.isclose(factor, expected, rel_tol=1e-12):
            raise ValueError(f"conversion_factor {expected:g} is required for declared units")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc


def _entries(package: dict) -> list[dict]:
    """Only ``replace`` entries relink a source flow code to a target flow code."""
    return list(package.get("replace", []))


def _entry(entry: dict, path: Path, i: int, nomenclature: bool) -> tuple[str, BridgeEntry]:
    """Parse one randonneur entry into ``(source_code, BridgeEntry)``.

    The factor rules live in ``BridgeEntry`` once; here a refusal only gains the file and
    entry index. Parsing stays here: ``float(cf)`` and the null-factor rule, which needs to
    know the factor was absent."""
    source = entry.get("source") or {}
    target = entry.get("target") or {}
    source_code = source.get("code")
    if source_code is None:
        raise ValueError(f"{path} entry {i}: missing source.code")
    target_code = target.get("code")
    if target_code is None:
        raise ValueError(f"{path} entry {i}: missing target.code")
    if entry.get("characterization_factor_fallbacks"):
        raise ValueError(
            f"{path} entry {i}: characterization_factor_fallbacks require a method-scoped "
            "consumer; this EF bridge cannot apply them"
        )
    cf = entry.get("conversion_factor")
    try:
        factor = 1.0 if cf is None else float(cf)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{path} entry {i}: conversion_factor must be positive and finite"
        ) from exc
    if isinstance(cf, bool):
        raise ValueError(f"{path} entry {i}: conversion_factor must be positive and finite")
    origin = f"{path} entry {i}"
    try:
        bridge_entry = BridgeEntry(
            target_code=target_code,
            target_unit=str(target.get("unit", "")),
            conversion_factor=factor,
            nomenclature=nomenclature,
            target_location=target.get("location"),
            source_unit=source.get("unit") or None,
            origin=origin,
        )
    except ValueError as exc:
        raise ValueError(f"{origin}: {exc}") from None
    # After the declared-unit rule, so a known magnitude change names its multiplier.
    # A null factor means "same quantity"; only a unit spelling may change without one.
    source_unit, target_unit = source.get("unit"), target.get("unit")
    if cf is None and source_unit and normalize_unit(source_unit) != normalize_unit(target_unit):
        raise ValueError(
            f"{path} entry {i}: conversion_factor is required to map {source_unit!r} "
            f"to {target_unit!r}"
        )
    return source_code, bridge_entry


def unit_conflicts(bridge: Mapping[str, BridgeEntry]) -> tuple[str, ...]:
    """One line per EF code that the bridge targets with more than one unit, in bridge order.

    Each line names the first entry of each unit by package file and entry index, with the
    unit as that entry spells it. It does not refuse: ``build()`` refuses, ``coverage`` counts.
    """
    seen: dict[str, dict[str, BridgeEntry]] = {}
    for entry in bridge.values():
        seen.setdefault(entry.target_code, {}).setdefault(normalize_unit(entry.target_unit), entry)
    return tuple(
        f"{code}: "
        + ", ".join(
            f"{e.target_unit!r} at {e.origin or 'an entry built outside load_bridge'}"
            for e in by_unit.values()
        )
        for code, by_unit in seen.items()
        if len(by_unit) > 1
    )


def _check_schema_version(meta: dict, meta_path: Path) -> None:
    schema_version = meta.get("schema_version")
    if schema_version is None:
        return
    major = str(schema_version).split(".")[0]
    if major != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError(
            f"{meta_path}: schema_version {schema_version!r} is not supported; this "
            f"package reads bridge schema major {SUPPORTED_SCHEMA_MAJOR!r}"
        )


def _ordered_packages(folder: Path, include_nomenclature: bool) -> list[tuple[Path, bool]]:
    meta_path = folder / "metadata.json"
    if not meta_path.is_file():
        raise data_root_error("bridge metadata.json", meta_path)
    meta = _load_json(meta_path)
    _check_schema_version(meta, meta_path)

    packages = meta.get("packages", [])
    for item in packages:
        if item.get("order") is None:
            raise ValueError(f"{meta_path}: a package entry is missing 'order'")
        if item.get("file") is None:
            raise ValueError(f"{meta_path}: a package entry is missing 'file'")

    out = []
    seen_files: set[str] = set()
    for item in sorted(packages, key=lambda p: int(p["order"])):
        filename = item["file"]
        if filename in seen_files:
            raise ValueError(f"{meta_path}: {filename} is listed more than once in packages")
        seen_files.add(filename)
        if item.get("kind", "biosphere") != "biosphere":
            continue
        is_nomenclature = int(item["order"]) == NOMENCLATURE_KIND_ORDER
        if is_nomenclature and not include_nomenclature:
            continue
        path = folder / filename
        if not path.is_file():
            raise FileNotFoundError(f"{meta_path} lists {filename} but it is missing")
        out.append((path, is_nomenclature))
    if not out:
        raise ValueError(f"{meta_path} lists no biosphere packages")
    return out


def _bridge_folder(data_root: Path) -> Path:
    folder = Path(data_root) / REPO_MAPPINGS / "data" / BRIDGE_FOLDER
    if not folder.is_dir():
        raise data_root_error("bridge folder", folder)
    return folder


def applied_packages(data_root: Path, include_nomenclature: bool = True) -> tuple[str, ...]:
    """File names of the packages ``load_bridge`` applies, in application order."""
    folder = _bridge_folder(data_root)
    return tuple(path.name for path, _ in _ordered_packages(folder, include_nomenclature))


def load_bridge(data_root: Path, include_nomenclature: bool = True) -> Mapping[str, BridgeEntry]:
    """``{bafu_flow_code: BridgeEntry}``; packages apply in ``metadata.json`` order, first wins."""
    folder = _bridge_folder(data_root)
    merged: dict[str, BridgeEntry] = {}
    for path, is_nomenclature in _ordered_packages(folder, include_nomenclature):
        package = _load_json(path)
        for i, entry in enumerate(_entries(package)):
            code, bridge_entry = _entry(entry, path, i, is_nomenclature)
            if code in merged:
                continue
            merged[code] = bridge_entry
    return MappingProxyType(merged)
