import json

import pandas as pd
import pytest

from sentier_brightway.backtest import emit
from sentier_brightway.backtest.categories import shorts
from sentier_brightway.backtest.compare import align, compare, summarise
from tests.conftest import P1, P2
from tests.test_backtest_compare import CATS, _reference, _scores

SHORTS = [c.short for c in CATS]


def _compared():
    return compare(align(_scores(), _reference(), CATS), CATS)


def _read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def test_emissions_csv_columns_and_rows(tmp_path):
    path = tmp_path / "emissions.csv"
    emit.write_emissions_csv(_scores(), align(_scores(), _reference(), CATS), CATS, path)
    df = _read(path)
    assert list(df.columns) == ["code", "name", "mapped_to", "type", "resolution", *SHORTS]
    assert df["code"].tolist() == [P1, P2, "x"]
    assert df["resolution"].tolist() == ["mapped", "mapped", "unmatched"]
    assert df["name"].tolist() == [
        "Electricity, low voltage, at grid - CH",
        "Electricity, medium voltage, at grid - CH",
        "Widget - GLO",
    ]
    assert df["mapped_to"].tolist() == [
        "Electricity, low voltage, at grid - CH",
        "Electricity, medium voltage, at grid - CH",
        "",
    ]
    assert df["type"].eq("").all()
    # mapped rows carry the converted value (per MJ), unmatched rows our raw score
    assert float(df["climate"].iloc[0]) == pytest.approx(2.0 / 3.6)
    assert float(df["climate"].iloc[2]) == 1.0
    assert float(df["acid"].iloc[1]) == pytest.approx(1e-9)
    assert df["water"].tolist()[1:] == ["", ""]  # NaN -> blank cell


def test_emissions_csv_raw_scores_for_unit_skipped_rows(tmp_path):
    scores = _scores().assign(unit=["kilowatt hour", "furlong", "kilogram"])
    path = tmp_path / "emissions.csv"
    emit.write_emissions_csv(scores, align(scores, _reference(), CATS), CATS, path)
    df = _read(path).set_index("code")
    assert df.loc[P2, "resolution"] == "unit_skipped"
    assert float(df.loc[P2, "climate"]) == 0.5  # our unit, unconverted
    assert df.loc[P2, "mapped_to"] == "Electricity, medium voltage, at grid - CH"


def test_vs_csv_has_ref_columns_and_blank_for_nan(tmp_path):
    path = tmp_path / "vs_bafu.csv"
    emit.write_vs_csv(_compared(), CATS, path)
    df = _read(path)
    assert list(df.columns) == [
        "code",
        "name",
        "mapped_to",
        "type",
        "resolution",
        "name_ref",
        "mapped_to_ref",
        *SHORTS,
    ]
    assert df["code"].tolist() == [P1, P2]  # mapped rows only
    assert df["resolution"].eq("mapped").all() and df["type"].eq("").all()
    assert df["name_ref"].iloc[0] == "Electricity, low voltage, at grid - CH"
    assert df["mapped_to_ref"].tolist() == ["MJ", "MJ"]
    assert float(df["climate"].iloc[1]) == pytest.approx(-100 / 11, abs=1e-3)
    assert df["acid"].tolist() == ["0.0000", "0.0000"]  # equal, near-zero floored
    assert df["water"].tolist() == ["", ""]  # zero reference / no score -> blank


def test_meta_and_run_report(tmp_path):
    compared = _compared()
    emit.write_meta(compared, CATS, tmp_path / "vs_bafu_meta.json")
    meta = json.loads((tmp_path / "vs_bafu_meta.json").read_text())
    assert meta["baseline"] == "BAFU-2026 v1 LCIA Results (openLCA, EF 3.1)"
    assert meta["n_common"] == 2
    assert meta["near_zero_factor"] == 0.01 and meta["fold_cap_pct"] == 1000.0
    assert meta["thresholds"]["acid"] == pytest.approx(2.5e-4, rel=1e-6)
    assert meta["suppressed"]["acid"] == {"near_zero": 1, "fold_capped": 0}
    assert meta["unmatched_ours"] == [["Widget", "GLO"]]
    assert meta["unmatched_ref"] == [["Other", "DE"]]
    assert meta["unit_skipped"] == {}
    emit.write_run_report(
        tmp_path / "run_report.json",
        pins=[{"name": "x", "repo": "y", "ref": "z"}],
        solver="scipy",
        timings={"score_s": 1.0},
        counts={"processes": 3},
    )
    report = json.loads((tmp_path / "run_report.json").read_text())
    assert report["sources"][0]["ref"] == "z"
    assert report["created"].endswith("+00:00")
    assert report["solver"] == "scipy" and report["timings_s"] == {"score_s": 1.0}
    assert report["counts"] == {"processes": 3}
    assert report["baseline"] == meta["baseline"]
    assert isinstance(report["sentier_brightway_version"], str)


def test_meta_lists_unit_skipped_pairs(tmp_path):
    scores = _scores().assign(unit=["kilowatt hour", "furlong", "kilogram"])
    compared = compare(align(scores, _reference(), CATS), CATS)
    emit.write_meta(compared, CATS, tmp_path / "meta.json")
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["unit_skipped"] == {"furlong -> MJ": 1}
    assert meta["n_common"] == 1


def test_parquet_bundle(tmp_path):
    compared = _compared()
    summary = summarise(compared, CATS)
    emit.write_parquet_bundle(_scores(), compared, summary, tmp_path / "backtest")
    folder = tmp_path / "backtest"
    for name in ("scores", "reference", "diff_pct", "summary"):
        assert (folder / f"{name}.parquet").is_file()
    pd.testing.assert_frame_equal(pd.read_parquet(folder / "scores.parquet"), _scores())
    reference = pd.read_parquet(folder / "reference.parquet")
    assert list(reference.columns) == [
        "code",
        "name",
        "location",
        "ref_unit",
        "resolution",
        *[f"{s}_ref" for s in SHORTS],
    ]
    assert len(reference) == 3
    diff = pd.read_parquet(folder / "diff_pct.parquet")
    assert list(diff.columns) == ["code", "short", "pct"]
    assert len(diff) == 2 * len(CATS)
    assert set(diff["short"]) == set(SHORTS)
    pd.testing.assert_frame_equal(pd.read_parquet(folder / "summary.parquet"), summary)


def test_all_shorts_helper_matches_categories():
    assert len(shorts()) == 25
