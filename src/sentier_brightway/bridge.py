"""Read the ordered ``bafu-2026-v1 -> ef-3.1`` randonneur packages from sentier-mappings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from ._frames import data_root_error
from .constants import BRIDGE_FOLDER, NOMENCLATURE_KIND_ORDER, REPO_MAPPINGS


@dataclass(frozen=True)
class BridgeEntry:
    target_code: str
    target_unit: str
    conversion_factor: float = 1.0
    nomenclature: bool = False  # target EF flow carries no factor in any EF 3.1 method


def _entries(package: dict) -> list[dict]:
    """``replace`` and ``update`` verbs both carry a source/target pair we can relink with."""
    return list(package.get("replace", [])) + list(package.get("update", []))


def _ordered_packages(folder: Path, include_nomenclature: bool) -> list[tuple[Path, bool]]:
    meta_path = folder / "metadata.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing {meta_path}")
    meta = json.loads(meta_path.read_text())
    out = []
    for item in sorted(meta.get("packages", []), key=lambda p: int(p["order"])):
        if item.get("kind", "biosphere") != "biosphere":
            continue
        is_nomenclature = int(item["order"]) == NOMENCLATURE_KIND_ORDER
        if is_nomenclature and not include_nomenclature:
            continue
        path = folder / item["file"]
        if not path.is_file():
            raise FileNotFoundError(f"{meta_path} lists {item['file']} but it is missing")
        out.append((path, is_nomenclature))
    if not out:
        raise FileNotFoundError(f"{meta_path} lists no biosphere packages")
    return out


def load_bridge(data_root: Path, include_nomenclature: bool = True) -> Mapping[str, BridgeEntry]:
    """``{bafu_flow_code: BridgeEntry}``; packages apply in ``metadata.json`` order, first wins."""
    folder = Path(data_root) / REPO_MAPPINGS / "data" / BRIDGE_FOLDER
    if not folder.is_dir():
        raise data_root_error("bridge folder", folder)
    merged: dict[str, BridgeEntry] = {}
    for path, is_nomenclature in _ordered_packages(folder, include_nomenclature):
        for entry in _entries(json.loads(path.read_text())):
            code = entry["source"]["code"]
            if code in merged:
                continue
            merged[code] = BridgeEntry(
                target_code=entry["target"]["code"],
                target_unit=str(entry["target"].get("unit", "")),
                conversion_factor=float(entry.get("conversion_factor", 1.0)),
                nomenclature=is_nomenclature,
            )
    return MappingProxyType(merged)
