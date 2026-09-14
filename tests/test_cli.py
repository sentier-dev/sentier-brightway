import warnings

import pytest

from sentier_brightway import cli, coverage


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
