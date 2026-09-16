import dataclasses
import sys
from types import SimpleNamespace

import bw_processing as bwp
import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from sentier_brightway.backtest import scorer
from sentier_brightway.backtest.categories import Category, by_short
from sentier_brightway.backtest.scorer import Scores, check_against_loop, score_all
from sentier_brightway.datapackage import METHODS_DIR, PACKAGE_DIR, REGISTRY_DIR, method_slug
from sentier_brightway.datapackage import score as loop_score
from tests.conftest import CLIMATE, IONISING, P1, P1_CLIMATE_SCORE, P1_IONISING_SCORE, P2

# the fixture's ionising method id differs from the real one; score it under a test category
FIXTURE_CATS = (by_short("climate"), Category("radiation", IONISING, "Ionising Radiation", "x"))


def test_scores_every_process_for_available_methods(files_export):
    scores = score_all(files_export, FIXTURE_CATS)
    assert isinstance(scores, Scores)
    assert scores.values.shape == (2, 2)
    p1 = scores.frame.set_index("code").loc[P1]
    assert p1["climate"] == pytest.approx(P1_CLIMATE_SCORE, rel=1e-9)
    assert p1["radiation"] == pytest.approx(P1_IONISING_SCORE, rel=1e-9)
    p2 = scores.frame.set_index("code").loc[P2]
    assert p2["climate"] == pytest.approx(0.5, rel=1e-9)
    assert scores.solver in {"scipy", "pypardiso"}
    assert scores.elapsed_s >= 0


def test_missing_method_datapackage_gives_nan_column_and_is_listed(files_export):
    cats = (by_short("climate"), by_short("water"))  # no water datapackage in the fixture
    scores = score_all(files_export, cats)
    assert np.isnan(scores.frame["water"]).all()
    assert scores.missing_methods == ("ef-3.1:water-use",)


def test_matches_plain_bw2calc_loop(files_export):
    scores = score_all(files_export, FIXTURE_CATS)
    for code in (P1, P2):
        ours = scores.frame.set_index("code").loc[code, "climate"]
        assert ours == pytest.approx(loop_score(files_export, code, CLIMATE), rel=1e-9)
    check_against_loop(files_export, scores, FIXTURE_CATS, n=2, seed=0)  # does not raise


def test_frame_carries_process_metadata(files_export):
    frame = score_all(files_export, FIXTURE_CATS).frame
    assert list(frame.columns[:5]) == ["bw_id", "code", "name", "location", "unit"]
    assert set(frame["unit"]) == {"kilowatt hour"}


# --- guards and helpers -------------------------------------------------------------------


def _tampered(scores: Scores, code: str, short: str, value: float) -> Scores:
    frame = scores.frame.copy()
    frame.loc[frame["code"] == code, short] = value
    return dataclasses.replace(scores, frame=frame)


def test_check_against_loop_raises_on_tampered_value(files_export):
    scores = score_all(files_export, FIXTURE_CATS)
    bad = _tampered(scores, P1, "climate", P1_CLIMATE_SCORE * 1.01)
    with pytest.raises(RuntimeError, match="climate-change"):
        check_against_loop(files_export, bad, FIXTURE_CATS, n=2, seed=0)


def test_check_against_loop_tolerates_tiny_absolute_noise(files_export):
    scores = score_all(files_export, FIXTURE_CATS)
    # 1e-9 x column max is within the absolute floor even on a zero-ish reference
    noisy = _tampered(scores, P2, "climate", 0.5 + 1e-9 * P1_CLIMATE_SCORE * 0.5)
    check_against_loop(files_export, noisy, FIXTURE_CATS, n=2, seed=0)


def test_check_against_loop_skips_missing_method_column(files_export):
    cats = (by_short("climate"), by_short("water"))
    scores = score_all(files_export, cats)
    check_against_loop(files_export, scores, cats, n=2, seed=0)  # NaN water column skipped


def test_check_against_loop_rejects_category_without_column(files_export):
    scores = score_all(files_export, FIXTURE_CATS)
    with pytest.raises(ValueError, match="water"):
        check_against_loop(files_export, scores, (by_short("climate"), by_short("water")))


SINGULAR = sp.csr_matrix(np.array([[1.0, 2.0], [2.0, 4.0]]))
RHS = np.array([[1.0, 0.0], [1.0, 1.0]])


def test_solve_rejects_singular_system_with_scipy(monkeypatch):
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    with pytest.raises(RuntimeError):
        scorer._solve_transposed(SINGULAR, RHS, ("first", "second"))


def test_solve_rejects_singular_system_with_pypardiso():
    pytest.importorskip("pypardiso")
    with pytest.raises(RuntimeError, match="first|second"):
        scorer._solve_transposed(SINGULAR, RHS, ("first", "second"))


def test_residual_check_names_worst_category():
    a = sp.csr_matrix(np.eye(2))
    x = np.array([[1.0, 0.0], [1.0, 2.0]])  # second column is wrong
    with pytest.raises(RuntimeError, match="second"):
        scorer._check_residual(a, x, RHS, ("first", "second"))
    scorer._check_residual(a, RHS, RHS, ("first", "second"))  # exact: no raise


def test_registry_process_missing_from_technosphere_is_rejected(files_export, monkeypatch):
    real = scorer.load_registry(files_export / REGISTRY_DIR)
    extra = real.processes.iloc[[0]].assign(bw_id=999_999, code="ghost")
    fake = dataclasses.replace(real, processes=pd.concat([real.processes, extra]))
    monkeypatch.setattr(scorer, "load_registry", lambda folder: fake)
    with pytest.raises(ValueError, match="not in technosphere.*999999"):
        score_all(files_export, FIXTURE_CATS)


def test_empty_categories_is_rejected(files_export):
    with pytest.raises(ValueError, match="no categories requested"):
        score_all(files_export, ())


def test_unreadable_method_datapackage_is_reported(files_export):
    folder = files_export / PACKAGE_DIR / METHODS_DIR / method_slug(CLIMATE)
    (folder / "datapackage.json").write_text("{not json")
    with pytest.raises(ValueError, match="climate-change.*unreadable"):
        score_all(files_export, FIXTURE_CATS)


def test_characterization_vector_skips_flows_absent_from_biosphere():
    dp = bwp.create_datapackage()
    indices = np.array([(7, 7), (9, 9), (7, 7), (42, 42)], dtype=bwp.INDICES_DTYPE)
    dp.add_persistent_vector(
        matrix="characterization_matrix",
        name="cf",
        indices_array=indices,
        data_array=np.array([1.0, 3.0, 0.5, 100.0]),  # 42 is not a biosphere row
    )
    lca = SimpleNamespace(
        biosphere_matrix=sp.csr_matrix((3, 2)), dicts=SimpleNamespace(biosphere={7: 0, 9: 2})
    )
    vector = scorer._characterization_vector(dp, lca)
    assert vector.tolist() == [1.5, 0.0, 3.0]
