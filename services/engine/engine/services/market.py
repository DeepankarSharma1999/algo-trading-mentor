"""Process-wide market data provider handle. Tests swap it with `set_provider`."""

from __future__ import annotations

from engine.data import get_provider
from engine.data.provider import MarketDataProvider

_provider: MarketDataProvider | None = None


def provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def set_provider(p: MarketDataProvider | None) -> None:
    global _provider
    _provider = p
