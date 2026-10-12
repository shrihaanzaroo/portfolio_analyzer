"""Runs the whole Check-Up page with Streamlit's AppTest, on the made-up market from conftest.py."""

import ast
import re

import numpy as np
import pandas as pd
import pytest
import streamlit
import streamlit as st
from streamlit.testing.v1 import AppTest

import engine
import funds
import llm_csv
import reference_data as ref
import regions
from conftest import APP


def open_app(tickers=None, shares=None, cash=None):
    """Loads the page once (like opening it in a browser), optionally with holdings and cash filled in."""
    at = AppTest.from_file(APP, default_timeout=120)
    if tickers is not None:
        at.session_state["holdings_df"] = pd.DataFrame(
            {"Ticker": tickers, "Shares": shares or [10] * len(tickers)}
        )
    if cash is not None:
        at.session_state["cash"] = cash
    at.run()
    assert not at.exception
    return at


def click_analyze(at):
    next(b for b in at.button if b.label == "Analyze my portfolio").click()
    at.run()
    return at


def ring_counts(at):
    return [
        m.value.count("class='ring-card'")
        for m in at.markdown
        if "class='ring-card'" in m.value
    ]


def captions(at):
    return [c.value for c in at.caption]


# ---- the normal path ----


@pytest.fixture
def analyzed():
    """The page after clicking Analyze on the default six-stock portfolio."""
    return click_analyze(open_app())


@pytest.mark.slow
def test_analyze_runs_without_errors(analyzed):
    """Analyze finishes with no exception and no error box."""
    assert not analyzed.exception
    assert not analyzed.error


@pytest.mark.slow
def test_six_rings_in_two_groups(analyzed):
    """The grade shows six rings: three under "Spread out" and three under "How it behaves"."""
    assert ring_counts(analyzed) == [3, 3]
    caps = captions(analyzed)
    assert caps.index("**Spread out**") < caps.index("**How it behaves**")


@pytest.mark.slow
def test_report_download_button_is_there(analyzed):
    """There is exactly one download button for the report."""
    assert len(analyzed.get("download_button")) == 1


@pytest.mark.slow
def test_changing_the_growth_window_works(analyzed):
    """Switching the growth chart to 10 years reruns without errors and keeps the download button."""
    analyzed.radio(key="growth_years").set_value("10 years").run()
    assert not analyzed.exception
    assert len(analyzed.get("download_button")) == 1


@pytest.mark.slow
def test_every_compare_with_option_works(analyzed):
    """Each "Compare with" choice reruns without errors."""
    compare = next(s for s in analyzed.selectbox if s.label == "Compare with")
    for option in [o for o in compare.options if o != compare.value]:
        next(s for s in analyzed.selectbox if s.label == "Compare with").set_value(
            option
        ).run()
        assert not analyzed.exception, option


@pytest.mark.slow
def test_scenario_prices_are_downloaded(analyzed, downloads):
    """The industry funds the what-if scenarios try are part of the price download."""
    asked = {t for call in downloads.calls for t in call}
    assert {"XLV", "XLE", "XLP", "XLF", "XLU"} <= asked


@pytest.mark.slow
def test_page_wording_is_neutral(analyzed):
    """The page uses "What usually changes this:" and never suggests a particular split."""
    md = " ".join(m.value for m in analyzed.markdown)
    assert "What usually changes this:" in md and "What would help" not in md
    assert (
        "this tool doesn't suggest any particular split" in md and "about 55%" not in md
    )
    assert "Only a short fixed list of broad funds is tried" in " ".join(
        i.value for i in analyzed.info
    )


@pytest.mark.slow
def test_status_box_ends_complete(monkeypatch):
    """While Analyze runs, the step-by-step status box lists its steps and ends as "Done"."""
    at = open_app(["AAPL", "MSFT", "NVDA"])
    monkeypatch.setattr(
        streamlit, "rerun", lambda *a, **k: None
    )  # so the status box stays on the page
    click_analyze(at)
    assert not at.exception
    boxes = list(at.status)
    assert len(boxes) == 1 and boxes[0].label == "Done" and boxes[0].state == "complete"
    lines = [m.value for m in boxes[0].get("markdown")]
    assert lines[:2] == ["Looking inside your funds", "Downloading prices"]
    assert lines[-1] == "Working out your mix"


@pytest.mark.slow
def test_status_box_shows_the_error_when_nothing_has_prices():
    """If no ticker has prices, the status box ends in an error and nothing is graded."""
    at = click_analyze(open_app(["NOPRICE1"]))
    assert not at.exception
    boxes = list(at.status)
    assert (
        len(boxes) == 1
        and boxes[0].label == "Couldn't finish"
        and boxes[0].state == "error"
    )
    assert any("No price data" in e.value for e in boxes[0].get("error"))
    assert at.session_state["weights"] is None


@pytest.mark.slow
def test_no_deprecation_messages(capfd):
    """Running the page prints no "use_container_width" deprecation notice."""
    at = click_analyze(open_app())
    at.radio(key="growth_years").set_value("10 years").run()
    out, err = capfd.readouterr()
    assert "use_container_width" not in out + err


