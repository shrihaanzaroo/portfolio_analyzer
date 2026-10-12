"""The Check-Up's grade: engine.report_card's five categories plus one it does not cover,
spread across countries. Each category scores 0-4, the
overall letter is their average, discounted by engine.earned when most money sits in cash."""
import engine
import reference_data as ref
import regions
import same_direction

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


def level(points):
    return "good" if points >= 3 else "medium" if points == 2 else "high"


def grade(weights, returns, invested_share):
    card = engine.report_card(weights, returns, invested_share)
    points = {name: POINTS[letter] for name, letter in card["grades"].items()}
    abroad = abroad_share(weights)
    points["Countries"] = country_points(abroad)

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
        industry_short = f"{top['pct']:.0f}% in {top['sector']}"
    else:
        industry_text = "You hold no stocks, so there is no industry split to judge."
        industry_short = "No stocks held"
    if abroad is None:
        country_text = "Nothing here is tied to a country (cash or gold only)."
        country_short = "Not tied to a country"
    elif abroad < 0.05:
        country_text = f"Almost everything is in one country: the {HOME}."
        country_short = f"{abroad * 100:.0f}% outside the U.S."
    else:
        country_text = f"About {abroad * 100:.0f}% of your money is outside the {HOME}."
        country_short = f"{abroad * 100:.0f}% outside the U.S."
    if len(tickers) == 1 and is_fund(tickers[0]):
        together_points, together_text, together_short = 0, "One fund: everything inside it rises and falls with the same market.", "One fund, one market"
    elif len(tickers) == 1:
        together_points, together_text, together_short = 0, "With one holding, everything moves as one.", "One holding"
    elif avg_corr is None:
        together_points, together_text, together_short = 4, "Your holdings are too steady to move together in any way that matters.", "Very steady"
    else:
        together_points = 4 if avg_corr <= 0.2 else 3 if avg_corr <= 0.4 else 2 if avg_corr <= 0.6 else 1
        same = same_direction.portfolio_share(weights, returns)
        if same is None:
            together_text = "Your holdings' daily moves don't overlap enough in time to compare."
            together_short = "Not enough overlap"
        else:
            together_text = f"On a typical day your holdings moved in the same direction about {same * 100:.0f}% of the time (two unrelated holdings would match about half the time)."
            together_short = f"Same direction {same * 100:.0f}% of days"

    dimensions = [
        {"name": "Across companies", "label": "Companies", "score": points["Diversification"], "level": level(points["Diversification"]),
         "short": f"Like {eb:.0f} equal holdings" if eb >= 1.5 else "One company",
         "text": f"{'Looking inside your funds, your' if any(is_fund(t) for t in tickers) else 'Your'} money is spread like about {eb:.0f} equal-sized companies." if eb >= 1.5 else "Your money rides on a single company."},
        {"name": "Across industries", "label": "Industries", "score": points["Sector balance"], "level": level(points["Sector balance"]),
         "short": industry_short, "text": industry_text},
        {"name": "Across countries", "label": "Countries", "score": points["Countries"], "level": level(points["Countries"]),
         "short": country_short, "text": country_text},
        {"name": "Moving independently", "label": "Independence", "score": together_points, "level": level(together_points),
         "short": together_short, "text": together_text},
    ]
    return {"overall": overall, "score": score, "points": points, "dimensions": dimensions}
