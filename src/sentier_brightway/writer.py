"""The only module that touches bw2data. Writes the three databases and the methods."""

from __future__ import annotations

from .build import BuildResult
from .constants import BIOSPHERE_DB, INVENTORY_DB, RESIDUAL_DB

_ORDER = (BIOSPHERE_DB, RESIDUAL_DB, INVENTORY_DB)  # targets before the nodes that link to them


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


def write(result: BuildResult, project: str, overwrite: bool = False) -> None:
    bd = _bd()
    bd.projects.set_current(project)
    _guard(bd, overwrite)
    bd.Database(BIOSPHERE_DB).write(dict(result.biosphere))
    bd.Database(RESIDUAL_DB).write(dict(result.residual))
    bd.Database(INVENTORY_DB).write(dict(result.inventory))
    for method in result.methods:
        m = bd.Method(method.key)
        if not m.registered:
            m.register(
                unit=method.unit,
                description=method.description,
                sentier_method_id=method.method_id,
            )
        m.write(list(method.cfs))


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
    prepare = getattr(bd, "prepare_lca_inputs", None)
    if prepare is not None:
        fu, data_objs, _ = prepare({activity: 1.0}, method=method_key)
        lca = bc.LCA(fu, data_objs=data_objs)
    else:  # bw2data 3.x / bw2calc 1.x
        lca = bc.LCA({activity: 1.0}, method=method_key)
    lca.lci()
    lca.lcia()
    return float(lca.score)
