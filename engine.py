import yfinance as yf
import pandas as pd

def download_prices(tickers, period="10y"):
    raw = yf.download(tickers, period=period, auto_adjust=True)['Close']
    if isinstance(raw, pd.Series):
        raw = raw.to_frame()
    return raw

def compute_returns(prices):
    return prices.pct_change()
import numpy as np

def ann_vol(daily_returns):
    return daily_returns.std() * np.sqrt(252)

def safe_corr(a, b):
    if a.std() == 0 or b.std() == 0:

        return 0.0
    return a.corr(b)
import reference_data as ref

def look_through_hhi(weights):
    nm = {}
    res = 0
    for ticker, wi in weights.items():
        if wi == 0:
            continue
        k = ref.spec_lookup(ticker)
        if k["top"]:
            inside = 0
            for s, pct in k["top"].items():
                x = wi * pct / 100
                nm[s] = nm.get(s, 0) + x
                inside += x
            res += max(0, wi - inside) ** 2 / max(1, k["br"] - len(k["top"]))
        elif k["br"] > 1:
            res += wi * wi / k["br"]
        else:
            nm[ticker] = nm.get(ticker, 0) + wi
    return res + sum(v * v for v in nm.values())

def risk_credit(vol):
    return max(0, min(1, vol / 0.05))

def correlation_matrix(returns_df):
    return returns_df.corr().fillna(0)

def true_bets(weights, returns_df):
    tickers = list(weights.keys())
    vols = {t: ann_vol(returns_df[t]) for t in tickers}
    risk_credits = {t: risk_credit(vols[t]) for t in tickers}
    is_risk = {t: risk_credits[t] > 0.15 for t in tickers}

    risk_weights = {t: weights[t] * risk_credits[t] if is_risk[t] else 0 for t in tickers}
    rw_tot = sum(risk_weights.values())
    rw_hhi = look_through_hhi(risk_weights)
    eff_bets_risk = 0 if rw_tot <= 0 or rw_hhi <= 0 else (rw_tot ** 2) / rw_hhi

    corr = correlation_matrix(returns_df[tickers])
    pair_corrs = [
        corr.loc[tickers[i], tickers[j]]
        for i in range(len(tickers))
        for j in range(i + 1, len(tickers))
        if is_risk[tickers[i]] and is_risk[tickers[j]]
    ]
    avg_corr = sum(pair_corrs) / len(pair_corrs) if pair_corrs else None

    if avg_corr is None:
        bets = eff_bets_risk
    else:
        bets = eff_bets_risk / (1 + (eff_bets_risk - 1) * max(0, avg_corr))

    return {"eff_bets_risk": eff_bets_risk, "avg_corr": avg_corr, "true_bets": bets}
def effective_bets(weights):
    return 1 / look_through_hhi(weights)

def sector_concentration(weights):
    sec_w = {}
    eq_total = 0
    for ticker, w in weights.items():
        k = ref.spec_lookup(ticker)
        if k["mix"]:
            tot = sum(k["mix"].values())
            for s, v in k["mix"].items():
                sec_w[s] = sec_w.get(s, 0) + w * v / tot
            eq_total += w
        elif k["sector"] not in ref.NON_EQUITY:
            sec_w[k["sector"]] = sec_w.get(k["sector"], 0) + w
            eq_total += w

    if eq_total == 0:
        return {"sectors": [], "max_sector": 0, "non_eq": 1 - eq_total}

    sectors = sorted(
        [{"sector": s, "pct": 100 * v / eq_total, "sp": ref.SP500.get(s, 0)} for s, v in sec_w.items()],
        key=lambda x: x["pct"], reverse=True
    )
    return {"sectors": sectors, "max_sector": sectors[0]["pct"], "non_eq": 1 - eq_total}
def hedge_detection(weights, returns, hedge_cutoff):
    is_hedge = {}
    hedge_corr = {}
    for i in weights:
        rest_return = sum(weights[j] * returns[j] for j in weights if j != i)
        # this is "the rest of the portfolio," as a single return series
        hedge_corr[i] = safe_corr(returns[i], rest_return)
        is_hedge[i] = hedge_corr[i] < hedge_cutoff
    return is_hedge, hedge_corr
def redundant_pairs(weights, returns, redundant_cutoff):
    flagged_pairs = []
    for i in weights:
        for j in weights:
            if j > i:
                c = safe_corr(returns[i], returns[j])
                if c > redundant_cutoff:
                    flagged_pairs.append((i, j, c, min(weights[i], weights[j])))
    return flagged_pairs
