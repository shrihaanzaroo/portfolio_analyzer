import pandas as pd

import engine


def portfolio_daily(weights, returns):
    return engine.portfolio_returns(weights, returns).dropna()


def filled_daily(weights, returns, min_coverage=0.5):
    """Daily return using whichever holdings had prices that day, their weights scaled up to fill the gap.
    Days are kept only while the holdings that existed make up at least min_coverage of the money."""
    frame = returns[list(weights)]
    w = pd.Series(weights)
    covered = frame.notna().mul(w, axis=1).sum(axis=1)
    daily = frame.fillna(0).mul(w, axis=1).sum(axis=1) / covered.where(covered > 0)
    return daily[covered >= min_coverage].dropna()


def monthly_returns(daily):
    return (1 + daily).resample("ME").prod() - 1


def cumulative_returns(daily):
    return (1 + daily.dropna()).cumprod() - 1


def growth_of(daily, start=10000.0):
    return start * (1 + cumulative_returns(daily))


def drawdown_series(daily):
    growth = growth_of(daily)
    return growth / growth.cummax() - 1


def max_drawdown(daily):
    dd = drawdown_series(daily)
    if dd.empty:
        return 0.0
    return float(dd.min())


def total_return(daily):
    clean = daily.dropna()
    if clean.empty:
        return 0.0
    return float((1 + clean).prod() - 1)


def annualized_return(daily):
    clean = daily.dropna()
    if len(clean) < 2:
        return 0.0
    return float((1 + total_return(clean)) ** (252 / len(clean)) - 1)


def summary(daily):
    clean = daily.dropna()
    return {
        "total_return": total_return(clean),
        "annual_return": annualized_return(clean),
        "max_drawdown": max_drawdown(clean),
        "volatility": float(engine.ann_vol(clean)),
    }


def window_start(returns, years=None):
    if years is None:
        return returns.index[0]
    return returns.index[-1] - pd.DateOffset(years=years)


def window(returns, years=None):
    if years is None or returns.empty:
        return returns
    return returns[returns.index >= window_start(returns, years)]


def date_text(date):
    return f"{date:%b} {date.day}, {date.year}"


def date_range_text(series):
    return f"{date_text(series.index[0])} – {date_text(series.index[-1])}"


def short_range_text(start, end):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.year != end.year:
        return f"{date_text(start)} – {date_text(end)}"
    return f"{start:%b} {start.day} – {date_text(end)}"


def late_starter(firsts, actual_start, requested_start, grace_days=30):
    if actual_start <= requested_start + pd.Timedelta(days=grace_days):
        return None
    known = {t: d for t, d in firsts.items() if d is not None}
    return max(known, key=known.get) if known else None


def align_to_dates(prices, dates, limit=5):
    """Puts prices on the given dates, carrying a price forward over at most `limit` of those dates
    where it is missing (never back before a ticker's first price)."""
    return prices.reindex(pd.DatetimeIndex(dates)).ffill(limit=limit)


def align_to_market(prices, anchor="SPY", limit=5):
    """Keeps only the days the anchor traded, so weekend prices (crypto) or other markets' holidays don't leave gaps
    in daily returns. Returns prices unchanged when the anchor wasn't downloaded."""
    if anchor not in prices.columns:
        return prices
    return align_to_dates(prices, prices.index[prices[anchor].notna()], limit)


# Yahoo quotes some markets in hundredths of the currency (London in pence, Tel Aviv in agorot, Johannesburg in cents)
MINOR_UNITS = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ILA": ("ILS", 100), "ZAc": ("ZAR", 100), "ZAC": ("ZAR", 100)}


def fx_ticker(currency):
    """Yahoo's ticker for the price of one unit of `currency` in US dollars."""
    base = MINOR_UNITS.get(currency, (currency, 1))[0]
    return f"{base}USD=X"


def to_usd(prices, currencies, fx, limit=5):
    """Converts the columns named in `currencies` ({ticker: currency code}) to US dollars using FX closes in `fx`.
    Returns (converted prices, {ticker: currency} that couldn't be converted); those columns are dropped."""
    out = prices.copy()
    missing = {}
    for ticker, code in currencies.items():
        if ticker not in out.columns or not code or code == "USD":
            continue
        divisor = MINOR_UNITS.get(code, (code, 1))[1]
        pair = fx_ticker(code)
        rate = None
        if fx is not None and pair in fx.columns and not fx[pair].dropna().empty:
            closes = fx[pair].dropna()
            rate = closes.reindex(closes.index.union(out.index)).ffill(limit=limit).reindex(out.index)
        has_price = out[ticker].notna()
        if rate is None or rate[has_price].dropna().empty:
            missing[ticker] = code
            out = out.drop(columns=ticker)
            continue
        out[ticker] = out[ticker] / divisor * rate
    return out, missing