# ---- cash ----

CASH_NOTE = "Cash is counted as earning nothing; the mix is kept at today's split."


@pytest.mark.slow
def test_cash_caption_appears_when_there_is_cash():
    """With cash entered, the charts say cash is counted as earning nothing."""
    at = click_analyze(open_app(cash=2500.0))
    caps = captions(at)
    assert CASH_NOTE in caps
    assert (
        "What $10,000 in your current mix, including cash, would be worth today, next to whatever you pick to compare it with."
        in caps
    )
    assert ring_counts(at) == [3, 3]


@pytest.mark.slow
def test_no_cash_caption_without_cash():
    """With no cash, the cash note isn't shown."""
    at = click_analyze(open_app(cash=0.0))
    caps = captions(at)
    assert CASH_NOTE not in caps
    assert (
        "What $10,000 in your current mix would be worth today, next to whatever you pick to compare it with."
        in caps
    )


# ---- foreign currency and crypto ----


@pytest.fixture
def world(market, downloads, yahoo):
    """Adds BTC-USD (trades every day), a Japanese stock priced in yen, and the yen-to-dollar rate."""
    p, idx = market.prices, market.index
    days = pd.date_range(idx[0], idx[-1])
    btc = pd.Series(
        10000 * np.cumprod(1 + np.random.default_rng(5).normal(0.001, 0.03, len(days))),
        index=days,
    )
    toyota_usd = pd.Series(
        20
        * np.cumprod(
            1 + 0.6 * market.mkt + np.random.default_rng(7).normal(0, 0.012, market.n)
        ),
        index=idx,
    )
    frame = pd.concat(
        [
            p,
            btc.rename("BTC-USD"),
            (toyota_usd / 0.0067).rename("7203.T"),
            pd.Series(0.0067, index=idx).rename("JPYUSD=X"),
        ],
        axis=1,
        sort=True,
    )
    downloads.frame = frame
    yahoo.info["7203.T"] = {
        "quoteType": "EQUITY",
        "sector": "Consumer Cyclical",
        "country": "Japan",
        "currency": "JPY",
    }
    yahoo.info["BTC-USD"] = {"quoteType": "CRYPTOCURRENCY", "currency": "USD"}
    a = p["AAPL"].iloc[-1]
    shares = {
        "AAPL": 10,
        "BTC-USD": round(10 * a / btc.loc[idx[-1]], 4),
        "7203.T": round(10 * a / toyota_usd.iloc[-1], 4),
    }
    values = {
        "AAPL": shares["AAPL"] * a,
        "BTC-USD": shares["BTC-USD"] * btc.loc[idx[-1]],
        "7203.T": shares["7203.T"] * toyota_usd.iloc[-1],
    }
    return {
        "frame": frame,
        "shares": shares,
        "weights": {t: v / sum(values.values()) for t, v in values.items()},
    }


@pytest.mark.slow
def test_yen_stock_is_weighted_in_dollars(world):
    """A yen-priced stock is converted to dollars before working out the weights."""
    at = click_analyze(open_app(list(world["shares"]), list(world["shares"].values())))
    assert not at.exception and not at.error
    for ticker, expected in world["weights"].items():
        assert abs(at.session_state["weights"][ticker] - expected) < 1e-9
    assert funds.currency_of("7203.T") == "JPY"


@pytest.mark.slow
def test_crypto_weekends_leave_no_gaps(world):
    """BTC's weekend prices are dropped so its daily returns have no gaps."""
    import history

    at = click_analyze(open_app(list(world["shares"]), list(world["shares"].values())))
    returns = at.session_state["returns"]
    assert (returns.index.dayofweek < 5).all()
    assert history.window(returns, 3)["BTC-USD"].isna().sum() == 0


@pytest.mark.slow
def test_stock_without_an_exchange_rate_is_dropped_with_a_warning(world, downloads):
    """With no yen rate available, the yen stock is left out and a warning says so."""
    downloads.frame = world["frame"].drop(columns="JPYUSD=X")
    at = click_analyze(open_app(list(world["shares"]), list(world["shares"].values())))
    assert not at.exception
    assert "Couldn't convert 7203.T from JPY to dollars, so it was left out." in [
        w.value for w in at.warning
    ]
    assert set(at.session_state["weights"]) == {"AAPL", "BTC-USD"}
    assert "7203.T" not in list(at.session_state["holdings_df"]["Ticker"])


# ---- industries from Yahoo and the AI ----


