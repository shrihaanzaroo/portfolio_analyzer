"""Hypothetical swaps: part or all of a large holding replaced by something that moves differently.
Each swap is ranked by gain = (score_after - score_before)
    + 0.5 * (true_bets_after - true_bets_before) / max(1, number of holdings)
    + 0.25 * clip(sharpe_after - sharpe_before, -1, 1), where sharpe = annual return / volatility,
where score is scorecard.grade's 0-4 average, so the grade leads, real diversification comes second, and risk-adjusted return only nudges.
A swap is offered only if the reader would see the difference: the grade letter goes up, the score rises
by half a grade, or real bets rise by half a bet; and real bets never fall.
When fewer than k such swaps exist (a mix that already grades well), the rest are filled with smaller tweaks:
half of one holding, the grade letter and real bets not lower, and at least one number on the card visibly better
(grade, real bets, yearly swing or worst drop as rounded there), ranked by grade letter, real bets, swing and drop gained."""
import math

import engine
import funds  # noqa: F401 -- gives the industry funds below their industry without a Yahoo lookup
import history
import scorecard

CANDIDATES = {
    "BND": "a broad bond fund — it moves independently of stocks",
    "GLD": "gold — it tends to hold up when stocks fall",
    "VTI": "the whole US stock market in one fund",
    "EFA": "large companies outside the US",
    "VWO": "companies in emerging markets like India and China",
    "XLV": "health care companies — a different industry from tech",
    "XLE": "energy companies — they move with oil prices, not with tech",
    "XLP": "everyday household brands — steady on purpose",
    "XLF": "banks and insurers — a different industry from tech",
    "XLU": "utilities — steady and low-drama",
}

SCORE = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
FRACTIONS = (0.5, 1.0)
MAX_SOURCES = 5
TIE_GAP = 0.05
MIN_BETS_GAIN = 0.5
MIN_SCORE_GAIN = 0.5
BETS_TOLERANCE = 0.05


def latest_price(prices, ticker):
    if ticker not in prices.columns:
        return None
    series = prices[ticker].dropna()
    if series.empty or series.iloc[-1] <= 0:
        return None
    return float(series.iloc[-1])


def holdings_to_weights(holdings, price_of):
    values = {t: shares * price_of[t] for t, shares in holdings.items()}
    total = sum(values.values())
    return {t: v / total for t, v in values.items()}


def metrics(holdings, price_of, returns, invested_share):
    weights = holdings_to_weights(holdings, price_of)
    card = scorecard.grade(weights, returns, invested_share)
    perf = history.summary(history.portfolio_daily(weights, returns))
    return {
        "grade": card["overall"],
        "score": card["score"],
        "true_bets": float(scorecard.real_bets(weights, returns)),
        "volatility": float(engine.portfolio_vol(weights, returns[list(weights)])),
        "max_drawdown": perf["max_drawdown"],
        "annual_return": perf["annual_return"],
    }


def sharpe(m):
    return m["annual_return"] / m["volatility"] if m["volatility"] > 0 else 0.0


def swap_gain(before, after, n_holdings):
    bets = (after["true_bets"] - before["true_bets"]) / max(1, n_holdings)
    ratio = max(-1.0, min(1.0, sharpe(after) - sharpe(before)))
    return (after["score"] - before["score"]) + 0.5 * bets + 0.25 * ratio


def visibly_better(before, after):
    bets_gain = after["true_bets"] - before["true_bets"]
    if bets_gain < -BETS_TOLERANCE:
        return False
    return (SCORE[after["grade"]] > SCORE[before["grade"]] or bets_gain >= MIN_BETS_GAIN
            or after["score"] - before["score"] >= MIN_SCORE_GAIN)


def shows_improvement(before, after):
    """True if at least one number on the scenario card, as rounded there, gets better."""
    return (SCORE[after["grade"]] > SCORE[before["grade"]]
            or round(after["true_bets"], 1) > round(before["true_bets"], 1)
            or round(after["volatility"] * 100) < round(before["volatility"] * 100)
            or round(after["max_drawdown"] * 100) > round(before["max_drawdown"] * 100))


