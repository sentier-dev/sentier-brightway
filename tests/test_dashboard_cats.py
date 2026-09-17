from pathlib import Path

from sentier_brightway.backtest.categories import as_js_cats

HTML = Path(__file__).resolve().parents[1] / "dashboard" / "backtest_dashboard.html"


def test_html_cats_block_is_generated_from_categories():
    text = HTML.read_text(encoding="utf-8")
    start = text.index("// CATS-BEGIN\n") + len("// CATS-BEGIN\n")
    end = text.index("\n// CATS-END")
    assert text[start:end].strip() == as_js_cats().strip()


def test_html_has_no_drilldown_or_cross_version_code():
    text = HTML.read_text(encoding="utf-8")
    for needle in (
        "FlowDecompositionPanel",
        "decomp32",
        "compare32",
        "name_32",
        "mapped_to_32",
        "vs_evea",
    ):
        assert needle not in text, needle
    assert "vs_bafu.csv" in text


def test_html_reads_the_v2_files():
    from sentier_brightway.backtest.emit import BOXES_JSON, OUTLIER_REASONS, VS_BAFU_CSV, WORST_DIR

    text = HTML.read_text(encoding="utf-8")
    assert f"const BOXES_URL = '{BOXES_JSON}'" in text
    assert f"const WORST_DIR = '{WORST_DIR}'" in text
    assert f"const VS_BAFU_URL = '{VS_BAFU_CSV}'" in text
    assert f"const REASONS_URL = '{OUTLIER_REASONS}'" in text


def test_html_has_no_table_or_abs_or_distributions():
    text = HTML.read_text(encoding="utf-8")
    for needle in (
        "DistributionsView",
        "DATA_MODES",
        "dataMode",
        "fmtAbs",
        "handleColClick",
        "colMeans",
    ):
        assert needle not in text, needle
    for needle in ("function BoxPlotView", "function WorstList", "symlog"):
        assert needle in text, needle
    # emissions.csv is offered as a download only; the page never fetches it.
    mentions = [line for line in text.splitlines() if "emissions.csv" in line]
    assert mentions and all('href="emissions.csv"' in line for line in mentions)
