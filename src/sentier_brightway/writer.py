"""The only module that touches bw2data. Writes the three databases and the methods."""

from __future__ import annotations

import logging

from .build import BoundMethod, BuildResult
from .constants import BIOSPHERE_DB, INVENTORY_DB, METHOD_PREFIX, RESIDUAL_DB

_ORDER = (BIOSPHERE_DB, RESIDUAL_DB, INVENTORY_DB)  # targets before the nodes that link to them
log = logging.getLogger(__name__)


class ExistingDatabaseError(RuntimeError):
    """The project already holds one of our databases and ``overwrite`` is False."""


def _bd():
    try:
        import bw2data as bd
    except ImportError as exc:  # pragma: no cover - exercised only in a bare environment
        raise ImportError(
            "bw2data is not installed in this Python environment. Run sentier-brightway from "
            "the environment where Brightway or Activity Browser is installed."
        ) from exc
    return bd


def _guard(bd, overwrite: bool) -> None:
    existing = [name for name in _ORDER if name in bd.databases]
    if existing and not overwrite:
        raise ExistingDatabaseError(
            f"project already has {existing}; pass overwrite=True or choose another project"
        )
    for name in reversed(_ORDER):  # dependents first
        if name in bd.databases:
            del bd.databases[name]


def _write_databases(bd, result: BuildResult) -> None:
    bd.Database(BIOSPHERE_DB).write(dict(result.biosphere))
    bd.Database(RESIDUAL_DB).write(dict(result.residual))
    bd.Database(INVENTORY_DB).write(dict(result.inventory))


def _write_methods(bd, methods: tuple[BoundMethod, ...], overwrite: bool) -> None:
    """Register (fresh metadata) and write every method; with ``overwrite`` also drop methods
    under our prefix that an older install left behind and this result no longer carries."""
    if overwrite:
        keep = {m.key for m in methods}
        for key in list(bd.methods):
            if tuple(key[: len(METHOD_PREFIX)]) == METHOD_PREFIX and key not in keep:
                bd.Method(key).deregister()
    for i, method in enumerate(methods, start=1):
        log.info("writing method %d/%d %s", i, len(methods), method.key)
        m = bd.Method(method.key)
        if m.registered:
            m.deregister()
        m.register(
            unit=method.unit,
            description=method.description,
            sentier_method_id=method.method_id,
        )
        m.write(list(method.cfs))


def _mark_dependents_dirty(bd) -> None:
    """Node ids change on every write, so other databases linking to ours must be
    reprocessed by bw2data before their next calculation."""
    ours = set(_ORDER)
    for name in list(bd.databases):
        if name not in ours and ours & set(bd.databases[name].get("depends", [])):
            bd.databases.set_dirty(name)


def write(result: BuildResult, project: str, overwrite: bool = False) -> None:
    """Write the three databases and the methods into ``project`` (created if missing).

    With ``overwrite`` a previous install is removed *before* the new one is written; if
    the write then fails part-way the project holds a partial set, and re-running with
    ``overwrite=True`` (CLI: ``--overwrite``) is the recovery step."""
    bd = _bd()
    if project not in bd.projects:
        log.info("creating Brightway project %r", project)
    bd.projects.set_current(project)
    _guard(bd, overwrite)
    try:
        _write_databases(bd, result)
        _write_methods(bd, result.methods, overwrite)
    except Exception as exc:
        raise RuntimeError(
            f"install into project {project!r} failed part-way ({exc}); the project now holds "
            f"a partial set of {list(_ORDER)}; re-run with overwrite=True (CLI: --overwrite)"
        ) from exc
    _mark_dependents_dirty(bd)


def get_node(database: str, code: str):
    """Resolve ``(database, code)`` on bw2data 3.x and 4.x alike."""
    bd = _bd()
    getter = getattr(bd, "get_node", None)
    if getter is not None:
        return getter(database=database, code=code)
    return bd.Database(database).get(code)


def score(activity, method_key: tuple[str, ...]) -> float:
    """One LCIA score with stock bw2calc; used by the smoke test and the CLI verify step."""
    import bw2calc as bc

    bd = _bd()
    if method_key not in bd.methods:
        raise KeyError(f"method {method_key} is not installed in project {bd.projects.current!r}")
    prepare = getattr(bd, "prepare_lca_inputs", None)
    if prepare is not None:
        fu, data_objs, _ = prepare({activity: 1.0}, method=method_key)
        lca = bc.LCA(fu, data_objs=data_objs)
    else:  # bw2data 3.x / bw2calc 1.x
        lca = bc.LCA({activity: 1.0}, method=method_key)
    lca.lci()
    lca.lcia()
    return float(lca.score)
