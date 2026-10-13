"""Unit multipliers preserve the signed distributions in actual file exports."""

import json
import math

import pandas as pd
import pytest

from sentier_brightway import import_files
from sentier_brightway.constants import METHODS_FOLDER, REPO_METHODS
from tests.conftest import B2, CLIMATE, E2


@pytest.mark.parametrize(
    "source_unit,target_unit,factor",
    [
        ("Bq", "kBq", 0.001),
        ("km", "m", 1000),
        ("kWh", "MJ", 3.6),
    ],
)
@pytest.mark.parametrize("uncertainty_type", [2, 3])
@pytest.mark.parametrize("sign", [1, -1])
def test_file_export_applies_conversion_once_to_amount_and_distribution(
    data_root, tmp_path, source_unit, target_unit, factor, uncertainty_type, sign
):
    path = data_root / "sentier-mappings/data/bafu-2026-v1__ef-3.1/biosphere-1-curated.json"
    package = json.loads(path.read_text())
    row = package["replace"][1]
    row["source"]["unit"] = source_unit
    row["target"]["unit"] = target_unit
    row["conversion_factor"] = factor
    path.write_text(json.dumps(package))

    path = data_root / "sentier-inventory/data/02-electricity/exchanges.parquet"
    frame = pd.read_parquet(path)
    selected = frame["flow"] == B2
    loc = math.log(1000) if uncertainty_type == 2 else sign * 1000
    scale = 0.2 if uncertainty_type == 2 else 25
    bounds = (800, 1200) if sign == 1 else (-1200, -800)
    # Replace all-null string bounds with numeric columns, as an input with
    # bounds would store them. No production/technosphere rows are modified.
    frame["minimum"] = pd.Series(float("nan"), index=frame.index)
    frame["maximum"] = pd.Series(float("nan"), index=frame.index)
    frame.loc[
        selected, ["unit", "amount", "uncertainty_type", "loc", "scale", "minimum", "maximum"]
    ] = [
        source_unit,
        sign * 1000,
        uncertainty_type,
        loc,
        scale,
        *bounds,
    ]
    frame.to_parquet(path, index=False)

    out = tmp_path / "export"
    import_files(out, data_root=data_root, include_nomenclature=False, datapackages=False)
    exchanges = pd.read_parquet(out / "registry/exchanges.parquet")
    (exported,) = exchanges[exchanges["input_code"] == E2].to_dict("records")
    assert exported["amount"] == pytest.approx(sign * 1000 * factor)
    assert exported["loc"] == pytest.approx(
        loc + math.log(factor) if uncertainty_type == 2 else loc * factor
    )
    assert exported["scale"] == pytest.approx(scale if uncertainty_type == 2 else scale * factor)
    assert exported["minimum"] == pytest.approx(bounds[0] * factor)
    assert exported["maximum"] == pytest.approx(bounds[1] * factor)
    if sign == -1 and uncertainty_type == 2:
        assert exported["negative"] is True
    else:
        assert pd.isna(exported["negative"])
    biosphere = pd.read_parquet(out / "registry/biosphere.parquet")
    assert exported["unit"] == biosphere[biosphere["code"] == E2].iloc[0]["unit"]


def test_explicit_zero_cf_survives_direct_mapping_export(data_root, tmp_path):
    path = data_root / REPO_METHODS / "data" / METHODS_FOLDER / "characterization-factors.parquet"
    frame = pd.read_parquet(path)
    frame.loc[frame["method_id"] == CLIMATE, "factor_value"] = 0.0
    frame.to_parquet(path, index=False)
    out = tmp_path / "export"
    import_files(out, data_root=data_root, include_nomenclature=False, datapackages=False)
    factors = pd.read_parquet(out / "registry/characterization-factors.parquet")
    climate = factors[factors["method_id"] == CLIMATE]
    assert len(climate) == 1
    assert climate.iloc[0]["factor"] == 0.0
