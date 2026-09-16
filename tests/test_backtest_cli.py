import json
import subprocess
import sys

import pandas as pd
import pytest

from sentier_brightway import cli
from sentier_brightway.backtest import FIXTURE_CATEGORIES, render_summary, run_backtest
from tests.conftest import IONISING, P1


def test_fixture_categories_are_climate_plus_fixture_radiation():
    assert [c.short for c in FIXTURE_CATEGORIES] == ["climate", "radiation"]
    assert FIXTURE_CATEGORIES[1].method_id == IONISING


def test_run_backtest_writes_everything(files_export, bafu_xlsx, tmp_path):
    result = run_backtest(
        files_export, bafu_xlsx, tmp_path / "dash", categories=FIXTURE_CATEGORIES
    )
    for name in (
        "emissions.csv",
        "vs_bafu.csv",
        "vs_bafu_meta.json",
        "run_report.json",
        "backtest/summary.parquet",
    ):
        assert (tmp_path / "dash" / name).is_file()
    vs = pd.read_csv(tmp_path / "dash" / "vs_bafu.csv", keep_default_na=False)
    assert abs(float(vs.set_index("code").loc[P1, "climate"])) < 1e-6  # ours/3.6 == ref per MJ
    assert result.summary.set_index("short").loc["climate", "n_compared"] == 2
    assert (result.n_mapped, result.n_unmatched, result.n_unit_skipped) == (2, 0, 0)
    assert result.out_dir == tmp_path / "dash"
    report = json.loads((tmp_path / "dash" / "run_report.json").read_text())
    assert report["counts"]["processes"] == 2 and report["sources"]
    assert report["counts"]["mapped"] == 2 and report["counts"]["reference_rows"] == 3
    assert set(report["timings_s"]) >= {"reference_s", "score_s", "check_s"}
    text = render_summary(result)
    assert "mapped 2, unmatched 0, unit skipped 0" in text and "climate" in text


def test_cli_backtest_with_existing_export(files_export, bafu_xlsx, tmp_path, capsys):
    rc = cli.main(
        [
            "backtest",
            "--out",
            str(tmp_path / "dash"),
            "--xlsx",
            str(bafu_xlsx),
            "--files",
            str(files_export),
            "--fixture-categories",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "climate" in out and "BAFU:2026" in out
    assert (tmp_path / "dash" / "vs_bafu.csv").is_file()
    assert not (tmp_path / "dash" / "files").exists()  # no implicit export


def test_cli_backtest_runs_export_when_files_missing(data_root, bafu_xlsx, tmp_path):
    rc = cli.main(
        [
            "backtest",
            "--out",
            str(tmp_path / "dash"),
            "--xlsx",
            str(bafu_xlsx),
            "--data-root",
            str(data_root),
            "--fixture-categories",
        ]
    )
    assert rc == 0
    assert (tmp_path / "dash" / "files" / "manifest.json").is_file()
    assert (tmp_path / "dash" / "vs_bafu.csv").is_file()


def test_cli_backtest_missing_xlsx_is_an_error(files_export, tmp_path, capsys):
    rc = cli.main(
        [
            "backtest",
            "--out",
            str(tmp_path / "dash"),
            "--xlsx",
            str(tmp_path / "nope.xlsx"),
            "--files",
            str(files_export),
        ]
    )
    assert rc == 2 and "ERROR:" in capsys.readouterr().err


def test_cli_backtest_hides_fixture_flag_from_help(capsys):
    try:
        cli.main(["backtest", "--help"])
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "--fixture-categories" not in out and "--xlsx" in out


def test_backtest_package_keeps_submodule_names():
    import types

    import sentier_brightway
    from sentier_brightway import backtest

    assert sentier_brightway.backtest is backtest
    for name in ("categories", "compare", "emit", "reference"):
        assert isinstance(getattr(backtest, name), types.ModuleType), name


def test_import_sentier_brightway_does_not_load_bw2calc():
    code = "import sentier_brightway, sys; print('bw2calc' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "False"


def test_run_backtest_missing_xlsx_creates_no_out_dir(files_export, tmp_path):
    with pytest.raises(FileNotFoundError):
        run_backtest(files_export, tmp_path / "nope.xlsx", tmp_path / "dash")
    assert not (tmp_path / "dash").exists()


def test_run_backtest_leaves_foreign_files_in_out_dir(files_export, bafu_xlsx, tmp_path):
    out = tmp_path / "dash"
    out.mkdir()
    (out / "notes.txt").write_text("keep me")
    run_backtest(files_export, bafu_xlsx, out, categories=FIXTURE_CATEGORIES)
    assert (out / "notes.txt").read_text() == "keep me"
    assert (out / "vs_bafu.csv").is_file()


def test_cli_backtest_files_at_non_export_folder_is_an_error(bafu_xlsx, tmp_path, capsys):
    (tmp_path / "junk").mkdir()
    rc = cli.main(
        [
            "backtest",
            "--out",
            str(tmp_path / "dash"),
            "--xlsx",
            str(bafu_xlsx),
            "--files",
            str(tmp_path / "junk"),
            "--fixture-categories",
        ]
    )
    assert rc == 2 and "ERROR:" in capsys.readouterr().err
    assert not (tmp_path / "dash").exists()
