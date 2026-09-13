import pandas as pd

import engine


def portfolio_daily(weights, returns):
    return engine.portfolio_returns(weights, returns).dropna()


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
