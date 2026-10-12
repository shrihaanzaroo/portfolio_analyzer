"""Shared test setup.

Every test runs offline: prices come from a made-up (but repeatable) market, Yahoo Finance and the AI
are replaced by fakes, and anything the app remembers between runs is put back afterwards.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import streamlit as st
import yfinance

import engine
import funds
import llm_csv
import reference_data as ref
import regions

APP = str(Path(__file__).resolve().parent.parent / "portfolio_analyzer_simple.py")

# (beta to the market, daily noise) for each made-up ticker
STOCKS = {
    "AAPL": (1.2, 0.012),
    "MSFT": (1.1, 0.011),
    "NVDA": (1.6, 0.025),
    "GOOGL": (1.1, 0.013),
    "META": (1.3, 0.02),
    "AMD": (1.6, 0.025),
    "JPM": (1.1, 0.01),
    "BAC": (1.2, 0.009),
    "WFC": (1.1, 0.009),
    "C": (1.2, 0.01),
    "WM": (0.7, 0.01),
    "MMM": (0.9, 0.012),
    "KR": (0.4, 0.013),
    "TJX": (0.9, 0.012),
    "ZTS": (0.8, 0.013),
    "SPY": (1.0, 0.001),
    "QQQ": (1.2, 0.004),
    "VTI": (1.02, 0.0015),
    "BND": (0.05, 0.003),
    "GLD": (0.05, 0.009),
    "EFA": (0.8, 0.006),
    "VWO": (0.8, 0.009),
    "JNJ": (0.5, 0.01),
    "XOM": (0.8, 0.016),
    "PG": (0.4, 0.009),
    "NEE": (0.5, 0.012),
}
# the industry funds the what-if scenarios try (their own random numbers, so the series above never change)
SECTOR_FUNDS = {
    "XLV": (0.7, 0.007),
    "XLE": (0.9, 0.014),
    "XLP": (0.55, 0.006),
    "XLF": (1.1, 0.007),
    "XLU": (0.5, 0.009),
}


def make_market():
    """About ten years of daily prices for the tickers above, always the same numbers (seeded)."""
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2016-01-01", "2026-10-09")
    n = len(idx)
    mkt = rng.normal(0.0004, 0.011, n)
    rets = pd.DataFrame(
        {t: b * mkt + rng.normal(0.0, s, n) for t, (b, s) in STOCKS.items()}, index=idx
    )
    prices = 100 * (1 + rets).cumprod()
    prices.iloc[0] = 100
    rng2 = np.random.default_rng(1)
    for t, (b, s) in SECTOR_FUNDS.items():
        prices[t] = 100 * np.cumprod(1 + b * mkt + rng2.normal(0, s, n))
    return SimpleNamespace(prices=prices, mkt=mkt, rng=rng, n=n, index=idx)


@pytest.fixture
def market():
    """The made-up market: .prices (a DataFrame), .mkt (daily market moves), .rng (for extra tickers)."""
    return make_market()


@pytest.fixture
def prices(market):
    return market.prices


@pytest.fixture
def returns3(prices):
    """Daily returns for the last three years, the window the grade uses."""
    import history

    return history.window(engine.compute_returns(prices), 3)


class FakeYahoo:
    """Stands in for yfinance.Ticker. Put Yahoo's answers in .info[ticker]; tickers in .down raise an error."""

    def __init__(self):
        self.info = {}
        self.down = set()
        self.calls = []
        self.fund_data = {
            "fund_overview": {},
            "asset_classes": {},
            "sector_weightings": {},
            "top_holdings": None,
        }

    def ticker(self, symbol):
        self.calls.append(symbol)
        if symbol in self.down:
            raise ConnectionError("unreachable")
        return SimpleNamespace(
            info=self.info.get(symbol, {}), funds_data=SimpleNamespace(**self.fund_data)
        )


@pytest.fixture
def yahoo():
    """The fake Yahoo Finance every test uses (see FakeYahoo)."""
    return FakeYahoo()


@pytest.fixture
def downloads(prices):
    """Controls what engine.download_prices returns: set .frame to another table; .calls lists each request."""
    state = SimpleNamespace(frame=prices, calls=[])

    def fake_download(tickers, period="10y"):
        tickers = [tickers] if isinstance(tickers, str) else list(tickers)
        state.calls.append(tuple(tickers))
        frame = state.frame
        return (
            frame[[t for t in tickers if t in frame.columns]].dropna(how="all").copy()
        )

    state.fake = fake_download
    return state


def _no_network(*args, **kwargs):
    raise RuntimeError("tests must not use the network")


@pytest.fixture(autouse=True)
def offline(monkeypatch, yahoo, downloads):
    """Runs around every test: no network, no AI, and app-wide lookups put back as they were."""
    monkeypatch.setattr(engine, "download_prices", downloads.fake)
    monkeypatch.setattr(yfinance, "Ticker", yahoo.ticker)
    monkeypatch.setattr(yfinance, "download", _no_network)
    monkeypatch.setattr(llm_csv, "available", lambda: False)
    monkeypatch.setattr(llm_csv, "classify_stocks", lambda tickers: {})
    monkeypatch.setattr(llm_csv, "_ask", _no_network)

    def no_estimates(items):
        raise ValueError("offline")

    monkeypatch.setattr(llm_csv, "estimate_funds", no_estimates)

    saved = {
        "sector_map": dict(ref.SECTOR_MAP),
        "fund_spec": dict(ref.FUND_SPEC),
        "countries": dict(regions.COUNTRY_OVERRIDES),
        "cache": dict(funds._cache),
        "stock_info": dict(funds.STOCK_INFO),
        "currency": dict(funds.CURRENCY),
    }
    st.cache_data.clear()
    yield
    st.cache_data.clear()
    for target, key in (
        (ref.SECTOR_MAP, "sector_map"),
        (ref.FUND_SPEC, "fund_spec"),
        (regions.COUNTRY_OVERRIDES, "countries"),
        (funds._cache, "cache"),
        (funds.STOCK_INFO, "stock_info"),
        (funds.CURRENCY, "currency"),
    ):
        target.clear()
        target.update(saved[key])
