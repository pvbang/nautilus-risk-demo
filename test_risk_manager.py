"""Unit tests for the risk manager with hand-built fixtures.

Run: python -m pytest test_risk_manager.py -v  (or plain python test_risk_manager.py)

These are the kinds of fixtures the client's DoD asks for: hand-built equity
paths, including the in-bar breach case that a vectorised engine rounds off.
"""

from datetime import date

from risk_manager import BreachType, RiskConfig, RiskManager


def make_manager(starting: float = 100_000.0, daily: float = 0.05, low: float = 0.10) -> RiskManager:
    return RiskManager(RiskConfig(daily_stop_pct=daily, equity_low_pct=low, starting_balance=starting))


def test_normal_bars_allowed():
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    d = rm.on_bar(equity=101_000.0)
    assert d.allowed and d.breach == BreachType.NONE
    d = rm.on_bar(equity=96_000.0)  # -4% from day start, above 5% stop
    assert d.allowed


def test_daily_loss_breach():
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    d = rm.on_bar(equity=94_999.0)  # crosses the 5% daily stop
    assert not d.allowed
    assert d.breach == BreachType.DAILY_LOSS
    assert d.resting_stop == 95_000.0
    assert rm.state.halted


def test_equity_low_wins_over_daily_stop():
    # Starting balance 100k, equity-low 10% floor = 90k.
    # A 12% single-day drop breaches both; equity-low must be reported
    # because it ends the account, not just the day.
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    d = rm.on_bar(equity=88_000.0)
    assert not d.allowed
    assert d.breach == BreachType.EQUITY_LOW


def test_resting_stop_tightens_with_losses():
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    d = rm.on_bar(equity=97_000.0)
    # Day start 100k, 5% stop -> 95k. Floor 90k. Tighter is 95k.
    assert d.resting_stop == 95_000.0


def test_day_reset_clears_watermark():
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    rm.on_bar(equity=97_000.0)
    rm.reset_day(date(2026, 1, 6), equity=97_000.0)
    d = rm.on_bar(equity=93_000.0)  # -4.1% from new day start, allowed
    assert d.allowed
    assert rm.state.day_high_equity == 97_000.0


def test_day_high_tracks_bounce():
    rm = make_manager()
    rm.on_session_start(date(2026, 1, 5), equity=100_000.0)
    rm.on_bar(equity=103_000.0)
    rm.on_bar(equity=101_000.0)
    assert rm.state.day_high_equity == 103_000.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")
