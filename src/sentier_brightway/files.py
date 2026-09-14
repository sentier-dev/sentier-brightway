"""Write the file-mode output folder: registry parquet, applied mappings, datapackages,
manifest."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from ._frames import data_root_error
from .bridge import applied_packages
from .build import BuildResult
from .constants import BRIDGE_FOLDER, CITATION, REPO_MAPPINGS
from .datapackage import PACKAGE_DIR, REGISTRY_DIR, write_datapackages
from .fetch import load_packaged_manifest
from .registry import build_registry, write_registry

LAYOUT_VERSION = "1"
MAPPINGS_DIR = "mappings"


class ExistingOutputError(RuntimeError):
    """``out_dir`` cannot be (re)used: it is a file or symlink, it is not empty and
    ``overwrite`` is False, or ``overwrite`` is True but it is not a previous export."""


def _is_previous_export(out_dir: Path) -> bool:
    """True when ``out_dir/manifest.json`` parses as JSON and carries ``layout_version``."""
    manifest = out_dir / "manifest.json"
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "layout_version" in data


def _prepare(out_dir: Path, overwrite: bool) -> Path:
    """Make ``out_dir`` an empty directory; ``overwrite`` only ever deletes a previous export."""
    out_dir = Path(out_dir)
    if out_dir.is_symlink():
        raise ExistingOutputError(f"{out_dir} is a symlink; choose a plain directory as --out")
    if out_dir.is_file():
        raise ExistingOutputError(f"{out_dir} is a file; choose a directory as --out")
    if out_dir.is_dir() and any(out_dir.iterdir()):
        if not overwrite:
            raise ExistingOutputError(
                f"{out_dir} is not empty; pass overwrite=True (CLI: --overwrite) to replace it"
            )
        if not _is_previous_export(out_dir):
            raise ExistingOutputError(
                f"{out_dir} is not empty and does not look like a previous sentier-brightway "
                "export (no manifest.json); refusing to delete it. Remove it yourself or "
                "choose another --out"
            )
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _copy_mappings(data_root: Path, out_dir: Path) -> None:
    """Copy every ``*.json`` of the bridge folder (metadata, packages, sidecars) verbatim."""
    src = Path(data_root) / REPO_MAPPINGS / "data" / BRIDGE_FOLDER
    if not src.is_dir():
        raise data_root_error("bridge folder", src)
    dst = out_dir / MAPPINGS_DIR / BRIDGE_FOLDER
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.json")):
        shutil.copyfile(path, dst / path.name)


def _pins() -> list[dict]:
    return [{"name": s.name, "repo": s.repo, "ref": s.ref} for s in load_packaged_manifest()]


def _manifest(
    result: BuildResult,
    registry,
    datapackages: bool,
    include_nomenclature: bool,
    bridge_packages: tuple[str, ...],
) -> dict:
    return {
        "layout_version": LAYOUT_VERSION,
        "sentier_brightway_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "citation": CITATION,
        "sources": _pins(),
        "bridge_folder": BRIDGE_FOLDER,
        "include_nomenclature": include_nomenclature,
        "bridge_packages": list(bridge_packages),
        "coverage": asdict(result.coverage),
        "counts": {
            "processes": len(registry.processes),
            "biosphere": len(registry.biosphere),
            "exchanges": len(registry.exchanges),
            "methods": len(registry.methods),
        },
        "datapackages": datapackages,
    }


def write_files(
    result: BuildResult,
    data_root: Path,
    out_dir: Path,
    datapackages: bool = True,
    overwrite: bool = False,
    include_nomenclature: bool = True,
) -> Path:
    """Write the output folder. ``include_nomenclature`` must match the value ``result`` was
    built with; it is recorded in the manifest together with the packages actually applied."""
    bridge_packages = applied_packages(data_root, include_nomenclature)
    out_dir = _prepare(out_dir, overwrite)
    registry = build_registry(result)
    write_registry(registry, out_dir / REGISTRY_DIR)
    _copy_mappings(data_root, out_dir)
    if datapackages:
        write_datapackages(registry, out_dir / PACKAGE_DIR)
    manifest = _manifest(result, registry, datapackages, include_nomenclature, bridge_packages)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=list))
    return out_dir
