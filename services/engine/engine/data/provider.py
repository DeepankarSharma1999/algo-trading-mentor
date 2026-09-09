"""Market data providers (ARCHITECTURE.md section 10).

`MarketDataProvider` is the only thing the rest of the engine talks to. Three implementations:

* `SyntheticProvider` reads the committed `data/SYNTHETIC_<SYMBOL>_1m.parquet` files.
* `CsvProvider` reads `data/csv/<SYMBOL>_1m.csv` files with the same columns.
* `VendorProvider` is a documented stub for a real feed and raises `NotImplementedError`.

All providers hold 1-minute bars and derive higher timeframes with `engine.data.resample`, so every
timeframe is consistent by construction. Timestamps are tz-naive Asia/Kolkata wall time.
"""

from __future__ import annotations

import abc
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from engine import config
from engine.data.options import build_chain
from engine.data.resample import BAR_COLUMNS, TIMEFRAMES, normalize_bars, resample_bars

SYNTHETIC_PREFIX = "SYNTHETIC_"
CSV_HEADER = "ts,open,high,low,close,volume"

# Contract lot sizes. Cash equities trade in units of one share.
LOT_SIZES: dict[str, int] = {"NIFTY": 25, "BANKNIFTY": 15}


def lot_size(symbol: str, market: str = "NSE_EQ") -> int:
    """Lot size for `symbol` in `market` ("NSE_EQ", "NSE_FO", "NSE_INDEX").

    Index derivatives use their contract lot; cash equities are 1 share. A stock in NSE_FO would
    need a per-stock lot table, which phase 1 does not have, so it falls back to 1.
    """
    if symbol in LOT_SIZES:
        return LOT_SIZES[symbol]
    return 1


DateLike = datetime | date | str | None


def _parse_range(start: DateLike, end: DateLike) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """`start` is inclusive. `end` is inclusive; a date-only `end` (midnight) extends to the end of that day."""
    s = pd.Timestamp(start) if start is not None else None
    e = pd.Timestamp(end) if end is not None else None
    if e is not None and e == e.normalize():
        e = e + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return s, e


def slice_bars(df: pd.DataFrame, start: DateLike, end: DateLike) -> pd.DataFrame:
    s, e = _parse_range(start, end)
    if s is not None:
        df = df[df["ts"] >= s]
    if e is not None:
        df = df[df["ts"] <= e]
    return df.reset_index(drop=True)


class MarketDataProvider(abc.ABC):
    """Read-only access to bars and option chains for one universe of symbols."""

    name: str = "abstract"

    @abc.abstractmethod
    def symbols(self) -> list[str]:
        """Symbols this provider can serve, sorted."""

    @abc.abstractmethod
    def get_bars(
        self, symbol: str, timeframe: str = "1m", start: DateLike = None, end: DateLike = None
    ) -> pd.DataFrame:
        """Bars for `symbol` at `timeframe` (one of 1m 3m 5m 15m 30m 1h 1D) within [start, end].

        Columns ts, open, high, low, close, volume; prices float32, volume int64; ts tz-naive IST,
        ascending, labelled at bar open. `start`/`end` accept datetimes or ISO strings; a date-only
        `end` includes the whole of that day.
        """

    @abc.abstractmethod
    def get_option_chain(self, underlying: str, expiry: date, asof: datetime) -> pd.DataFrame:
        """Option chain for `underlying` expiring on `expiry`, priced as of `asof`.

        Columns strike, call_price, put_price, call_iv, put_iv, call_oi, put_oi, one row per strike,
        ascending strike.
        """


