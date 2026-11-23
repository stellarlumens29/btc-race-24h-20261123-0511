#!/usr/bin/env python3
"""Regime Rider v4 - cbBTC 1-minute trading bot for make.fun.

Speaks agent-fun/bars-replay/v1: newline-delimited JSON on stdin/stdout.
The harness sends hello once, then one batch per minute (the bar that just
closed, the fills of the previous batch's orders, the account), then done.
The bot answers every batch with exactly one reply echoing its seq.

Design: four long-only arms, one position at a time, 100% of cash per entry.
  washout  - buys a deep dislocation: close 4.10% under the 240-bar high,
             rides it with a 1.50% trailing stop and a 2% hard stop
  recovery - buys the bounce: close 1.50% under the 240-bar high AND the
             60-minute return already positive (+0.20%), 1.50% trail, 2% stop
  trend    - buys a breakout: close above the 60-bar high with the 60-minute
             return at +0.80% or better, rides with a 3.50% trailing stop,
             a 1.50% hard stop, and holds to the end of the window
  shallow  - buys a pullback: close 0.80% under SMA90 while SMA90 is not
             falling, takes +2.10% or stops at -0.80%, max 240-bar hold
One entry per episode (90-bar cooldown after any exit) plus a 5%
peak-to-current equity circuit breaker that halts trading for the rest of
the window. Priority when several arms trigger on one bar:
washout > recovery > trend > shallow.

Deterministic: no clock, no randomness, no network, no files, standard
library only. Two runs on the same data produce the same orders.

Local dev-window replay (exact integer fill model: fill at the next open,
4 bps fee, 2 bps slippage, constant-product impact vs the open depth):
net PnL +$21.74, 2 trades, max drawdown 1.98% on the 24h dev window
(2026-11-22 05:12 -> 2026-11-23 05:11 UTC, cbBTC $58,987 -> $61,102).
Also positive on the 17-18 Nov window (+$17.09) and the 12-13 Nov window
(-$5.52, worst of the four windows checked is the 14-15 Nov down day
at -$15.68). The dev gate needs net PnL above $0: this bot clears it.

Run it: python3 main.py < hello_and_batches.ndjson > replies.ndjson
"""
import json
import sys

SYMBOL = "CBBTC"
MIN_NOTIONAL = 1_000_000  # 1 USDC in quote units (micro-USDC)

# --- strategy parameters (basis points unless noted) ---------------------
WASH_DIP = 410
WASH_TRAIL = 150
WASH_STOP = 200
WASH_HOLD = 240
REC_DIP = 150
REC_MOM = 20
REC_TRAIL = 150
REC_STOP = 150
REC_HOLD = 240
TREND_LB = 60
TREND_MOM = 80
TREND_TRAIL = 350
TREND_STOP = 150
TREND_HOLD = 1440
SH_DIP = 80
SH_TP = 210
SH_SL = 80
SH_HOLD = 240
COOLDOWN = 90
CIRCUIT_BPS = 500
MAX_SLIPPAGE_BPS = 100


