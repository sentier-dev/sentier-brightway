import importlib.metadata
import json
import warnings

import pytest

import sentier_brightway
from sentier_brightway import cli, coverage, import_bafu_files


def test_coverage_api_needs_no_brightway(data_root):
    with pytest.warns(UserWarning, match="conflicting units"):  # the fixture's B4 -> E1 entry
        cov = coverage(data_root=data_root)
    assert (cov.flows_used, cov.flows_mapped, cov.flows_nomenclature) == (3, 3, 1)
    assert coverage(data_root=data_root, include_nomenclature=False).flows_mapped == 2


def test_cli_coverage_prints_report_and_citation(data_root, capsys):
    rc = cli.main(["coverage", "--data-root", str(data_root), "--skip-nomenclature"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2/3 BAFU flows" in out and "BAFU:2026" in out


def test_cli_coverage_reports_unit_conflicts_once(data_root, capsys, recwarn):
    rc = cli.main(["coverage", "--data-root", str(data_root)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 EF flows targeted with conflicting units" in out
    assert not [w for w in recwarn if "conflicting units" in str(w.message)]


def test_cli_db_requires_project(data_root):
    with pytest.raises(SystemExit):
        cli.main(["db", "--data-root", str(data_root)])


def test_cli_reports_missing_data_root_as_error(tmp_path, capsys):
    rc = cli.main(["coverage", "--data-root", str(tmp_path / "nowhere")])
    assert rc == 2
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.bw
def test_cli_db_round_trip(bw_project, data_root, capsys):
    rc = cli.main(["db", "--project", "cli-test", "--data-root", str(data_root)])
    assert rc == 0
    assert "Installed bafu-2026: 2 processes" in capsys.readouterr().out
    rc = cli.main(["db", "--project", "cli-test", "--data-root", str(data_root)])
    assert rc == 2
    assert "overwrite" in capsys.readouterr().err


@pytest.mark.bw
def test_cli_db_shows_method_progress_on_stderr(bw_project, data_root, capsys):
    rc = cli.main(["db", "--project", "cli-test", "--data-root", str(data_root)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "writing method 1/2" in err and "writing method 2/2" in err
    cli.main(["db", "--project", "cli-test", "--data-root", str(data_root), "--overwrite"])
    assert capsys.readouterr().err.count("writing method 1/2") == 1  # no duplicate handlers


def test_cli_lets_other_user_warnings_through(data_root, monkeypatch):
    real_run = cli._run

    def warn_then_run(args):
        warnings.warn("bw2data says something", UserWarning, stacklevel=1)
        return real_run(args)

    monkeypatch.setattr(cli, "_run", warn_then_run)
    with pytest.warns(UserWarning, match="bw2data says something"):
        assert cli.main(["coverage", "--data-root", str(data_root)]) == 0


def test_import_bafu_files_api(data_root, tmp_path):
    cov = import_bafu_files(tmp_path / "out", data_root=data_root)
    assert (tmp_path / "out/registry/exchanges.parquet").is_file()
    assert (tmp_path / "out/bw_package/bafu-2026/datapackage.json").is_file()
    assert cov.processes == 2


def test_cli_files_subcommand(data_root, tmp_path, capsys):
    out_dir = tmp_path / "out"
    rc = cli.main(
        ["files", "--out", str(out_dir), "--data-root", str(data_root), "--no-datapackages"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert (out_dir / "manifest.json").is_file()
    assert not (out_dir / "bw_package").exists()
    assert "BAFU:2026" in out
    assert f"Files written to {out_dir.resolve()}" in out


def test_cli_files_requires_out(data_root):
    with pytest.raises(SystemExit):
        cli.main(["files", "--data-root", str(data_root)])


def test_cli_files_refuses_non_empty_out_without_overwrite(data_root, tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "foreign.txt").write_text("x")
    rc = cli.main(["files", "--out", str(out_dir), "--data-root", str(data_root)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "ERROR:" in err and "not empty" in err and "--overwrite" in err
    # --overwrite never deletes a folder that is not a previous export
    rc = cli.main(["files", "--out", str(out_dir), "--data-root", str(data_root), "--overwrite"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "ERROR:" in err and "does not look like a previous sentier-brightway export" in err
    assert (out_dir / "foreign.txt").is_file()


def test_cli_files_overwrite_replaces_previous_export(data_root, tmp_path, capsys):
    out_dir = tmp_path / "out"
    args = ["files", "--out", str(out_dir), "--data-root", str(data_root), "--no-datapackages"]
    assert cli.main(args) == 0
    (out_dir / "stale.txt").write_text("x")
    assert cli.main(args) == 2
    assert cli.main(args + ["--overwrite"]) == 0
    assert not (out_dir / "stale.txt").exists()
    assert (out_dir / "manifest.json").is_file()


def test_cli_files_out_is_a_file(data_root, tmp_path, capsys):
    out = tmp_path / "out"
    out.write_text("x")
    rc = cli.main(["files", "--out", str(out), "--data-root", str(data_root), "--overwrite"])
    assert rc == 2
    assert "ERROR:" in capsys.readouterr().err and out.read_text() == "x"


def test_cli_files_out_is_a_symlink(data_root, tmp_path, capsys):
    target = tmp_path / "target"
    target.mkdir()
    out = tmp_path / "out"
    out.symlink_to(target)
    rc = cli.main(["files", "--out", str(out), "--data-root", str(data_root), "--overwrite"])
    assert rc == 2
    assert "ERROR:" in capsys.readouterr().err and out.is_symlink()


def test_cli_files_out_under_a_file_is_a_clean_error(data_root, tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    rc = cli.main(["files", "--out", str(blocker / "out"), "--data-root", str(data_root)])
    assert rc == 2  # NotADirectoryError from mkdir, an OSError
    assert "ERROR:" in capsys.readouterr().err


def test_cli_files_skip_nomenclature_is_recorded_in_manifest(data_root, tmp_path):
    out_dir = tmp_path / "out"
    rc = cli.main(
        [
            "files",
            "--out",
            str(out_dir),
            "--data-root",
            str(data_root),
            "--no-datapackages",
            "--skip-nomenclature",
        ]
    )
    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["include_nomenclature"] is False
    assert manifest["bridge_packages"] == ["biosphere-1-curated.json"]


def test_import_bafu_files_resolves_data_root_once(data_root, tmp_path, monkeypatch):
    calls = []
    real = sentier_brightway.resolve_data_root

    def counting(arg):
        calls.append(arg)
        return real(arg)

    monkeypatch.setattr(sentier_brightway, "resolve_data_root", counting)
    import_bafu_files(tmp_path / "out", data_root=data_root, datapackages=False)
    assert len(calls) == 1


def test_version_matches_installed_metadata():
    assert sentier_brightway.__version__ == importlib.metadata.version("sentier-brightway")
    assert sentier_brightway.__version__ != "0.0.0"


def test_version_falls_back_when_not_installed(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    from sentier_brightway import _version

    assert _version._version() == _version.FALLBACK_VERSION == "0.1.0"


def test_version_module_is_the_single_source():
    from sentier_brightway._version import __version__

    assert sentier_brightway.__version__ == __version__
    assert __version__ == importlib.metadata.version("sentier-brightway")
