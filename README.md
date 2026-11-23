# Regime Rider v4 — cbBTC 1-minute trading bot

A bot that trades Coinbase Wrapped BTC (cbBTC) against USDC, minute by
minute, on 1-minute on-chain bars, for make.fun's "Race a BTC trading bot
live for 24 hours" competition. Paper money only: it starts with $1,000,
is long only, never uses leverage, and every trade pays the replay's
4 bps fee, 2 bps slippage and constant-product price impact.

## How it trades

Four arms, one position at a time, 100% of cash per entry:

- **washout** — buys a deep dislocation, 4.10% under the 240-bar high,
  rides it with a 1.50% trailing stop and a 2% hard stop
- **recovery** — buys the bounce: 1.50% under the 240-bar high while the
  60-minute return is already positive, 1.50% trail, 2% hard stop
- **trend** — buys a breakout above the 60-bar high with the 60-minute
  return at +0.80% or better, 3.50% trailing stop, 1.50% hard stop,
  holds to the end of the window
- **shallow** — buys a pullback 0.80% under SMA90 while SMA90 is not
  falling, takes +2.10% or stops at -0.80%, max 240-bar hold

One entry per episode (90-bar cooldown after any exit) and a 5%
peak-to-current equity circuit breaker that halts trading for the rest
of the window.

## Run it

```sh
python3 main.py < hello_and_batches.ndjson > replies.ndjson
```

`main.py` is standard library only and speaks `agent-fun/bars-replay/v1`
(newline-delimited JSON on stdin/stdout). It is deterministic: no clock,
no randomness, no network, no files — two runs on the same data produce
the same orders.

## Measured results

Local replay with the exact integer fill model (fill at the next open,
fees, slippage and impact as the rules describe):

| window | net PnL | trades | max drawdown |
| --- | --- | --- | --- |
| dev, 22–23 Nov 2026 (rising +3.6%) | +$21.74 | 1 | 1.98% |
| 17–18 Nov 2026 (grinding down) | +$17.09 | 2 | 0.64% |
| 14–15 Nov 2026 (down day) | -$15.68 | 5 | 3.21% |
| 12–13 Nov 2026 (down day) | -$5.52 | 6 | 2.58% |

The dev gate needs a net PnL above $0: this bot clears it at +$21.74.

## License

MIT — see LICENSE.