def look_through_overlap_pairs(weights):
    pairs = []
    for t in weights:
        for f in weights:
            if f == t:
                continue
            k = ref.spec_lookup(f)
            if k["top"] and t in k["top"]:
                implied = weights[f] * k["top"][t] / 100
                overlap = min(weights[t], implied)
                pairs.append((t, f, implied, overlap))
    return pairs


def fund_overlap_pairs(weights):
    funds = [f for f in weights if ref.spec_lookup(f)["top"]]
    pairs = []
    for a in range(len(funds)):
        for b in range(a + 1, len(funds)):
            f1, f2 = funds[a], funds[b]
            top1 = ref.spec_lookup(f1)["top"]
            top2 = ref.spec_lookup(f2)["top"]
            for s in set(top1) & set(top2):
                implied1 = weights[f1] * top1[s] / 100
                implied2 = weights[f2] * top2[s] / 100
                pairs.append((s, f1, f2, min(implied1, implied2)))
    return pairs

def portfolio_vol(weights, returns):
    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers])
    cov = returns[tickers].cov() * 252  # annualize daily covariance
    return np.sqrt(w @ cov.values @ w)
def portfolio_returns(weights, returns):
    tickers = list(weights.keys())
    return sum(weights[t] * returns[t] for t in tickers)

def rolling_win_rate(weights, returns):
    port_returns = portfolio_returns(weights, returns).dropna()
    monthly = (1 + port_returns).resample("ME").prod() - 1
    win_rate = (monthly > 0).mean()
    return {"win_rate": win_rate, "monthly": monthly}
def crash_test(weights, returns, start, end):
    port_returns = portfolio_returns(weights, returns).dropna()
    window = port_returns.loc[start:end]
    if window.empty:
        return None
    path = (1 + window).cumprod() - 1
    return {"total_return": path.iloc[-1], "path": path}
def letter_grade(score):
    if score >= 3.5: return "A"
    if score >= 2.5: return "B"
    if score >= 1.5: return "C"
    if score >= 0.5: return "D"
    return "F"
def earned(score, invested_share, anchor=0.75, floor=1.0):
    inv = max(0, min(1, invested_share / anchor))
    return score * inv + floor * (1 - inv)

def report_card(weights, returns, invested_share):
    tickers = list(weights.keys())
    eb = effective_bets(weights)
    sec = sector_concentration(weights)
    pv = portfolio_vol(weights, returns[tickers])
    spy_vol = ann_vol(returns["SPY"])
    win = rolling_win_rate(weights, returns[tickers])
    redundant = redundant_pairs(weights, returns, 0.75)

    scores = {}

    if eb >= 6: scores["Diversification"] = 4
    elif eb >= 4: scores["Diversification"] = 3
    elif eb >= 2.5: scores["Diversification"] = 2
    elif eb >= 1.5: scores["Diversification"] = 1
    else: scores["Diversification"] = 0

    max_sector = sec["max_sector"]
    if max_sector <= 25: scores["Sector balance"] = 4
    elif max_sector <= 40: scores["Sector balance"] = 3
    elif max_sector <= 55: scores["Sector balance"] = 2
    elif max_sector <= 70: scores["Sector balance"] = 1
    else: scores["Sector balance"] = 0

    if spy_vol > 0:
        vol_ratio = pv / spy_vol
        if vol_ratio <= 1.0: scores["Volatility"] = 4
        elif vol_ratio <= 1.3: scores["Volatility"] = 3
        elif vol_ratio <= 1.6: scores["Volatility"] = 2
        elif vol_ratio <= 2.0: scores["Volatility"] = 1
        else: scores["Volatility"] = 0

    win_rate = win["win_rate"]
    if win_rate >= 0.65: scores["Consistency"] = 4
    elif win_rate >= 0.55: scores["Consistency"] = 3
    elif win_rate >= 0.45: scores["Consistency"] = 2
    elif win_rate >= 0.35: scores["Consistency"] = 1
    else: scores["Consistency"] = 0

    n_redundant = len(redundant)
    if n_redundant == 0: scores["No duplicate bets"] = 4
    elif n_redundant == 1: scores["No duplicate bets"] = 3
    elif n_redundant == 2: scores["No duplicate bets"] = 2
    elif n_redundant == 3: scores["No duplicate bets"] = 1
    else: scores["No duplicate bets"] = 0

    raw_avg = sum(scores.values()) / len(scores)
    adjusted_avg = earned(raw_avg, invested_share)
    overall = letter_grade(adjusted_avg)
    return {"grades": {k: letter_grade(v) for k, v in scores.items()}, "overall": overall, "invested_share": invested_share}








