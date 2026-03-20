import pytest
import pandas as pd
import numpy as np
from tinvest.valuation_engine import evaluate_stock_valuation

def create_mock_df():
    dates = pd.date_range(start="2023-01-01", periods=100)
    close = [100] * 100
    df = pd.DataFrame({
        "Date": dates,
        "Open": close,
        "High": close,
        "Low": [c-1 for c in close],
        "Close": close,
        "Volume": [1000000] * 100
    })
    # Add indicators
    df['MA20'] = 98
    df['MA50'] = 95
    df['Tenkan'] = 99
    df['Kijun'] = 97
    df['Kijun65'] = 96
    df['SpanA'] = 94
    df['SpanB'] = 95
    df['CloudTop'] = 95
    return df

def test_aic_valuation_buffers():
    df = create_mock_df()
    entry_info = {"state": "JUST_EARLY"}
    # Price = 100, MA20=98, Tenkan=99, Low10=99
    # S1 = max(98, 99, 99) = 99
    # SL_Partial = 99 * 0.99 = 98.01
    
    res = evaluate_stock_valuation("TEST", df, entry_info)
    assert res["is_valid"] is True
    assert res["s1"] == 99.0
    assert res["cutloss_partial"] == 98.01
    assert res["tp1"] == pytest.approx(100 * 1.08 * 0.98, rel=0.01)

def test_risk_score_low():
    df = create_mock_df()
    entry_info = {"state": "STRONG_UPTREND"}
    # Price = 100, MA20=98, Tenkan=99, Cloud=95, K65=96
    # All good -> risk_score = 0
    res = evaluate_stock_valuation("TEST", df, entry_info)
    assert res["risk_score"] == 0
    assert res["risk_desc"] == "Low"

def test_risk_score_high():
    df = create_mock_df()
    # Force bad state
    df.loc[df.index[-1], "Close"] = 80
    df.loc[df.index[-1], "MA20"] = 100 # Price < MA20 -> +30
    df.loc[df.index[-1], "Tenkan"] = 90
    df.loc[df.index[-1], "Kijun"] = 95 # TK bearish -> +20
    df.loc[df.index[-1], "CloudTop"] = 100 # Below cloud -> +20
    df.loc[df.index[-1], "Kijun65"] = 100 # < K65 -> +20
    # Total = 90
    
    res = evaluate_stock_valuation("TEST", df, {})
    assert res["risk_score"] >= 90
    assert res["risk_desc"] == "High"

def test_actionable_conclusion():
    df = create_mock_df()
    # RR = (R1 - Price) / (Price - S1)
    # Price = 100, S1 = 99. Risk = 1.
    # R1 = 108. Reward = 8.
    # RR = 8.
    res = evaluate_stock_valuation("TEST", df, {})
    assert res["action"] == "YES"
