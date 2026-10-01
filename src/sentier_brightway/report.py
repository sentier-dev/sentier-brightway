"""What got linked, what did not, and the citation the user must carry."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import BIOSPHERE_DB, DEFAULT_SOURCE, citation, inventory_db, residual_db


@dataclass(frozen=True)
class Coverage:
    flows_used: int  # distinct BAFU flow codes appearing in biosphere exchanges
    flows_mapped: int  # of those, relinked to an EF flow
    exchange_rows: int  # biosphere exchange rows
    exchange_rows_mapped: int
    residual_by_compartment: tuple[tuple[str, int], ...]  # (compartment, unmapped flow count)
    processes: int
    methods: int
    # subset of flows_mapped: linked, but the EF target has no factor (impact zero)
    flows_nomenclature: int = 0
    # EF flows targeted by bridge entries that disagree on the target unit (first wins)
    unit_conflicts: int = 0
    # inventory source the install was built from, and the database names derived from it
    source: str = DEFAULT_SOURCE
    inventory_db: str = inventory_db(DEFAULT_SOURCE)
    residual_db: str = residual_db(DEFAULT_SOURCE)

    @property
    def flow_share(self) -> float:
        return self.flows_mapped / self.flows_used if self.flows_used else 0.0

    @property
    def exchange_share(self) -> float:
        return self.exchange_rows_mapped / self.exchange_rows if self.exchange_rows else 0.0


def render(cov: Coverage) -> str:
    residual_lines = [f"  {comp}: {n}" for comp, n in cov.residual_by_compartment] or ["  none"]
    conflict_lines = []
    if cov.unit_conflicts:
        conflict_lines = [
            f"  {cov.unit_conflicts} EF flows targeted with conflicting units "
            "(check sentier-mappings)"
        ]
    lines = [
        f"Installed {cov.inventory_db}: {cov.processes} processes",
        f"Installed {BIOSPHERE_DB} and {cov.methods} EF 3.1 methods",
        f"Linked {cov.flows_mapped}/{cov.flows_used} {cov.source} flows to EF 3.1 "
        f"({cov.flow_share:.1%}); {cov.exchange_rows_mapped}/{cov.exchange_rows} biosphere "
        f"exchanges ({cov.exchange_share:.1%})",
        f"  {cov.flows_nomenclature} of the linked flows point at EF flows with no factor "
        "(nomenclature only, impact zero)",
        *conflict_lines,
        f"Unlinked flows kept in {cov.residual_db} (no EF 3.1 counterpart in the bridge):",
        *residual_lines,
        "",
        citation(cov.source),
    ]
    return "\n".join(lines)
