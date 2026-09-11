import engine
import reference_data as ref

BIG_POSITION = 0.30
SECTOR_HEAVY = 50
SECTOR_VERY_HEAVY = 65
VOL_RATIO_HIGH = 1.3
CASH_HEAVY = 0.25
FEW_BETS_RATIO = 0.5

LEVEL_ORDER = {"high": 0, "medium": 1, "good": 2}


def sector_examples(max_per_sector=3):
    examples = {}
    for ticker, sector in ref.SECTOR_MAP.items():
        bucket = examples.setdefault(sector, [])
        if len(bucket) < max_per_sector:
            bucket.append(ticker)
    return examples


def is_fund(ticker):
    return ref.spec_lookup(ticker)["br"] > 1


def pct(x):
    return f"{x * 100:.0f}%"


def build_tips(weights, returns, invested_share, hedge_cutoff=0.30, redundant_cutoff=0.75):
    tickers = list(weights.keys())
    n = len(tickers)

    tb = engine.true_bets(weights, returns)
    eb = engine.effective_bets(weights)
    sec = engine.sector_concentration(weights)
    port_vol = engine.portfolio_vol(weights, returns[tickers])
    spy_vol = engine.ann_vol(returns["SPY"])
    card = engine.report_card(weights, returns, invested_share)
    redundant = sorted(engine.redundant_pairs(weights, returns, redundant_cutoff), key=lambda p: -p[2])
    overlaps = sorted(engine.look_through_overlap_pairs(weights), key=lambda p: -p[3])
    if n >= 2:
        is_hedge, hedge_corr = engine.hedge_detection(weights, returns, hedge_cutoff)
    else:
        is_hedge, hedge_corr = {}, {}
    hedges = [t for t in tickers if is_hedge.get(t)]

    total_weights = {t: w * invested_share for t, w in weights.items()}
    cash_share = 1 - invested_share
    biggest, biggest_w = max(total_weights.items(), key=lambda kv: kv[1])
    vol_ratio = port_vol / spy_vol if spy_vol > 0 else None
    true_bets = tb["true_bets"]
    avg_corr = tb["avg_corr"]
    examples = sector_examples()
    user_sectors = {row["sector"] for row in sec["sectors"]}
    missing_sectors = [s for s in ref.SP500 if s not in user_sectors]

    tips = []

    if biggest_w > BIG_POSITION:
        if is_fund(biggest):
            tips.append({
                "level": "good",
                "title": f"{biggest} is your biggest holding ({pct(biggest_w)}), and that's fine",
                "why": f"{biggest} is a fund, so that money is already spread across many companies. A big slice of a broad fund is not the same as a big slice of one stock.",
                "action": "Nothing to fix here. If you add individual stocks later, just watch that no single one of them gets this large.",
            })
        else:
            tips.append({
                "level": "high",
                "title": f"{biggest} alone is {pct(biggest_w)} of your money",
                "why": "One company's bad quarter, lawsuit, or CEO surprise would move your whole portfolio. A common rule of thumb is to keep any single stock under about 10–20%.",
                "action": f"Trim {biggest} and spread that money across a couple of other holdings — or into a broad fund like VTI, which holds thousands of companies at once.",
            })

    if n >= 3 and true_bets < FEW_BETS_RATIO * n:
        corr_text = f" — on average they move together with a correlation of {avg_corr:.2f}" if avg_corr is not None else ""
        tips.append({
            "level": "high",
            "title": f"Your {n} holdings act like only about {true_bets:.1f} separate bets",
            "why": f"They tend to rise and fall at the same time{corr_text}. When that happens, owning more of them doesn't protect you — a bad day for one is a bad day for all.",
            "action": "Add something that moves differently: a company from a different industry, a bond fund like BND, or an international fund like EFA. Another stock similar to the ones you already own mostly won't count as a new bet.",
        })

    if redundant:
        a, b, c, _ = redundant[0]
        extra = f" There are {len(redundant) - 1} more pairs like this." if len(redundant) > 1 else ""
        tips.append({
            "level": "medium",
            "title": f"{a} and {b} move almost in lockstep (correlation {c:.2f})",
            "why": f"Owning both feels like two holdings but behaves like one bigger one.{extra}",
            "action": f"Keep whichever of {a} or {b} you understand and believe in more. If you keep both, think of them as one position when deciding how much to invest.",
        })

    if overlaps and overlaps[0][2] >= 0.01:
        stock, fund, implied, _ = overlaps[0]
        tips.append({
            "level": "medium",
            "title": f"You own {stock} twice — directly, and again through {fund}",
            "why": f"{fund} already holds {stock}. About {pct(implied)} of your money is in {stock} through the fund, on top of the shares you hold directly.",
            "action": f"That's fine if you want {stock} to be a deliberate extra bet — just know your real exposure is bigger than the {stock} line alone shows.",
        })

    max_sector = sec["max_sector"]
    if sec["sectors"] and max_sector > SECTOR_HEAVY:
        top = sec["sectors"][0]
        suggestions = []
        for s in missing_sectors[:2]:
            ex = ", ".join(examples.get(s, [])[:2])
            suggestions.append(f"{s} (e.g. {ex})" if ex else s)
        where = " or ".join(suggestions) if suggestions else "your smallest industries"
        tips.append({
            "level": "high" if max_sector > SECTOR_VERY_HEAVY else "medium",
            "title": f"{top['pct']:.0f}% of your stock money is in {top['sector']}",
            "why": f"The S&P 500 has about {top['sp']:.0f}% there. When one industry has a rough year — and every industry eventually does — most of your money feels it at once.",
            "action": f"Add something from {where}, or a broad index fund like VTI that covers every industry in one go.",
        })

    if n >= 2:
        if hedges:
            best = min(hedges, key=lambda t: hedge_corr[t])
            tips.append({
                "level": "good",
                "title": f"{best} acts as a safety net",
                "why": f"It moves independently of the rest of your portfolio (correlation {hedge_corr[best]:.2f}), so it tends to hold up on days the others fall.",
                "action": "Keep it. This is what makes a bad month survivable.",
            })
        else:
            tips.append({
                "level": "medium",
                "title": "Nothing here tends to hold up when the rest falls",
                "why": "Every holding moves with the others, so on a bad day there's nothing cushioning the drop.",
                "action": "A bond fund (BND or AGG) or gold (GLD) is the classic cushion. Even 10–15% changes how a bad year feels.",
            })

    if vol_ratio is not None:
        if vol_ratio > VOL_RATIO_HIGH:
            tips.append({
                "level": "medium",
                "title": f"Your portfolio swings about {pct(vol_ratio - 1)} more than the market",
                "why": f"In a typical year the S&P 500 moves around ±{pct(spy_vol)}; yours moves around ±{pct(port_vol)}. The real danger isn't the drop itself — it's selling in a panic during one.",
                "action": "Every fix above (spreading across industries, adding a cushion) lowers this number. So does owning a broad index fund as your core.",
            })
        elif vol_ratio <= 1.0:
            tips.append({
                "level": "good",
                "title": "Your ride is no bumpier than the market's",
                "why": f"Your portfolio moves about ±{pct(port_vol)} in a typical year, versus ±{pct(spy_vol)} for the S&P 500.",
                "action": "Keep it that way as you add holdings — check this number again after changes.",
            })

    if cash_share > CASH_HEAVY:
        tips.append({
            "level": "medium",
            "title": f"{pct(cash_share)} of your money is sitting in cash",
            "why": "Cash is a fine cushion, but it doesn't grow — and your grade is discounted because so little is actually invested.",
            "action": "Decide on purpose how much cushion you want (many people keep a few months of expenses outside investing entirely), then put the rest to work in a broad fund.",
        })

    if not redundant and n >= 2:
        tips.append({
            "level": "good",
            "title": "No two holdings are near-duplicates",
            "why": "None of your holdings move in lockstep with another, so each one is pulling its own weight.",
            "action": "When you add something new, check it doesn't just copy something you already own.",
        })

    if sec["sectors"] and max_sector <= 40:
        tips.append({
            "level": "good",
            "title": "Your money is spread across industries",
            "why": f"Your biggest industry is {sec['sectors'][0]['sector']} at {max_sector:.0f}% — no single one dominates.",
            "action": "Nice. Keep an eye on this as you add holdings.",
        })

    tips.sort(key=lambda t: LEVEL_ORDER[t["level"]])

    grade = card["overall"]
    if n == 1:
        # one stock can't score above D no matter how calm it has been
        grade = max(grade, "D")
        verdict = f"Everything is riding on one company. Whatever happens to {biggest} happens to you."
    elif grade in ("A", "B"):
        verdict = f"Looking solid. Your {n} holdings act like about {true_bets:.1f} genuinely separate bets."
    elif grade == "C":
        verdict = f"A decent start — but more of your money is riding on the same thing than it looks. {n} holdings, acting like about {true_bets:.1f} bets."
    else:
        verdict = f"Your holdings mostly move together. This is closer to one big bet wearing {n} different names ({true_bets:.1f} real bets)."

    return {
        "grade": grade,
        "grades": card["grades"],
        "verdict": verdict,
        "tips": tips,
        "facts": {
            "holdings": n,
            "true_bets": true_bets,
            "effective_bets": eb,
            "avg_corr": avg_corr,
            "port_vol": port_vol,
            "spy_vol": spy_vol,
            "biggest": biggest,
            "biggest_pct": biggest_w * 100,
            "total_weights": total_weights,
            "cash_share": cash_share,
            "sectors": sec["sectors"],
            "non_eq": sec["non_eq"],
        },
    }