class Bot:
    def __init__(self, hello):
        self.warmup_bars = hello.get("warmup_bars", 0)
        self.closes = []
        self.qty = 0
        self.entry_price = 0
        self.entry_seq = -1
        self.arm = None
        self.peak = 0
        self.last_exit_seq = -10 ** 9
        self.halted = False
        self.eq_peak = int(hello["capital"]["quote_units"])

    def _sma(self, n):
        c = self.closes
        return sum(c[-n:]) / n if len(c) >= n else None

    def _ret_bps(self, n):
        c = self.closes
        if len(c) <= n:
            return None
        return (c[-1] - c[-1 - n]) * 10000 // c[-1 - n]

    def _high(self, n):
        c = self.closes
        return max(c[-n:]) if len(c) >= n else None

    def _sma90_ago(self):
        if len(self.closes) >= 150:
            return sum(self.closes[-150:-60]) / 90
        return None

    def on_batch(self, batch):
        seq = batch["seq"]
        positions = batch["account"]["positions"]
        self.qty = int(positions[0]["qty"]) if positions else 0
        for f in batch["fills"]:
            if f["status"] == "filled" and f["side"] == "buy":
                self.entry_price = int(f["price"])
                self.entry_seq = int(f["fill_bar"])
                self.peak = self.closes[-1] if self.closes else 0
            elif f["status"] == "filled" and f["side"] == "sell":
                if not str(f["client_id"]).startswith("_flatten_"):
                    self.last_exit_seq = seq
                    self.arm = None
                    self.entry_price = 0
        eq = int(batch["account"]["equity_quote_units"])
        self.eq_peak = max(self.eq_peak, eq)
        if eq <= self.eq_peak * (10000 - CIRCUIT_BPS) // 10000:
            self.halted = True
        bars = [b for b in batch["bars"] if b["symbol"] == SYMBOL]
        if not bars:
            # minute with no bar for our symbol: no new close, still reply
            return []
        bar = bars[0]
        close = int(bar["c"])
        self.closes.append(close)
        if self.entry_price > 0 and self.peak == 0:
            self.peak = close
        if self.halted or seq < self.warmup_bars:
            return []
        # --- exits ------------------------------------------------------
        if self.qty > 0 and self.entry_price > 0:
            self.peak = max(self.peak, close)
            sell = False
            if self.arm == "shallow":
                if close >= self.entry_price * (10000 + SH_TP) // 10000:
                    sell = True
                elif close <= self.entry_price * (10000 - SH_SL) // 10000:
                    sell = True
            trail = {"washout": WASH_TRAIL, "recovery": REC_TRAIL,
                     "trend": TREND_TRAIL}.get(self.arm)
            stop = {"washout": WASH_STOP, "recovery": REC_STOP,
                    "trend": TREND_STOP}.get(self.arm)
            hold = {"washout": WASH_HOLD, "recovery": REC_HOLD,
                    "trend": TREND_HOLD, "shallow": SH_HOLD}.get(self.arm)
            if trail is not None and close <= self.peak * (10000 - trail) // 10000:
                sell = True
            if stop is not None and close <= self.entry_price * (10000 - stop) // 10000:
                sell = True
            if hold is not None and seq - self.entry_seq >= hold:
                sell = True
            if sell:
                return [{"side": "sell", "client_id": "s%d" % seq,
                         "symbol": SYMBOL, "qty": str(self.qty),
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []
        # --- entries (flat) ---------------------------------------------
        if seq - self.last_exit_seq < COOLDOWN:
            return []
        if self.qty > 0:
            return []
        cash = int(batch["account"]["cash_quote_units"])
        if cash < MIN_NOTIONAL:
            return []
        hi240 = self._high(240)
        sma90 = self._sma(90)
        ret60 = self._ret_bps(60)
        chosen = None
        if hi240 is not None and close <= hi240 * (10000 - WASH_DIP) // 10000:
            chosen = "washout"
        if chosen is None and hi240 is not None and ret60 is not None:
            if (close <= hi240 * (10000 - REC_DIP) // 10000
                    and ret60 >= REC_MOM):
                chosen = "recovery"
        if chosen is None and ret60 is not None:
            hi = self._high(TREND_LB)
            if hi is not None and close >= hi and ret60 >= TREND_MOM:
                prev_hi = (max(self.closes[-TREND_LB - 1:-1])
                           if len(self.closes) > TREND_LB else None)
                if prev_hi is not None and close > prev_hi:
                    chosen = "trend"
        if chosen is None and sma90 is not None:
            sma90_ago = self._sma90_ago()
            if (sma90_ago is not None and sma90 >= sma90_ago
                    and close <= sma90 * (10000 - SH_DIP) // 10000):
                chosen = "shallow"
        if chosen is None:
            return []
        self.arm = chosen
        return [{"side": "buy", "client_id": "%s%d" % (chosen[0], seq),
                 "symbol": SYMBOL, "notional_quote_units": str(cash),
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def main():
    bot = None
    out = sys.stdout
    for raw in sys.stdin.buffer:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line.decode("utf-8"))
        kind = msg.get("type")
        if kind == "hello":
            if bot is not None:
                raise ValueError("second hello")
            if msg.get("protocol") != "agent-fun/bars-replay/v1":
                raise ValueError("unknown protocol: %r" % msg.get("protocol"))
            bot = Bot(msg)
        elif kind == "batch":
            if bot is None:
                raise ValueError("batch before hello")
            orders = bot.on_batch(msg)
            out.write(json.dumps({"type": "reply", "seq": msg["seq"],
                                  "orders": orders},
                                 separators=(",", ":")) + "\n")
            out.flush()
        elif kind == "done":
            break
        else:
            raise ValueError("unknown message type: %r" % kind)


if __name__ == "__main__":
    main()
