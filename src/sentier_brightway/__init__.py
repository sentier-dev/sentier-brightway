"""sentier-brightway: install Sentier data into a Brightway project."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

from .bridge import load_bridge
from .build import BuildResult, build
from .fetch import resolve_data_root
from .flows import load_bafu_flows, load_ef_flows
from .inventory import load_inventory
from .methods import load_methods
from .report import Coverage, render


def _version() -> str:
    """Installed distribution version; falls back for a source tree that is not installed."""
    try:
        return importlib.metadata.version("sentier-brightway")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


__version__ = _version()
__all__ = [
    "import_bafu_db",
    "import_bafu_files",
    "coverage",
    "assemble",
    "render",
    "Coverage",
    "BuildResult",
    "backtest",
]


def _assemble_from_root(root: Path, include_nomenclature: bool) -> BuildResult:
    """Build from an already resolved data root."""
    return build(
        inventory=load_inventory(root),
        ef_flows=load_ef_flows(root),
        bafu_flows=load_bafu_flows(root),
        bridge=load_bridge(root, include_nomenclature=include_nomenclature),
        methods=load_methods(root),
    )


def assemble(
    data_root: Path | str | None = None, include_nomenclature: bool = True
) -> BuildResult:
    """Read the Sentier data (local root or verified download) and build the node dicts."""
    return _assemble_from_root(resolve_data_root(data_root), include_nomenclature)


def coverage(data_root: Path | str | None = None, include_nomenclature: bool = True) -> Coverage:
    """Linking coverage without touching Brightway."""
    return assemble(data_root, include_nomenclature).coverage


def import_bafu_db(
    project: str,
    overwrite: bool = False,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
) -> Coverage:
    """Install BAFU-2026 + EF 3.1 biosphere + EF 3.1 methods into ``project``.

    Run inside the Python environment where Brightway / Activity Browser is installed.
    ``include_nomenclature=False`` keeps BAFU flows whose EF counterpart has no factor in
    the residual database instead of relinking them.

    With ``overwrite`` the previous install is removed before the new one is written; if
    the write fails part-way, re-running with ``overwrite=True`` (CLI: ``--overwrite``) is
    the recovery step.
    """
    from .writer import write  # bw2data import stays lazy

    result = assemble(data_root, include_nomenclature)
    write(result, project=project, overwrite=overwrite)
    return result.coverage


def import_bafu_files(
    out_dir: Path | str,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    datapackages: bool = True,
    overwrite: bool = False,
) -> Coverage:
    """Write BAFU-2026 + EF 3.1 as plain files instead of a bw2data project.

    ``out_dir`` receives ``registry/`` (parquet tables joined by integer ``bw_id``),
    ``mappings/`` (every JSON of the bridge folder, copied verbatim; ``manifest.bridge_packages``
    lists the packages that were applied and ``include_nomenclature`` says whether the order-4
    package was), ``bw_package/``
    (bw_processing datapackages for ``bw2calc.LCA`` with no bw2data project; skipped with
    ``datapackages=False``) and ``manifest.json``. Read them back with
    ``sentier_brightway.registry.load_registry`` and
    ``sentier_brightway.datapackage.load_inventory_datapackage`` /
    ``load_method_datapackage`` / ``score``.

    A non-empty ``out_dir`` is refused unless ``overwrite=True``, and even then only a
    previous export (a folder with a ``manifest.json``) is replaced; anything else is left
    alone.
    """
    from .files import write_files

    root = resolve_data_root(data_root)
    result = _assemble_from_root(root, include_nomenclature)
    write_files(
        result,
        data_root=root,
        out_dir=Path(out_dir),
        datapackages=datapackages,
        overwrite=overwrite,
        include_nomenclature=include_nomenclature,
    )
    return result.coverage


# backtest.emit reads __version__, so the subpackage is bound after it is defined
from . import backtest  # noqa: E402
