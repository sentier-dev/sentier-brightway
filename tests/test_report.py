import dataclasses

import pytest

from sentier_brightway.constants import CITATION
from sentier_brightway.report import Coverage, render


def test_ratios_and_rendering():
    cov = Coverage(
        flows_used=3,
        flows_mapped=2,
        exchange_rows=4,
        exchange_rows_mapped=3,
        residual_by_compartment=(("emissions to air", 1),),
        processes=2,
        methods=2,
        flows_nomenclature=1,
    )
    assert cov.flow_share == 2 / 3
    assert cov.exchange_share == 0.75
    text = render(cov)
    assert "2/3 BAFU flows" in text
    assert "3/4 biosphere exchanges" in text
    assert "emissions to air: 1" in text
    assert "1 of the linked flows point at EF flows with no factor" in text
    assert "(no EF 3.1 counterpart in the bridge)" in text
    assert CITATION in text


def test_zero_rows_do_not_divide_by_zero():
    cov = Coverage(0, 0, 0, 0, (), 0, 0)
    assert cov.flow_share == 0.0 and cov.exchange_share == 0.0


def test_coverage_is_frozen():
    cov = Coverage(0, 0, 0, 0, (), 0, 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cov.flows_used = 5


def test_multiple_residual_compartments_each_rendered():
    cov = Coverage(
        flows_used=5,
        flows_mapped=3,
        exchange_rows=5,
        exchange_rows_mapped=3,
        residual_by_compartment=(("emissions to air", 1), ("emissions to water", 2)),
        processes=1,
        methods=1,
    )
    text = render(cov)
    assert "emissions to air: 1" in text
    assert "emissions to water: 2" in text


def test_empty_residual_renders_none():
    cov = Coverage(
        flows_used=3,
        flows_mapped=3,
        exchange_rows=3,
        exchange_rows_mapped=3,
        residual_by_compartment=(),
        processes=1,
        methods=1,
    )
    text = render(cov)
    assert "  none" in text


def test_unit_conflicts_rendered_only_when_present():
    base = dict(
        flows_used=3,
        flows_mapped=3,
        exchange_rows=3,
        exchange_rows_mapped=3,
        residual_by_compartment=(),
        processes=1,
        methods=1,
    )
    assert Coverage(**base).unit_conflicts == 0
    assert "conflicting units" not in render(Coverage(**base))
    text = render(Coverage(**base, unit_conflicts=91))
    assert "91 EF flows targeted with conflicting units (check sentier-mappings)" in text
