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
    assert "-0.0000" not in path.read_text()


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
    assert meta["location_aliases_applied"] == 0
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


def test_outlier_reasons_is_valid_json_keyed_by_known_shorts(tmp_path):
    path = tmp_path / emit.OUTLIER_REASONS
    emit.write_outlier_reasons(path)
    notes = json.loads(path.read_text(encoding="utf-8"))
    assert set(notes) <= set(shorts())
    assert {"ht_c", "ht_c_inorg", "water", "radiation"} <= set(notes)
    assert "ht_c_org" not in notes
    for note in notes.values():
        assert note["short"] and note["long"] and note["impact_level"] is True
        assert note["count"] == 0 and note["not_a_bug"] is True
    assert "Cr(VI)" in notes["ht_c"]["long"] and notes["ht_c"] == notes["ht_c_inorg"]


def test_outlier_reasons_rejects_unknown_short(tmp_path, monkeypatch):
    monkeypatch.setitem(emit.OUTLIER_NOTES, "not_a_cat", {"short": "x"})
    with pytest.raises(ValueError, match="not_a_cat"):
        emit.write_outlier_reasons(tmp_path / "r.json")
    assert not (tmp_path / "r.json").exists()


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
        "sector",
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


def test_meta_counts_location_aliases(tmp_path):
    scores = _scores().assign(location=["ERCOT", "CH", "GLO"])
    reference = _reference().assign(location=["US-ERCOT", "CH", "DE"])
    compared = compare(align(scores, reference, CATS), CATS)
    emit.write_meta(compared, CATS, tmp_path / "meta.json")
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["location_aliases_applied"] == 1
    assert meta["n_common"] == 2


def test_vs_csv_writes_no_negative_zero(tmp_path):
    scores = _scores().assign(climate=[2.0 * (1 - 1e-7), 0.5, 1.0])
    compared = compare(align(scores, _reference(), CATS), CATS)
    path = tmp_path / "vs_bafu.csv"
    emit.write_vs_csv(compared, CATS, path)
    text = path.read_text()
    assert "-0.0000" not in text
    assert _read(path)["climate"].iloc[0] == "0.0000"


def test_boxes_json_constants_and_shape(tmp_path):
    assert emit.BOXES_JSON == "boxes.json" and emit.WORST_DIR == "worst" and emit.WORST_N == 200
    path = tmp_path / emit.BOXES_JSON
    emit.write_boxes(_compared(), CATS, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {"baseline", "sectors", "categories", "boxes"}
    assert payload["baseline"] == emit.BASELINE
    assert payload["sectors"] == ["all", "electricity"]
    assert payload["categories"] == SHORTS
    assert payload["boxes"]["all"]["climate"]["n"] == 2
    assert payload["boxes"]["all"]["water"]["median"] is None


def test_worst_dir_has_one_file_per_category(tmp_path):
    folder = tmp_path / emit.WORST_DIR
    emit.write_worst(_compared(), CATS, folder)
    assert sorted(p.name for p in folder.iterdir()) == sorted(f"{s}.json" for s in SHORTS)
    climate = json.loads((folder / "climate.json").read_text(encoding="utf-8"))
    assert isinstance(climate, list) and len(climate) <= emit.WORST_N
    assert [row["code"] for row in climate] == [P2, P1]
    assert set(climate[0]) == {"code", "name", "location", "sector", "unit", "ours", "ref", "pct"}
    assert json.loads((folder / "water.json").read_text(encoding="utf-8")) == []


def test_worst_lists_are_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(emit, "WORST_N", 1)
    emit.write_worst(_compared(), CATS, tmp_path / "worst")
    assert len(json.loads((tmp_path / "worst" / "climate.json").read_text())) == 1


def test_boxes_and_worst_are_deterministic(tmp_path):
    for i in (1, 2):
        emit.write_boxes(_compared(), CATS, tmp_path / f"boxes{i}.json")
        emit.write_worst(_compared(), CATS, tmp_path / f"worst{i}")
    assert (tmp_path / "boxes1.json").read_bytes() == (tmp_path / "boxes2.json").read_bytes()
    for short in SHORTS:
        a = (tmp_path / "worst1" / f"{short}.json").read_bytes()
        assert a == (tmp_path / "worst2" / f"{short}.json").read_bytes()
    text = (tmp_path / "boxes1.json").read_text(encoding="utf-8")
    assert text.index('"baseline"') < text.index('"boxes"') < text.index('"categories"')
