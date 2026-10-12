"""The Check-Up's grade: engine.report_card's five categories plus one it does not cover,
spread across countries. Each category scores 0-4, the
overall letter is their average, discounted by engine.earned when most money sits in cash.
grade() also describes each graded category as a "dimension" (one ring on the page), in two groups."""
import engine
import reference_data as ref
import regions
import same_direction

POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
HOME = "United States"
NOT_COUNTRIES = {"Cash", "Gold"}
SPREAD_OUT = "Spread out"
BEHAVES = "How it behaves"
REDUNDANT_CUTOFF = 0.75  # the correlation engine.report_card counts as a near-duplicate pair
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

    def dimension(category, name, label, group, short, text):
        return {"name": name, "label": label, "group": group, "category": category, "score": points[category],
                "level": level(points[category]), "short": short, "text": text}

    dimensions = [
        dimension("Diversification", "Across companies", "Companies", SPREAD_OUT,
                  f"Like {eb:.0f} equal holdings" if eb >= 1.5 else "One company",
                  f"{'Looking inside your funds, your' if any(is_fund(t) for t in tickers) else 'Your'} money is spread like about {eb:.0f} equal-sized companies." if eb >= 1.5 else "Your money rides on a single company."),
        dimension("Sector balance", "Across industries", "Industries", SPREAD_OUT, industry_short, industry_text),
        dimension("Countries", "Across countries", "Countries", SPREAD_OUT, country_short, country_text),
    ]

    if "Volatility" in points:  # engine.report_card leaves it out when the S&P 500's swing can't be measured
        port_vol = engine.portfolio_vol(weights, returns[tickers])
        spy_vol = engine.ann_vol(returns["SPY"])
        dimensions.append(dimension(
            "Volatility", "Steadiness compared with the market", "Steadiness", BEHAVES,
            f"{port_vol / spy_vol:.1f}× the market's swings",
            f"Your typical yearly swing is about ±{port_vol * 100:.0f}%, versus ±{spy_vol * 100:.0f}% for the S&P 500."))

    monthly = engine.rolling_win_rate(weights, returns[tickers])["monthly"]
    if len(monthly):
        ups, months = int((monthly > 0).sum()), len(monthly)
        consistency_text = f"Your mix ended higher in {ups} of {months} calendar months ({ups / months * 100:.0f}%). Around 6 in 10 is typical for the overall market."
        consistency_short = f"Up in {ups / months * 100:.0f}% of months"
    else:
        consistency_text, consistency_short = "There isn't enough price history to count months.", "Not enough history"
    dimensions.append(dimension("Consistency", "Consistency month to month", "Consistency", BEHAVES, consistency_short, consistency_text))

    pairs = len(engine.redundant_pairs(weights, returns, REDUNDANT_CUTOFF))
    if len(tickers) == 1:
        duplicates_text = "With one holding there is nothing to duplicate."
    elif pairs == 0:
        duplicates_text = f"No two of your holdings moved almost in lockstep (a daily correlation above {REDUNDANT_CUTOFF})."
    else:
        duplicates_text = f"{pairs} pair{'' if pairs == 1 else 's'} of your holdings moved almost in lockstep (a daily correlation above {REDUNDANT_CUTOFF})."
    same = same_direction.portfolio_share(weights, returns)
    if same is not None:
        duplicates_text += f" On a typical day your holdings moved in the same direction about {same * 100:.0f}% of the time (two unrelated holdings would match about half the time)."
    dimensions.append(dimension(
        "No duplicate bets", "Near-duplicate holdings", "Duplicates", BEHAVES,
        "No near-duplicates" if pairs == 0 else f"{pairs} near-duplicate pair{'' if pairs == 1 else 's'}", duplicates_text))

    return {"overall": overall, "score": score, "points": points, "dimensions": dimensions}
