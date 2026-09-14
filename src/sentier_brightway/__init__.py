"""sentier-brightway: install Sentier data into a Brightway project."""

from __future__ import annotations

from pathlib import Path

from .bridge import load_bridge
from .build import BuildResult, build
from .fetch import resolve_data_root
from .flows import load_bafu_flows, load_ef_flows
from .inventory import load_inventory
from .methods import load_methods
from .report import Coverage, render

__version__ = "0.1.0"
__all__ = ["import_bafu_db", "coverage", "assemble", "render", "Coverage", "BuildResult"]


def assemble(
    data_root: Path | str | None = None, include_nomenclature: bool = True
) -> BuildResult:
    """Read the Sentier data (local root or verified download) and build the node dicts."""
    root = resolve_data_root(data_root)
    return build(
        inventory=load_inventory(root),
        ef_flows=load_ef_flows(root),
        bafu_flows=load_bafu_flows(root),
        bridge=load_bridge(root, include_nomenclature=include_nomenclature),
        methods=load_methods(root),
    )


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
