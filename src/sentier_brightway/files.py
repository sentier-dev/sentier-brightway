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
from .build import BuildResult
from .constants import BRIDGE_FOLDER, CITATION, REPO_MAPPINGS
from .datapackage import PACKAGE_DIR, REGISTRY_DIR, write_datapackages
from .registry import build_registry, write_registry

LAYOUT_VERSION = "1"
MAPPINGS_DIR = "mappings"


class ExistingOutputError(RuntimeError):
    """``out_dir`` is not empty and ``overwrite`` is False."""


def _prepare(out_dir: Path, overwrite: bool) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        if not overwrite:
            raise ExistingOutputError(f"{out_dir} is not empty; pass overwrite=True to replace it")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _copy_mappings(data_root: Path, out_dir: Path) -> list[str]:
    """Copy every ``*.json`` from the bridge folder (metadata, packages, sidecars) and return
    the biosphere package file names listed in the copied ``metadata.json``, in file order."""
    src = Path(data_root) / REPO_MAPPINGS / "data" / BRIDGE_FOLDER
    if not src.is_dir():
        raise data_root_error("bridge folder", src)
    dst = out_dir / MAPPINGS_DIR / BRIDGE_FOLDER
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.json")):
        shutil.copyfile(path, dst / path.name)
    meta = json.loads((dst / "metadata.json").read_text())
    return [item["file"] for item in meta.get("packages", [])]


def _pins() -> list[dict]:
    try:
        from .fetch import load_packaged_manifest

        return [{"name": s.name, "repo": s.repo, "ref": s.ref} for s in load_packaged_manifest()]
    except Exception:  # manifest absent in a dev checkout before Task 10 ran
        return []


def _manifest(
    result: BuildResult, registry, datapackages: bool, bridge_packages: list[str]
) -> dict:
    return {
        "layout_version": LAYOUT_VERSION,
        "sentier_brightway_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "citation": CITATION,
        "sources": _pins(),
        "bridge_folder": BRIDGE_FOLDER,
        "bridge_packages": bridge_packages,
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
) -> Path:
    out_dir = _prepare(out_dir, overwrite)
    registry = build_registry(result)
    write_registry(registry, out_dir / REGISTRY_DIR)
    bridge_packages = _copy_mappings(data_root, out_dir)
    if datapackages:
        write_datapackages(registry, out_dir / PACKAGE_DIR)
    manifest = _manifest(result, registry, datapackages, bridge_packages)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=list))
    return out_dir