def tweak_gain(before, after, n_holdings):
    """How much a smaller tweak improves the mix; None if it isn't worth showing."""
    if SCORE[after["grade"]] < SCORE[before["grade"]] or after["true_bets"] < before["true_bets"] - BETS_TOLERANCE:
        return None
    if not shows_improvement(before, after):
        return None
    vol_drop = before["volatility"] - after["volatility"]
    drawdown_gain = after["max_drawdown"] - before["max_drawdown"]  # drawdowns are negative, so smaller drop = positive
    gain = (SCORE[after["grade"]] - SCORE[before["grade"]]) + 0.5 * (after["true_bets"] - before["true_bets"]) / max(1, n_holdings) + vol_drop + drawdown_gain
    return gain if gain > 0 else None


def shares_word(n):
    return "share" if n == 1 else "shares"


def swap_text(sell, n, total, buy, m):
    if n < total:
        sold = f"{n} of your {total} {sell} shares were"
    elif total == 1:
        sold = f"your {sell} share were"
    else:
        sold = f"your {total} {sell} shares were"
    return f"If {sold} {m} {shares_word(m)} of {buy} instead"


def suggest_swaps(holdings, prices, returns, cash, k=3):
    holdings = {t: s for t, s in holdings.items() if s > 0 and latest_price(prices, t)}
    if not holdings or k <= 0:
        return []
    price_of = {t: latest_price(prices, t) for t in holdings}
    stock_value = sum(s * price_of[t] for t, s in holdings.items())
    invested_share = stock_value / (stock_value + cash) if stock_value + cash > 0 else 1.0
    before = metrics(holdings, price_of, returns, invested_share)

    sources = sorted(holdings, key=lambda t: -holdings[t] * price_of[t])[:MAX_SOURCES]
    for t in CANDIDATES:
        if t not in holdings and t in returns.columns:
            price_of[t] = latest_price(prices, t)
    candidates = [t for t in CANDIDATES if t not in holdings and price_of.get(t)]

    best, tweaks = {}, {}
    for sell in sources:
        total = holdings[sell]
        for buy in candidates:
            for n in sorted({min(total, max(1, round(f * total))) for f in FRACTIONS}):
                m = math.floor(n * price_of[sell] / price_of[buy])
                if m < 1:
                    continue
                new = dict(holdings)
                if n < total:
                    new[sell] = total - n
                else:
                    del new[sell]
                if not new:
                    continue
                new[buy] = m
                after = metrics(new, price_of, returns, invested_share)
                swap = {
                    "sell_ticker": sell,
                    "sell_shares": n,
                    "sell_total_shares": total,
                    "buy_ticker": buy,
                    "buy_shares": m,
                    "why": f"{buy} is {CANDIDATES[buy]}.",
                    "before": dict(before),
                    "after": after,
                    "text": swap_text(sell, n, total, buy, m),
                    "tweak": False,
                }
                gain = swap_gain(before, after, len(holdings))
                if gain > 0 and after["score"] >= before["score"] and visibly_better(before, after):
                    prev = best.get((sell, buy))
                    if prev is None or gain > prev[0] + TIE_GAP:
                        best[(sell, buy)] = (gain, swap)
                elif n < total:
                    small = tweak_gain(before, after, len(holdings))
                    if small is not None and small > tweaks.get((sell, buy), (0,))[0]:
                        tweaks[(sell, buy)] = (small, {**swap, "tweak": True})

    picked, seen = [], set()
    ranked = sorted(best.values(), key=lambda gs: -gs[0]) + sorted(tweaks.values(), key=lambda gs: -gs[0])
    for gain, swap in ranked:
        if swap["buy_ticker"] in seen:
            continue
        seen.add(swap["buy_ticker"])
        picked.append(swap)
        if len(picked) == k:
            break
    return picked
