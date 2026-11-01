# nautilus-risk-demo

Extract from my risk-manager approach for the NautilusTrader prop-trading research platform job.

The point of this extract: **the risk manager is a separate, pure component**, not baked into a strategy base class. No Nautilus import anywhere in `risk_manager.py`. The engine wires it in at the edge, the logic stays pure, so every rule unit-tests in isolation with hand-built equity fixtures, exactly the style of fixture the job's DoD asks for.

## What it shows

- In-bar daily loss stop: resting stop recalculated every bar from day-start equity.
- Equity-low floor: hard halt at the account's low-water mark. When both rules breach in the same bar, equity-low wins because it ends the account, not just the day.
- Breach classification (`daily_loss` vs `equity_low`) so a downstream prop-firm simulator can score pass/fail per rule.
- Session reset: new day, new daily-high watermark.

## Run the tests

```
python test_risk_manager.py
```

6/6 pass on Python 3.13, no dependencies. Or with pytest: `python -m pytest test_risk_manager.py -v`.

## Files

- `risk_manager.py` - the component (~150 lines, pure logic)
- `test_risk_manager.py` - hand-built fixture unit tests (6 cases)
