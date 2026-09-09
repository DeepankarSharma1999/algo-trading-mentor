**Every file in this folder is SYNTHETIC. No price, volume or timestamp here ever existed on any exchange.**

The tickers (NIFTY, RELIANCE, ...) are familiar names used only so the app reads naturally. Nothing
in `data/` may be used to draw conclusions about real markets, and every file name carries the
`SYNTHETIC_` prefix so it cannot be mistaken for a vendor download.

## Files

| File | Contents |
|---|---|
| `SYNTHETIC_<SYMBOL>_1m.parquet` | 1-minute OHLCV bars, 2024-01-01 to 2025-12-31, 492 sessions, 184,500 rows each |
| `generate.py` | the generator; regenerates every file byte-for-byte |
| `csv/<SYMBOL>_1m.csv` | (optional, not committed) your own 1-minute bars for `DATA_PROVIDER=csv`, header `ts,open,high,low,close,volume` |

Columns: `ts` (datetime64[ns], tz-naive Asia/Kolkata wall time, bar open), `open high low close`
(float32, tick 0.05), `volume` (int32). Compression zstd. Whole folder about 46 MB.

Universe and starting levels: NIFTY 21500, BANKNIFTY 46000, RELIANCE 2600, HDFCBANK 1650,
ICICIBANK 1000, INFY 1550, TCS 3800, SBIN 620, ITC 440, LT 3400, AXISBANK 1050, KOTAKBANK 1800.

## Regenerate

```
python data/generate.py            # default seed 20240101, writes into data/
python data/generate.py --seed 7   # a different but equally deterministic universe
```

Output is fully determined by the seed: every symbol and every sub-process (regimes, drift, gaps,
noise, wicks, volume) draws from its own `numpy.random.default_rng([seed, crc32(tag)...])` stream,
so a symbol's first N days are identical however long the run is. `generate_symbol(symbol, start,
end, seed)` returns the frame in memory (used by the tests with a three-day window).

## Sessions

Weekdays only, 375 bars per day from 09:15 through 15:29 inclusive (each bar covers
`ts .. ts+59s`). The holiday list below is hardcoded in
`services/engine/engine/data/calendar.py` (`HOLIDAYS`), which the engine shares for the simulated
clock. It follows the published NSE calendars closely but is not authoritative.

**2024:** Jan 22 (special holiday), Jan 26 (Republic Day), Mar 8 (Mahashivratri), Mar 25 (Holi),
Mar 29 (Good Friday), Apr 11 (Id-Ul-Fitr), Apr 17 (Ram Navami), May 1 (Maharashtra Day), May 20
(election), Jun 17 (Bakri Id), Jul 17 (Muharram), Aug 15 (Independence Day), Oct 2 (Gandhi Jayanti),
Nov 1 (Diwali Laxmi Pujan), Nov 15 (Guru Nanak Jayanti), Nov 20 (state election), Dec 25 (Christmas).

**2025:** Feb 26 (Mahashivratri), Mar 14 (Holi), Mar 31 (Id-Ul-Fitr), Apr 10 (Mahavir Jayanti),
Apr 14 (Ambedkar Jayanti), Apr 18 (Good Friday), May 1 (Maharashtra Day), Aug 15 (Independence Day),
Aug 27 (Ganesh Chaturthi), Oct 2 (Gandhi Jayanti / Dussehra), Oct 21 (Diwali Laxmi Pujan), Oct 22
(Balipratipada), Nov 5 (Guru Nanak Jayanti), Dec 25 (Christmas).

Event days (`EVENT_DAYS`, 2x volatility and 1.6x volume): RBI MPC decisions 2024-02-08, 04-05,
06-07, 08-08, 10-09, 12-06, 2025-02-07, 04-09, 06-06, 08-06, 10-01, 12-05, and Union Budgets
2024-07-23 and 2025-02-01.

## Price model

- **Common factor.** One market-wide process (the "market"). NIFTY loads on it with beta 1 and a
  tiny idiosyncratic term; BANKNIFTY with beta 1.15; stocks with betas 0.6-1.15 plus their own
  idiosyncratic process, giving daily correlations with NIFTY of roughly 0.4-0.7.
- **Volatility regimes.** Each process runs a 3-state Markov chain (quiet / normal / high-vol,
  vol multipliers 0.55 / 1.0 / 2.1, mean durations about 20 / 17 / 8 sessions). Normal-regime daily
  vol is 0.85 % for the factor and 1.0-1.35 % idiosyncratic for stocks, so rolling 20-day NIFTY
  vol ranges from roughly 8 % to 22 % annualised; compression and high-vol stretches both occur.
- **Drift.** Daily drift is an AR(1) with persistence 0.985 and stationary std 0.12 %/day around a
  long-run +0.03 %/day, so multi-week trends and flat ranges both appear.
- **Overnight gaps.** 30 % of each day's variance is realised in the open gap; the rest is spread
  over the session with a U-shaped intraday vol profile (heavier first 30 minutes and last 30).
- **Bars.** Log-price path: bar open = previous close, bar close = open x exp(r). Wicks extend
  beyond the body by |N(0,1)| x 0.6 x local minute vol, so high >= max(open, close) and
  low <= min(open, close) always hold. Prices are rounded to the 0.05 tick.
- **Volume.** Base per-symbol volume x U-shaped profile with an opening spike and lunch lull x
  regime multiplier x event multiplier x (1 + 1.5 |r| / sigma) x lognormal noise. Index "volume"
  is a stand-in for futures volume.

## Engine access

`services/engine/engine/data`: `SyntheticProvider(data_dir).get_bars(symbol, timeframe, start,
end)` for 1m 3m 5m 15m 30m 1h 1D (higher timeframes are resampled from 1m, aligned to 09:15) and
`get_option_chain(underlying, expiry, asof)` (Black-Scholes at a flat IV on the synthetic close).
