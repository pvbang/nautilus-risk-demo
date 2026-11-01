"""Prop-firm risk manager: pure logic, no engine dependency.

Demo extract from my approach for the NautilusTrader prop-trading platform.
The risk manager is a separate component that subscribes to 1-minute bars
and the account, so every rule below unit-tests in isolation with hand-built
fixtures. No Nautilus import anywhere in this module: the engine wires it in
at the edge, the logic stays pure.

Rules covered here (the spec's core risk concerns):
- In-bar daily loss stop: resting stop recalculated per bar from equity,
  placed where equity would hit the floor.
- Equity-low floor: hard halt if equity touches the account's low-water mark.
- Breach classification: daily-stop breach vs equity-low breach, so the
  prop-firm simulator downstream can score pass/fail per rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class BreachType(Enum):
    NONE = "none"
    DAILY_LOSS = "daily_loss"      # trailing daily stop hit
    EQUITY_LOW = "equity_low"      # hard low-water mark hit


@dataclass(frozen=True)
class RiskConfig:
    """Per-account risk parameters, one set per prop-firm rule file."""

    daily_stop_pct: float = 0.05       # e.g. 5% max daily loss
    equity_low_pct: float = 0.10       # e.g. 10% total drawdown floor
    starting_balance: float = 100_000.0


@dataclass
class RiskState:
    """Mutable session state. Reset daily-high at session start."""

    day: date
    day_start_equity: float
    day_high_equity: float
    halted: bool = False
    breach: BreachType = BreachType.NONE
    breach_equity: Optional[float] = None


@dataclass
class RiskDecision:
    """Returned on every bar. The strategy asks, the risk manager answers."""

    allowed: bool
    breach: BreachType
    resting_stop: Optional[float]  # equity level where we would stop out
    halt_reason: Optional[str] = None


class RiskManager:
    """Per-bar risk gate. One instance per account.

    Usage from the engine side (wired in later, not shown here):
        rm = RiskManager(config)
        rm.on_session_start(day, equity)
        for bar in bars:
            d = rm.on_bar(equity)
            if not d.allowed:
                flatten_and_halt(d.halt_reason)
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self.state: Optional[RiskState] = None

    @property
    def equity_low_floor(self) -> float:
        """Hard floor: starting balance minus max total drawdown."""
        return self.config.starting_balance * (1.0 - self.config.equity_low_pct)

    def daily_stop_level(self, day_start_equity: float) -> float:
        """Trailing daily loss floor: day start minus max daily loss."""
        return day_start_equity * (1.0 - self.config.daily_stop_pct)

    def on_session_start(self, day: date, equity: float) -> RiskState:
        """Call once at session open. Resets the daily-high watermark."""
        self.state = RiskState(
            day=day,
            day_start_equity=equity,
            day_high_equity=equity,
        )
        return self.state

    def on_bar(self, equity: float) -> RiskDecision:
        """Evaluate one bar's closing equity against every active rule.

        Order matters: equity-low is the hard floor and wins over daily stop,
        because a low-water breach ends the account, not just the day.
        """
        if self.state is None:
            raise RuntimeError("on_session_start must be called before on_bar")
        s = self.state

        # Track the running high for trailing stops (future rule: profit lock).
        if equity > s.day_high_equity:
            s.day_high_equity = equity

        # Rule 1: hard equity-low floor. In-bar breach means the resting stop
        # was already pierced; we halt and report the level that broke.
        if equity <= self.equity_low_floor:
            s.halted = True
            s.breach = BreachType.EQUITY_LOW
            s.breach_equity = equity
            return RiskDecision(
                allowed=False,
                breach=BreachType.EQUITY_LOW,
                resting_stop=self.equity_low_floor,
                halt_reason=f"equity {equity:.2f} <= floor {self.equity_low_floor:.2f}",
            )

        # Rule 2: in-bar daily loss stop. The resting stop recalculates every
        # bar from day-start equity, so a losing streak tightens it naturally.
        daily_stop = self.daily_stop_level(s.day_start_equity)
        if equity <= daily_stop:
            s.halted = True
            s.breach = BreachType.DAILY_LOSS
            s.breach_equity = equity
            return RiskDecision(
                allowed=False,
                breach=BreachType.DAILY_LOSS,
                resting_stop=daily_stop,
                halt_reason=f"equity {equity:.2f} <= daily stop {daily_stop:.2f}",
            )

        return RiskDecision(
            allowed=True,
            breach=BreachType.NONE,
            # Resting stop for the next in-bar move: the tighter of the two.
            resting_stop=max(daily_stop, self.equity_low_floor),
        )

    def reset_day(self, day: date, equity: float) -> RiskState:
        """Next session: new day watermark, previous breaches archived."""
        return self.on_session_start(day, equity)
