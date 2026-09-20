"""The Check-Up's grade: engine.report_card's five categories plus two it does not cover,
spread across countries and across types of investment. Each category scores 0-4, the
overall letter is their average, discounted by engine.earned when most money sits in cash."""
import engine
import reference_data as ref
import regions

POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
HOME = "United States"
NOT_COUNTRIES = {"Cash", "Gold"}
# engine.true_bets cannot see inside a fund, so a fund's many companies would count as fully independent bets;
# this is the assumed typical correlation between two companies held by the same fund
WITHIN_FUND_CORRELATION = 0.35


def is_fund(ticker):
    return ref.spec_lookup(ticker)["br"] > 1


def real_bets(weights, returns):
    tb = engine.true_bets(weights, returns)
    n = tb["eff_bets_risk"]
    if n <= 1:
        return tb["true_bets"]
    rho = max(0.0, tb["avg_corr"] or 0.0)
    in_funds = sum(w for t, w in weights.items() if is_fund(t))
    blended = in_funds * max(rho, WITHIN_FUND_CORRELATION) + (1 - in_funds) * rho
    return n / (1 + (n - 1) * blended)


def abroad_share(weights):
    rows = [r for r in regions.country_mix(weights) if r["country"] not in NOT_COUNTRIES]
    total = sum(r["pct"] for r in rows)
    if total <= 0:
        return None
    return sum(r["pct"] for r in rows if r["country"] != HOME) / total


def largest_type(weights):
    rows = regions.asset_mix(weights)
    return (rows[0]["asset"], rows[0]["pct"] / 100) if rows else ("Stocks", 1.0)


def country_points(abroad):
    if abroad is None or abroad >= 0.20: return 4
    if abroad >= 0.10: return 3
    if abroad >= 0.05: return 2
    return 1


def type_points(share):
    if share <= 0.70: return 4
    if share <= 0.80: return 3
    if share <= 0.90: return 2
    if share <= 0.97: return 1
    return 0


def level(points):
    return "good" if points >= 3 else "medium" if points == 2 else "high"


def grade(weights, returns, invested_share):
    card = engine.report_card(weights, returns, invested_share)
    points = {name: POINTS[letter] for name, letter in card["grades"].items()}
    abroad = abroad_share(weights)
    kind, kind_share = largest_type(weights)
    points["Countries"] = country_points(abroad)
    points["Types of investment"] = type_points(kind_share)

    score = sum(points.values()) / len(points)
    overall = engine.letter_grade(engine.earned(score, invested_share))
    tickers = list(weights)
    if len(tickers) == 1 and not is_fund(tickers[0]):
        overall = max(overall, "D")  # one company can't score above D however calm it has been

    eb = engine.effective_bets(weights)
    sec = engine.sector_concentration(weights)
    avg_corr = engine.true_bets(weights, returns)["avg_corr"]

    if sec["sectors"]:
        top = sec["sectors"][0]
        industry_text = f"Your biggest industry is {top['sector']}, at {top['pct']:.0f}% of your stock money (the S&P 500 has about {top['sp']:.0f}% there)."
    else:
        industry_text = "You hold no stocks, so there is no industry split to judge."
    if abroad is None:
        country_text = "Nothing here is tied to a country (cash or gold only)."
    elif abroad < 0.05:
        country_text = f"Almost everything is in one country: the {HOME}."
    else:
        country_text = f"About {abroad * 100:.0f}% of your money is outside the {HOME}."
    if len(tickers) == 1 and is_fund(tickers[0]):
        together_points, together_text = 0, "One fund: everything inside it rises and falls with the same market."
    elif len(tickers) == 1:
        together_points, together_text = 0, "With one holding, everything moves as one."
    elif avg_corr is None:
        together_points, together_text = 4, "Your holdings are too steady to move together in any way that matters."
    else:
        together_points = 4 if avg_corr <= 0.2 else 3 if avg_corr <= 0.4 else 2 if avg_corr <= 0.6 else 1
        together_text = f"On a typical day your holdings' moves match about {max(0, avg_corr) * 100:.0f}% of the time. Lower means they protect each other more."

    dimensions = [
        {"name": "Across companies", "level": level(points["Diversification"]),
         "text": f"{'Looking inside your funds, your' if any(is_fund(t) for t in tickers) else 'Your'} money is spread like about {eb:.0f} equal-sized companies." if eb >= 1.5 else "Your money rides on a single company."},
        {"name": "Across industries", "level": level(points["Sector balance"]), "text": industry_text},
        {"name": "Across countries", "level": level(points["Countries"]), "text": country_text},
        {"name": "Across types of investment", "level": level(points["Types of investment"]),
         "text": f"{kind_share * 100:.0f}% of your invested money is in {kind.lower()}. Stocks, bonds, gold and cash behave differently in a bad year."},
        {"name": "Moving independently", "level": level(together_points), "text": together_text},
    ]
    return {"overall": overall, "score": score, "points": points, "dimensions": dimensions}
