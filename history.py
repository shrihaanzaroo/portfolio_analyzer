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
