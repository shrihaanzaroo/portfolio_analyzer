"""Concrete swap ideas: sell part or all of a large holding and buy something that moves differently.
Each swap is ranked by gain = (score_after - score_before)
    + 0.5 * (true_bets_after - true_bets_before) / max(1, number of holdings)
    + 0.25 * clip(sharpe_after - sharpe_before, -1, 1), where sharpe = annual return / volatility,
so the report-card score leads, real diversification comes second, and risk-adjusted return only nudges.
A swap is offered only if the reader would see the difference: the grade letter goes up or real bets
rise by at least half a bet, and real bets never fall."""
import math

import engine
import history

CANDIDATES = {
    "BND": "a broad bond fund — it moves independently of stocks",
    "GLD": "gold — it tends to hold up when stocks fall",
    "VTI": "the whole US stock market in one fund",
    "EFA": "large companies outside the US",
    "VWO": "companies in emerging markets like India and China",
    "JNJ": "health care — a different industry from tech",
    "XOM": "energy — it moves with oil prices, not with tech",
    "PG": "everyday household brands — steady on purpose",
    "JPM": "banking — a different industry from tech",
    "NEE": "a utility — steady and low-drama",
}

SCORE = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
FRACTIONS = (0.5, 1.0)
MAX_SOURCES = 5
TIE_GAP = 0.05
MIN_BETS_GAIN = 0.5
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
    card = engine.report_card(weights, returns, invested_share)
    perf = history.summary(history.portfolio_daily(weights, returns))
    grade = card["overall"]
    if len(holdings) == 1:
        grade = max(grade, "D")  # same cap as tips.build_tips: one stock can't score above D
    return {
        "grade": grade,
        "score": sum(SCORE[g] for g in card["grades"].values()) / len(card["grades"]),
        "true_bets": float(engine.true_bets(weights, returns)["true_bets"]),
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
    return SCORE[after["grade"]] > SCORE[before["grade"]] or bets_gain >= MIN_BETS_GAIN


def shares_word(n):
    return "share" if n == 1 else "shares"


def swap_text(sell, n, total, buy, m):
    if n < total:
        sold = f"{n} of your {total} {sell} shares"
    elif total == 1:
        sold = f"your only {sell} share"
    else:
        sold = f"all {total} of your {sell} shares"
    return f"Replace {sold} with {m} {shares_word(m)} of {buy}"


def suggest_swaps(holdings, prices, returns, cash, k=3):
    holdings = {t: int(s) for t, s in holdings.items() if s > 0 and latest_price(prices, t)}
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

    best = {}
    for sell in sources:
        total = holdings[sell]
        for buy in candidates:
            for n in sorted({max(1, round(f * total)) for f in FRACTIONS}):
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
                gain = swap_gain(before, after, len(holdings))
                if gain <= 0 or after["score"] < before["score"] or not visibly_better(before, after):
                    continue
                prev = best.get((sell, buy))
                if prev is not None and gain <= prev[0] + TIE_GAP:
                    continue
                best[(sell, buy)] = (gain, {
                    "sell_ticker": sell,
                    "sell_shares": n,
                    "sell_total_shares": total,
                    "buy_ticker": buy,
                    "buy_shares": m,
                    "why": f"{buy} is {CANDIDATES[buy]}.",
                    "before": dict(before),
                    "after": after,
                    "text": swap_text(sell, n, total, buy, m),
                })

    picked, seen = [], set()
    for gain, swap in sorted(best.values(), key=lambda gs: -gs[0]):
        if swap["buy_ticker"] in seen:
            continue
        seen.add(swap["buy_ticker"])
        picked.append(swap)
        if len(picked) == k:
            break
    return picked
