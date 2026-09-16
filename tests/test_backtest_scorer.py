import numpy as np
import pytest

from sentier_brightway.backtest.categories import Category, by_short
from sentier_brightway.backtest.scorer import Scores, check_against_loop, score_all
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