class _FileProvider(MarketDataProvider):
    """Shared machinery for providers backed by one 1-minute file per symbol."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self._load = lru_cache(maxsize=32)(self._read_1m)

    # subclasses implement these two
    def _path(self, symbol: str) -> Path:
        raise NotImplementedError

    def _read_1m(self, symbol: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_bars(
        self, symbol: str, timeframe: str = "1m", start: DateLike = None, end: DateLike = None
    ) -> pd.DataFrame:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"unknown timeframe {timeframe!r}; expected one of {list(TIMEFRAMES)}")
        path = self._path(symbol)
        if not path.exists():
            raise FileNotFoundError(f"{self.name} provider has no data for {symbol!r} (expected {path})")
        bars = slice_bars(self._load(symbol), start, end)
        return resample_bars(bars, timeframe)

    def get_option_chain(self, underlying: str, expiry: date, asof: datetime) -> pd.DataFrame:
        asof = pd.Timestamp(asof)
        bars = self._load(underlying)
        upto = bars[bars["ts"] <= asof]
        if upto.empty:
            raise ValueError(f"no {underlying} bar at or before {asof}")
        spot = float(upto["close"].iloc[-1])
        return build_chain(underlying, spot, expiry, asof.to_pydatetime())

    def clear_cache(self) -> None:
        self._load.cache_clear()


class SyntheticProvider(_FileProvider):
    """Reads `data/SYNTHETIC_<SYMBOL>_1m.parquet` (see data/README.md). Files are cached per symbol."""

    name = "synthetic"

    def _path(self, symbol: str) -> Path:
        return self.data_dir / f"{SYNTHETIC_PREFIX}{symbol}_1m.parquet"

    def _read_1m(self, symbol: str) -> pd.DataFrame:
        return normalize_bars(pd.read_parquet(self._path(symbol), columns=BAR_COLUMNS))

    def symbols(self) -> list[str]:
        suffix = "_1m.parquet"
        paths = self.data_dir.glob(f"{SYNTHETIC_PREFIX}*{suffix}")
        return sorted(p.name[len(SYNTHETIC_PREFIX) : -len(suffix)] for p in paths)


class CsvProvider(_FileProvider):
    """Reads `<data_dir>/<SYMBOL>_1m.csv`.

    Expected file: UTF-8, comma separated, header exactly ``ts,open,high,low,close,volume`` where
    ``ts`` is an ISO-8601 tz-naive IST bar-open time (``2024-01-01 09:15:00``), prices are decimals
    and volume is an integer. Rows need not be sorted. Point `data_dir` at ``data/csv``.
    """

    name = "csv"

    def _path(self, symbol: str) -> Path:
        return self.data_dir / f"{symbol}_1m.csv"

    def _read_1m(self, symbol: str) -> pd.DataFrame:
        df = pd.read_csv(self._path(symbol), parse_dates=["ts"])
        missing = [c for c in BAR_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{self._path(symbol)} is missing columns {missing}; header must be {CSV_HEADER}")
        return normalize_bars(df)

    def symbols(self) -> list[str]:
        suffix = "_1m.csv"
        return sorted(p.name[: -len(suffix)] for p in self.data_dir.glob(f"*{suffix}"))


class VendorProvider(MarketDataProvider):
    """Placeholder for a licensed market-data feed. Every method raises NotImplementedError.

    A real adapter must:

    * Implement ``symbols()`` from the vendor's instrument master, mapped to the engine's plain
      tickers (``NIFTY``, ``RELIANCE`` ...), and set ``name`` to a short lowercase id.
    * Implement ``get_bars`` returning 1-minute bars pulled (and ideally cached on disk) from the
      vendor, then call ``engine.data.resample.resample_bars`` for any other timeframe so bar
      alignment matches the synthetic and CSV providers exactly. Output must be normalised with
      ``engine.data.resample.normalize_bars``: columns ts/open/high/low/close/volume, prices float32,
      volume int64, ts tz-naive IST at bar open, ascending, no duplicates, session bars only
      (09:15-15:29). Convert vendor timestamps from epoch/UTC to IST wall time before dropping tz.
    * Implement ``get_option_chain`` returning the columns in ``engine.data.options.CHAIN_COLUMNS``
      for the requested expiry as of ``asof`` (historical snapshots if the vendor has them,
      otherwise the latest chain with ``asof`` ignored and documented as such).
    * Never place orders and never accept API keys through the app UI; credentials come from the
      environment only (spec section 0).
    """

    name = "vendor"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("VendorProvider is a stub; see its docstring for what to implement")

    def symbols(self) -> list[str]:
        raise NotImplementedError

    def get_bars(self, symbol, timeframe="1m", start=None, end=None) -> pd.DataFrame:
        raise NotImplementedError

    def get_option_chain(self, underlying, expiry, asof) -> pd.DataFrame:
        raise NotImplementedError


def get_provider(name: str | None = None, data_dir: Path | str | None = None) -> MarketDataProvider:
    """Build the provider named by `name` (default: `engine.config.DATA_PROVIDER`).

    ``synthetic`` reads `DATA_DIR`, ``csv`` reads `DATA_DIR/csv`, ``vendor`` raises NotImplementedError.
    """
    name = (name or config.DATA_PROVIDER).lower()
    root = Path(data_dir) if data_dir is not None else config.DATA_DIR
    if name == "synthetic":
        return SyntheticProvider(root)
    if name == "csv":
        return CsvProvider(root / "csv")
    if name == "vendor":
        return VendorProvider()
    raise ValueError(f"unknown DATA_PROVIDER {name!r}; expected synthetic, csv or vendor")
