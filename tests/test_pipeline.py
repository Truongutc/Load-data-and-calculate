"""
tests/test_pipeline.py
======================
End-to-end pipeline tests for Modules 5-8 (Scoring, Decision, Scanner, Analyzer)
"""
import pytest
import pandas as pd
from pathlib import Path

from tinvest.data_loader    import load_data
from tinvest.scoring_engine import calculate_score
from tinvest.decision_engine import analyze_decision
from tinvest.scanner        import scan_stocks
from tinvest.analyzer       import analyze_stock, format_report
from tinvest.ichimoku_engine import analyze_ichimoku
from tinvest.vsa_engine      import analyze_vsa
from tinvest.aic_engine      import analyze_aic

SAMPLE_CSV = Path(__file__).parent / "sample_data.csv"
MULTI_CSV  = Path(__file__).parent / "multi_ticker.csv"


@pytest.fixture(scope="module")
def sample_df():
    return load_data(str(SAMPLE_CSV))


@pytest.fixture(scope="module")
def pipeline_results(sample_df):
    ichi  = analyze_ichimoku(sample_df)
    vsa   = analyze_vsa(sample_df)
    aic   = analyze_aic(sample_df)
    score = calculate_score(ichi, vsa, aic)
    dec   = analyze_decision(sample_df, ichi, vsa, aic)
    return ichi, vsa, aic, score, dec


# ═══════════════════════════════════════════════════════════════════
#  Module 5 – Scoring Engine
# ═══════════════════════════════════════════════════════════════════

class TestScoringEngine:

    def test_required_keys(self, pipeline_results):
        _, _, _, score, _ = pipeline_results
        for key in ("total_score", "classification", "breakdown"):
            assert key in score

    def test_total_score_in_range(self, pipeline_results):
        _, _, _, score, _ = pipeline_results
        assert 0 <= score["total_score"] <= 11

    def test_classification_is_valid(self, pipeline_results):
        _, _, _, score, _ = pipeline_results
        assert score["classification"] in ("STRONG BUY", "BUY", "WATCH", "AVOID")

    def test_breakdown_sums_to_total(self, pipeline_results):
        _, _, _, score, _ = pipeline_results
        bd = score["breakdown"]
        assert bd["ichimoku"] + bd["vsa"] + bd["aic"] == score["total_score"]

    def test_strong_buy_threshold(self):
        """Score >= 9 should be STRONG BUY."""
        result = calculate_score({"score": 3}, {"score": 4}, {"score": 3})
        assert result["classification"] == "STRONG BUY"
        assert result["total_score"] == 10

    def test_avoid_threshold(self):
        result = calculate_score({"score": 0}, {"score": 0}, {"score": 0})
        assert result["classification"] == "AVOID"


# ═══════════════════════════════════════════════════════════════════
#  Module 6 – Decision Engine
# ═══════════════════════════════════════════════════════════════════

class TestDecisionEngine:

    def test_required_keys(self, pipeline_results):
        _, _, _, _, dec = pipeline_results
        assert "opportunity" in dec
        assert "risk" in dec

    def test_lists_of_strings(self, pipeline_results):
        _, _, _, _, dec = pipeline_results
        for item in dec["opportunity"] + dec["risk"]:
            assert isinstance(item, str)


# ═══════════════════════════════════════════════════════════════════
#  Module 8 – Single Stock Analyzer
# ═══════════════════════════════════════════════════════════════════

class TestAnalyzer:

    def test_analyze_stock_keys(self, sample_df):
        result = analyze_stock("TEST", sample_df)
        for key in ("ticker", "price", "date", "ichi", "vsa", "ma_trend", "adv", "accum"):
            assert key in result

    def test_format_report_is_string(self, sample_df):
        result  = analyze_stock("TEST", sample_df)
        report  = format_report(result)
        assert isinstance(report, str)
        assert "TEST" in report
        assert "BÁO CÁO PHÂN TÍCH TỔNG HỢP" in report

    def test_ticker_normalized_to_upper(self, sample_df):
        result = analyze_stock("test", sample_df)
        assert result["ticker"] == "TEST"


# ═══════════════════════════════════════════════════════════════════
#  Module 7 – Stock Scanner
# ═══════════════════════════════════════════════════════════════════

class TestScanner:

    def test_scan_returns_dataframe(self):
        data = load_data(str(MULTI_CSV))
        result = scan_stocks(data)
        assert isinstance(result, pd.DataFrame)

    def test_scan_columns(self):
        data = load_data(str(MULTI_CSV))
        result = scan_stocks(data)
        if not result.empty:
            for col in ("Ticker", "Price", "Trend", "MoneyFlow", "Trigger", "Score", "Classification", "Action"):
                assert col in result.columns

    def test_scan_score_filter(self):
        data = load_data(str(MULTI_CSV))
        result = scan_stocks(data)
        if not result.empty:
            assert (result["Score"] >= 8).all(), "All returned tickers must have Score >= 8"

    def test_scan_rejects_single_dataframe(self, sample_df):
        with pytest.raises(TypeError):
            scan_stocks(sample_df)
