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
    assert "vs_bafu.csv" in text and "emissions.csv" in text
