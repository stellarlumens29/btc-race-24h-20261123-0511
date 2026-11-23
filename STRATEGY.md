# Regime Rider v4 — design note

## The idea

The dev window decides only who races; the race window is unseen. A bot
that only buys dips can sit out a rally day, and a bot that only chases
breakouts bleeds on a falling day, so this bot carries both: dip-buying
arms for falling and choppy days, and a breakout arm for rally days.
One position at a time, full size, with hard stops and a circuit breaker
so no single day can do much damage (worst max drawdown across the four
windows checked is 3.21%).

## Arms (all long only, 100% of cash)

- **washout** (dislocation): close 4.10% under the 240-bar high.
  Trail 1.50%, hard stop 2%, max hold 240 bars.
- **recovery** (bounce): close 1.50% under the 240-bar high AND the
  60-minute return already positive (+0.20%). The momentum filter is
  what separates a bounce from a falling knife. Trail 1.50%,
  hard stop 1.50%, max hold 240 bars.
- **trend** (breakout): close above the 60-bar high with the 60-minute
  return at +0.80% or better. Trail 3.50%, hard stop 1.50%, holds to
  the end of the window unless the trail or the stop fires.
- **shallow** (pullback): close 0.80% under SMA90 while SMA90 is not
  falling. Take profit +2.10%, stop -0.80%, max hold 240 bars.

Priority on one bar: washout > recovery > trend > shallow. After any
exit, no re-entry for 90 bars. A 5% peak-to-current equity circuit
breaker halts all trading for the rest of the window.

## What was tried and rejected

- Dip arms alone (the previous version): +$7.02 on this dev window —
  passes the gate, but leaves the rally unridden and the margin thin.
- Breakout arm alone with a tight trail (1.20%): +$4.41 on this dev
  window — it exits in the chop and churns (6 trades).
- Breakout with a 2.50% trail and 480-bar hold: +$21.84 — better, but
  the 1440-bar hold rides the whole window cleaner (+$29.50 alone).
- The combination above keeps the breakout's dev score (+$21.74) while
  the dip arms keep the falling days survivable (17–18 Nov +$17.09).

## Measured results (exact integer replay)

| window | net PnL | trades | max DD |
| --- | --- | --- | --- |
| dev 22–23 Nov 2026 | +$21.74 | 1 | 1.98% |
| 17–18 Nov 2026 | +$17.09 | 2 | 0.64% |
| 14–15 Nov 2026 | -$15.68 | 5 | 3.21% |
| 12–13 Nov 2026 | -$5.52 | 6 | 2.58% |

Dev gate (net PnL > $0): PASS. Guardrails (>= 1 trade, max DD <= 25%):
PASS on all four windows.
