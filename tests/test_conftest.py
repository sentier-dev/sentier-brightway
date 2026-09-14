import json
import math

import pandas as pd

from tests.conftest import B1, B2, E1, E2, P1, P1_CLIMATE_SCORE, P1_IONISING_SCORE, P2


def test_fixture_layout(data_root):
    assert (data_root / "sentier-inventory/data/02-electricity/exchanges.parquet").is_file()
    assert (data_root / "sentier-vocab/data/elementary-flows/air-01.parquet").is_file()
    assert (data_root / "sentier-methods/data/01-ef-3.1/methods.parquet").is_file()
    assert (
        data_root / "sentier-mappings/data/bafu-2026-v1__ef-3.1/biosphere-1-curated.json"
    ).is_file()
    ex = pd.read_parquet(data_root / "sentier-inventory/data/02-electricity/exchanges.parquet")
    assert len(ex) == 8


def test_fixture_invariants(data_root):
    inventory = data_root / "sentier-inventory" / "data" / "02-electricity"
    methods = data_root / "sentier-methods" / "data" / "01-ef-3.1"
    bridge_folder = data_root / "sentier-mappings" / "data" / "bafu-2026-v1__ef-3.1"

    ex = pd.read_parquet(inventory / "exchanges.parquet")
    cf = pd.read_parquet(methods / "characterization-factors.parquet")
    bridge = json.loads((bridge_folder / "biosphere-1-curated.json").read_text())

    factor = {e["source"]["code"]: e.get("conversion_factor", 1.0) for e in bridge["replace"]}
    global_cf = cf[cf.location.isna()].set_index("flow").factor_value
    co2_cf = float(global_cf["https://vocab.sentier.dev/flows/" + E1])
    u_cf = float(global_cf["https://vocab.sentier.dev/flows/" + E2])

    def amount(process_id: str, flow: str) -> float:
        row = ex[(ex.process_id == process_id) & (ex.flow == flow)]
        return float(row.amount.iloc[0])

    p2_per_p1 = amount(P1, P2)
    climate = amount(P1, B1) * co2_cf + p2_per_p1 * amount(P2, B1) * co2_cf
    ionising = p2_per_p1 * amount(P2, B2) * factor[B2] * u_cf
    assert climate == P1_CLIMATE_SCORE
    assert ionising == P1_IONISING_SCORE

    lognormal = ex[ex.uncertainty_type == 2]
    for row in lognormal.itertuples():
        assert math.isclose(row.loc, math.log(abs(row.amount)), abs_tol=1e-3)

    meta = json.loads((bridge_folder / "metadata.json").read_text())
    assert [p["order"] for p in meta["packages"]] == sorted(p["order"] for p in meta["packages"])
