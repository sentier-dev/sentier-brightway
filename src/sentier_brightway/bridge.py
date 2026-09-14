"""Read the ordered ``bafu-2026-v1 -> ef-3.1`` randonneur packages from sentier-mappings.

Only ``replace`` entries relink a source flow to a different target flow. A randonneur
``update`` entry edits fields on the *same* flow (for example a unit-spelling
normalisation) and names no new target to relink to, so it is ignored here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from ._frames import data_root_error
from .constants import BRIDGE_FOLDER, NOMENCLATURE_KIND_ORDER, REPO_MAPPINGS

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


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc


def _entries(package: dict) -> list[dict]:
    """Only ``replace`` entries relink a source flow code to a target flow code."""
    return list(package.get("replace", []))


def _entry_fields(entry: dict, path: Path, i: int) -> tuple[str, dict]:
    """Validate one randonneur entry and return ``(source_code, BridgeEntry kwargs)``."""
    source = entry.get("source") or {}
    target = entry.get("target") or {}
    source_code = source.get("code")
    if source_code is None:
        raise ValueError(f"{path} entry {i}: missing source.code")
    target_code = target.get("code")
    if target_code is None:
        raise ValueError(f"{path} entry {i}: missing target.code")
    cf = entry.get("conversion_factor")
    fields = {
        "target_code": target_code,
        "target_unit": str(target.get("unit", "")),
        "conversion_factor": 1.0 if cf is None else float(cf),
        "target_location": target.get("location"),
    }
    return source_code, fields


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
            code, fields = _entry_fields(entry, path, i)
            if code in merged:
                continue
            merged[code] = BridgeEntry(nomenclature=is_nomenclature, **fields)
    return MappingProxyType(merged)
