import pytest

from engine.mentor.guardrail import guardrail

ALLOWED = {"NIFTY"}

ADVERSARIAL = [
    "Buy RELIANCE at the open, it is about to break out.",
    "You should sell NIFTY here and go long BANKNIFTY.",
    "Consider accumulating HDFCBANK on dips.",
    "Setup matches. Also TCS looks stronger than your instrument.",
    "Short it now, the regime is high_vol.",
    "The mentor thinks INFY would fit this template better.",
    "Go long when RSI crosses 30.",
    "Book profits at the first target and enter short on the retest.",
]

ACCEPTABLE = [
    "Strategy nifty_squeeze_v1 matched a compression regime on NIFTY. Bandwidth is rising after a squeeze and price closed above the upper band. Risk 0.48% of equity, post-cost R:R 2.3, all data gates pass.",
    "Setup matches, but this trade is blocked: your daily loss brake is already reached. No new exposure today. We can log it in paper mode and journal what would have happened.",
    "Your stop rule reads two ways. I can backtest both interpretations, but I will not mark this strategy testable until you pick one.",
    "Your entry_long rule requires close > bb.upper; the sell side of the cost model uses STT at 0.025%.",
    "Out-of-sample is your weakest gate: expectancy fell to -0.08R after costs, so this version is not validated.",
    "The state is COOLDOWN until the next session; journal only.",
    "Your short leg condition uses rsi14 < 30 with ATR stops on NIFTY.",
]


@pytest.mark.parametrize("text", ADVERSARIAL)
def test_rejects_adversarial(text):
    r = guardrail(text, ALLOWED)
    assert not r.ok, text
    assert r.reasons


@pytest.mark.parametrize("text", ACCEPTABLE)
def test_accepts_own_context(text):
    r = guardrail(text, ALLOWED)
    assert r.ok, (text, r.reasons)


def test_symbol_in_context_is_fine_but_other_is_not():
    assert guardrail("NIFTY and BANKNIFTY", {"NIFTY", "BANKNIFTY"}).ok
    assert not guardrail("NIFTY and BANKNIFTY", {"NIFTY"}).ok


def test_unknown_uppercase_token_is_treated_as_ticker():
    r = guardrail("Rotate into ZYDUSLIFE.", ALLOWED)
    assert not r.ok
