import numpy as np
import pandas as pd
import pytest

import engine
import history

# ---- align_to_market: crypto trades every day, the S&P 500 only on weekdays ----

DAYS = pd.date_range("2023-01-02", "2023-03-31")  # every calendar day
WEEKDAYS = DAYS[DAYS.dayofweek < 5]


@pytest.fixture
def raw():
    """SPY on weekdays, BTC-USD every day, and LATE starting 20 weekdays in."""
    spy = pd.Series(np.linspace(400, 420, len(WEEKDAYS)), index=WEEKDAYS)
    btc = pd.Series(20000 + np.arange(len(DAYS)) * 10.0, index=DAYS)
    late = pd.Series(50.0 + np.arange(len(WEEKDAYS) - 20), index=WEEKDAYS[20:])
    return pd.concat({"SPY": spy, "BTC-USD": btc, "LATE": late}, axis=1, sort=True)


def test_align_keeps_only_market_days(raw):
    """After aligning, the dates are exactly the days SPY traded."""
    assert list(history.align_to_market(raw).index) == list(WEEKDAYS)


def test_align_leaves_no_gaps_in_daily_returns(raw):
    """Neither SPY nor BTC has missing returns once weekends are dropped."""
    r = engine.compute_returns(history.align_to_market(raw))
    assert r["BTC-USD"].iloc[1:].isna().sum() == 0
    assert r["SPY"].iloc[1:].isna().sum() == 0


def test_monday_return_is_measured_from_friday(raw):
    """BTC's Monday return compares Monday's price with Friday's."""
    r = engine.compute_returns(history.align_to_market(raw))
    monday = r.index[r.index.dayofweek == 0][1]
    friday = monday - pd.Timedelta(days=3)
    assert (
        abs(
            r.loc[monday, "BTC-USD"]
            - (raw.loc[monday, "BTC-USD"] / raw.loc[friday, "BTC-USD"] - 1)
        )
        < 1e-12
    )


def test_late_starter_is_not_filled_backwards(raw):
    """A ticker that started trading later stays empty before its first price."""
    aligned = history.align_to_market(raw)
    assert aligned["LATE"].iloc[:20].isna().all()
    assert aligned["LATE"].iloc[20:].notna().all()


def test_without_spy_prices_are_unchanged(raw):
    """If SPY wasn't downloaded, the table comes back as it was."""
    no_spy = raw.drop(columns="SPY")
    assert history.align_to_market(no_spy).equals(no_spy)


def test_gaps_are_filled_for_at_most_five_days(raw):
    """A missing stretch is carried forward for five days only."""
    gap = raw.copy()
    gap.loc[WEEKDAYS[30] : WEEKDAYS[40], "LATE"] = np.nan
    filled = history.align_to_market(gap)["LATE"]
    assert int(filled.loc[WEEKDAYS[30] : WEEKDAYS[40]].notna().sum()) == 5


# ---- to_usd: converting foreign prices to dollars ----

FX_DAYS = pd.bdate_range("2024-01-01", periods=10)


@pytest.fixture
def converted():
    prices = pd.DataFrame(
        {"7203.T": 3000.0, "VOD.L": 70.0, "AAPL": 190.0, "BADFX": 10.0}, index=FX_DAYS
    )
    fx = pd.DataFrame(
        {"JPYUSD=X": 0.0067, "GBPUSD=X": 1.25}, index=FX_DAYS.drop(FX_DAYS[3])
    )  # one FX day missing
    out, missing = history.to_usd(
        prices, {"7203.T": "JPY", "VOD.L": "GBp", "AAPL": "USD", "BADFX": "CHF"}, fx
    )
    return prices, out, missing


def test_yen_prices_become_dollars(converted):
    """A yen price is multiplied by the yen-to-dollar rate, even on a day the rate is missing."""
    _, out, _ = converted
    assert abs(out["7203.T"].iloc[-1] - 3000 * 0.0067) < 1e-9
    assert abs(out.loc[FX_DAYS[3], "7203.T"] - 3000 * 0.0067) < 1e-9


def test_pence_are_turned_into_pounds_first(converted):
    """London prices in pence are divided by 100 before converting."""
    _, out, _ = converted
    assert abs(out["VOD.L"].iloc[-1] - 0.70 * 1.25) < 1e-9


def test_dollar_prices_are_untouched(converted):
    """US dollar prices don't change."""
    prices, out, _ = converted
    assert out["AAPL"].equals(prices["AAPL"])


def test_missing_rate_drops_the_ticker(converted):
    """A ticker with no exchange rate is left out and reported."""
    _, out, missing = converted
    assert missing == {"BADFX": "CHF"} and "BADFX" not in out.columns


def test_no_fx_data_at_all_reports_every_foreign_ticker():
    """With an empty FX table, every foreign ticker is reported as unconverted."""
    prices = pd.DataFrame({"7203.T": 3000.0}, index=FX_DAYS)
    _, missing = history.to_usd(prices, {"7203.T": "JPY"}, pd.DataFrame())
    assert missing == {"7203.T": "JPY"}


def test_fx_ticker_names():
    """Minor units (pence, agorot, cents) use the main currency's FX ticker."""
    assert history.fx_ticker("GBp") == "GBPUSD=X"
    assert history.fx_ticker("ILA") == "ILSUSD=X"
    assert history.fx_ticker("ZAc") == "ZARUSD=X"
    assert history.fx_ticker("JPY") == "JPYUSD=X"


# ---- with_cash: cash earns nothing ----


@pytest.fixture
def daily(returns3):
    return history.filled_daily({"AAPL": 0.5, "BND": 0.3, "XOM": 0.2}, returns3)


def test_growth_with_cash_only_grows_the_invested_part(daily):
    """With 20% in cash, $10,000 grows by 80% of each day's return."""
    growth = history.growth_of(history.with_cash(daily, 0.8))
    expected = 10000 * (1 + 0.8 * daily).cumprod()
    assert np.allclose(growth.values, expected.values, rtol=1e-12, atol=1e-9)


def test_total_return_with_cash(daily):
    """Total return with cash compounds 80% of each day's return."""
    assert (
        abs(
            history.total_return(history.with_cash(daily, 0.8))
            - ((1 + 0.8 * daily).prod() - 1)
        )
        < 1e-12
    )


def test_fully_invested_is_unchanged(daily):
    """With no cash the daily returns are the same."""
    assert history.with_cash(daily, 1.0).equals(daily)
