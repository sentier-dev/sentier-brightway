"""A non-default inventory ``source`` flows from the parquet tag to every output name."""

import json

import pandas as pd
import pytest

from sentier_brightway import assemble, cli, coverage, import_files
from sentier_brightway.constants import DEFAULT_SOURCE, SOURCE_IRI_PREFIX, citation
from sentier_brightway.datapackage import inventory_folder, load_inventory_datapackage
from sentier_brightway.report import render
from tests.conftest import B3, P1, P2

OTHER = "other-1"
SECTOR = "sentier-inventory/data/02-electricity"


@pytest.fixture
def other_root(data_root):
    """The fixture inventory relabelled as source ``other-1`` (rows, metadata, vocab IRI)."""
    path = data_root / SECTOR / "processes.parquet"
    proc = pd.read_parquet(path)
    proc["source"] = OTHER
    proc["source_version"] = "2025"
    proc.to_parquet(path, index=False)
    meta_path = data_root / SECTOR / "metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["sources"] = [OTHER]
    meta_path.write_text(json.dumps(meta))
    folder = data_root / "sentier-vocab" / "data" / "elementary-flows"
    for shard in folder.glob("*.parquet"):
        df = pd.read_parquet(shard)
        df["source"] = df["source"].replace(
            {SOURCE_IRI_PREFIX + DEFAULT_SOURCE: SOURCE_IRI_PREFIX + OTHER}
        )
        df.to_parquet(shard, index=False)
    return data_root


def test_default_build_is_named_after_bafu(data_root):
    with pytest.warns(UserWarning, match="conflicting units"):
        result = assemble(data_root)
    assert (result.source, result.source_version) == (DEFAULT_SOURCE, "v1")
    assert (result.inventory_db, result.residual_db) == ("bafu-2026", "bafu-2026-residual")
    assert result.coverage.inventory_db == "bafu-2026"
    node = result.inventory[("bafu-2026", P1)]
    assert (node["source"], node["source_version"]) == ("bafu-2026", "v1")


def test_default_source_is_absent_from_relabelled_root(other_root):
    with pytest.raises(ValueError, match="source='bafu-2026'") as exc_info:
        assemble(other_root)
    assert OTHER in str(exc_info.value)


def test_build_names_databases_after_the_source(other_root):
    result = assemble(other_root, include_nomenclature=False, source=OTHER)
    assert (result.source, result.source_version) == (OTHER, "2025")
    assert (result.inventory_db, result.residual_db) == (OTHER, f"{OTHER}-residual")
    assert set(result.inventory) == {(OTHER, P1), (OTHER, P2)}
    assert set(result.residual) == {(f"{OTHER}-residual", B3)}
    by_input = {e["input"]: e for e in result.inventory[(OTHER, P1)]["exchanges"]}
    assert by_input[(OTHER, P2)]["type"] == "technosphere"
    assert by_input[(f"{OTHER}-residual", B3)]["type"] == "biosphere"
    assert result.inventory[(OTHER, P1)]["source"] == OTHER


def test_coverage_report_uses_source_names_and_fallback_citation(other_root):
    cov = coverage(other_root, include_nomenclature=False, source=OTHER)
    assert (cov.source, cov.inventory_db, cov.residual_db) == (OTHER, OTHER, f"{OTHER}-residual")
    text = render(cov)
    assert f"Installed {OTHER}: 2 processes" in text
    assert f"kept in {OTHER}-residual" in text
    assert text.endswith(citation(OTHER)) and citation(OTHER) == "Source: other-1."
    assert "BAFU" not in text


def test_files_mode_folder_and_manifest_follow_the_source(other_root, tmp_path):
    out = tmp_path / "out"
    cov = import_files(out, data_root=other_root, include_nomenclature=False, source=OTHER)
    assert cov.processes == 2
    assert (out / f"bw_package/{OTHER}/datapackage.json").is_file()
    assert not (out / "bw_package/bafu-2026").exists()
    assert inventory_folder(out) == out / "bw_package" / OTHER
    dp = load_inventory_datapackage(out)
    assert dp.metadata["name"] == OTHER
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["source"] == OTHER
    assert manifest["source_version"] == "2025"
    assert (manifest["inventory_db"], manifest["residual_db"]) == (OTHER, f"{OTHER}-residual")
    assert manifest["citation"] == citation(OTHER)
    registry = pd.read_parquet(out / "registry/processes.parquet")
    assert set(registry["database"]) == {OTHER}


def test_cli_source_flag_reaches_assemble(other_root, capsys):
    rc = cli.main(
        ["coverage", "--data-root", str(other_root), "--source", OTHER, "--skip-nomenclature"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert f"Installed {OTHER}: 2 processes" in out


def test_cli_default_source_errors_on_relabelled_root(other_root, capsys):
    rc = cli.main(["coverage", "--data-root", str(other_root)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "source='bafu-2026'" in err and OTHER in err


@pytest.mark.bw
def test_db_mode_writes_databases_named_after_the_source(other_root, bw_project):
    bd = pytest.importorskip("bw2data")
    from sentier_brightway import import_db

    import_db(bw_project, data_root=other_root, include_nomenclature=False, source=OTHER)
    assert {OTHER, f"{OTHER}-residual", "ef-3.1-biosphere"} <= set(bd.databases)
    assert "bafu-2026" not in bd.databases
    assert len(bd.Database(OTHER)) == 2
    assert len(bd.Database(f"{OTHER}-residual")) == 1