@pytest.fixture
def extra_tickers(market, yahoo):
    """Gives WM, KR and a few made-up stocks Yahoo answers (some with no sector) and prices."""
    p, rng = market.prices, market.rng
    for t in ["AIS", "UNK1", "UNK2"]:
        p[t] = 100 * np.cumprod(1 + 0.9 * market.mkt + rng.normal(0, 0.012, market.n))
        yahoo.info[t] = {"quoteType": "EQUITY"}
    yahoo.info["WM"] = {
        "quoteType": "EQUITY",
        "sector": "Industrials",
        "country": "United States",
    }
    yahoo.info["KR"] = {
        "quoteType": "EQUITY",
        "sector": "Consumer Defensive",
        "country": "United States",
    }
    yahoo.info["GHOST"] = {
        "quoteType": "EQUITY"
    }  # Yahoo knows it but there are no prices
    return yahoo


def industry_captions(at):
    return [c for c in captions(at) if "industry" in c.lower()]


@pytest.mark.slow
def test_ai_fills_in_missing_industries(extra_tickers, monkeypatch):
    """Stocks Yahoo has no industry for are sent to the AI (only if they have prices), and the page says so."""
    asked = []

    def fake_classify(tickers):
        asked.append(list(tickers))
        return {"AIS": {"sector": "Materials", "country": "Chile"}}

    monkeypatch.setattr(llm_csv, "available", lambda: True)
    monkeypatch.setattr(llm_csv, "classify_stocks", fake_classify)
    at = click_analyze(open_app(["WM", "KR", "AIS", "UNK1", "UNK2", "GHOST", "FAKEZ"]))
    assert not at.exception
    assert asked == [["AIS", "UNK1", "UNK2"]]
    assert industry_captions(at) == [
        "Industry and country for AIS were estimated by AI because Yahoo Finance didn't list them.",
        "Couldn't find the industry for UNK1, UNK2, so they're counted as \"Other\".",
    ]
    assert "GHOST" not in ref.SECTOR_MAP and "FAKEZ" not in ref.SECTOR_MAP


@pytest.mark.slow
def test_ai_failure_is_quietly_skipped(extra_tickers, monkeypatch):
    """If the AI call fails, the analysis still finishes and the stock is counted as "Other"."""

    def broken(tickers):
        raise ValueError("AI down")

    monkeypatch.setattr(llm_csv, "available", lambda: True)
    monkeypatch.setattr(llm_csv, "classify_stocks", broken)
    at = click_analyze(open_app(["WM", "UNK1"]))
    assert not at.exception
    assert industry_captions(at) == [
        "Couldn't find the industry for UNK1, so it's counted as \"Other\"."
    ]


# ---- small helpers inside the app file ----


@pytest.fixture
def app_helpers():
    """Pulls a few helper functions out of the app file without running the whole page."""
    wanted = {
        "IncompleteDownload",
        "_complete_download",
        "cached_download",
        "SHARE_CLASS",
        "normalize_ticker",
        "df_tickers",
        "holdings_df_to_dict",
    }
    tree = ast.parse(open(APP).read())
    picked = [
        node
        for node in tree.body
        if getattr(node, "name", None) in wanted
        or (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) in wanted for t in node.targets)
        )
    ]
    namespace = {"st": st, "pd": pd, "engine": engine, "re": re}
    exec(compile(ast.Module(body=picked, type_ignores=[]), APP, "exec"), namespace)
    return namespace


def test_complete_downloads_are_cached(app_helpers, downloads):
    """A download with every ticker is remembered, so Yahoo is asked only once."""
    first = app_helpers["cached_download"](["AAPL", "MSFT"], "max")
    second = app_helpers["cached_download"](["AAPL", "MSFT"], "max")
    assert len(downloads.calls) == 1 and first.equals(second)


def test_partial_downloads_are_asked_again(app_helpers, downloads):
    """A download missing a ticker isn't remembered, but what did arrive is still returned."""
    first = app_helpers["cached_download"](["AAPL", "NOPE"], "max")
    app_helpers["cached_download"](["AAPL", "NOPE"], "max")
    assert len(downloads.calls) == 2 and list(first.columns) == ["AAPL"]


def test_failed_download_gives_an_empty_table(app_helpers, monkeypatch):
    """If the download raises an error, an empty table comes back instead of a crash."""

    def broken(tickers, period="10y"):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(engine, "download_prices", broken)
    result = app_helpers["cached_download"](["ZZZ"], "max")
    assert isinstance(result, pd.DataFrame) and result.empty


def test_holdings_table_is_cleaned_up(app_helpers):
    """Tickers are upper-cased, share classes use a dash (BRK-B), and blank rows are dropped."""
    df = pd.DataFrame(
        {
            "Ticker": [
                "brk.b",
                "BRK.A",
                "7203.T",
                "VOD.L",
                "SHOP.TO",
                "",
                None,
                np.nan,
                "nan",
                "None",
                "  ",
                "ABCDE.B",
                "BF.B",
                "AAPL",
            ],
            "Shares": list(range(1, 15)),
        }
    )
    assert app_helpers["holdings_df_to_dict"](df) == {
        "BRK-B": 1,
        "BRK-A": 2,
        "7203.T": 3,
        "VOD.L": 4,
        "SHOP.TO": 5,
        "ABCDE.B": 12,
        "BF-B": 13,
        "AAPL": 14,
    }
