import reference_data as ref

COUNTRY_OVERRIDES = {"SHOP": "Canada", "LULU": "Canada", "SPOT": "Sweden"}

FUND_COUNTRY_MIX = {
    "EFA": {"Japan": 22, "United Kingdom": 15, "France": 11, "Switzerland": 10, "Germany": 8,
            "Australia": 7, "Netherlands": 4, "Sweden": 3, "Denmark": 3, "Other": 17},
    "VWO": {"China": 30, "India": 20, "Taiwan": 20, "Brazil": 5, "Saudi Arabia": 4,
            "South Africa": 3, "Other": 18},
}


def country_lookup(ticker):
    if ticker in FUND_COUNTRY_MIX:
        return dict(FUND_COUNTRY_MIX[ticker])
    if ticker in ("GLD", "SLV"):
        return {"Gold": 100}
    if ticker == "CASH":
        return {"Cash": 100}
    if ticker in ref.FUND_SPEC:
        return {"United States": 100}
    return {COUNTRY_OVERRIDES.get(ticker, "United States"): 100}


def country_mix(weights):
    total = sum(weights.values())
    if total <= 0:
        return []
    raw = {}
    for ticker, w in weights.items():
        for country, pct in country_lookup(ticker).items():
            raw[country] = raw.get(country, 0) + 100 * w * pct / 100 / total
    named = sorted(((c, p) for c, p in raw.items() if c != "Other"), key=lambda kv: kv[1], reverse=True)
    top = dict(named[:6])
    other = raw.get("Other", 0) + sum(p for _, p in named[6:])
    if other > 0:
        top["Other countries"] = other
    rows = [{"country": c, "pct": p} for c, p in top.items() if p > 0]
    return sorted(rows, key=lambda r: r["pct"], reverse=True)


def asset_class(ticker):
    sector = ref.spec_lookup(ticker)["sector"]
    if sector in ("Bonds", "Gold", "Cash"):
        return sector
    return "Stocks"


def asset_mix(weights):
    total = sum(weights.values())
    if total <= 0:
        return []
    raw = {}
    for ticker, w in weights.items():
        cls = asset_class(ticker)
        raw[cls] = raw.get(cls, 0) + 100 * w / total
    rows = [{"asset": a, "pct": p} for a, p in raw.items() if p > 0]
    return sorted(rows, key=lambda r: r["pct"], reverse=True)
