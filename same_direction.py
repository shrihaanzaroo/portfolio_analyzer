"""How often holdings moved in the same direction on the same day, measured from daily returns.
Two unrelated holdings land on about 50% (each day is a coin flip); identical ones on 100%."""
import numpy as np

import engine

RISK_CREDIT_CUTOFF = 0.15  # the same "barely moves" cut engine.true_bets uses before averaging correlation


def same_direction_share(a, b):
    """Share of days both moved (non-zero return) in the same direction, out of the days both have data. None if there are no such days."""
    both = a.to_frame("a").join(b.to_frame("b"), how="inner").dropna()
    if both.empty:
        return None
    x, y = both["a"], both["b"]
    same = (x != 0) & (y != 0) & ((x > 0) == (y > 0))
    return float(same.sum() / len(both))


def risk_holdings(weights, returns):
    """Holdings engine.true_bets counts as risk (it leaves out ones that barely move, such as cash-like funds)."""
    return [t for t in weights if engine.risk_credit(engine.ann_vol(returns[t])) > RISK_CREDIT_CUTOFF]


def average_share(tickers, returns):
    """Average same_direction_share over every pair of tickers; None if there are fewer than two or no pair can be measured.
    Works on the sign of every return at once, because the scenarios re-grade about 100 mixes."""
    signs = np.sign(returns[list(tickers)].to_numpy(dtype=float))
    shares = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            a, b = signs[:, i], signs[:, j]
            both = ~np.isnan(a) & ~np.isnan(b)
            if both.any():
                shares.append(float(((a == b) & (a != 0) & both).sum() / both.sum()))
    return sum(shares) / len(shares) if shares else None


def portfolio_share(weights, returns):
    """Average over pairs of risk holdings, the same pairs engine.true_bets averages correlation over."""
    return average_share(risk_holdings(weights, returns), returns)


def rest_of_portfolio(weights, returns, ticker):
    """The other holdings' combined daily return, their weights rescaled to add up to 1. None if nothing else is held."""
    rest = {t: w for t, w in weights.items() if t != ticker}
    total = sum(rest.values())
    if total <= 0:
        return None
    return engine.portfolio_returns({t: w / total for t, w in rest.items()}, returns)


def share_with_rest(weights, returns, ticker):
    """same_direction_share between one holding and the rest of the portfolio."""
    rest = rest_of_portfolio(weights, returns, ticker)
    return None if rest is None else same_direction_share(returns[ticker], rest)
