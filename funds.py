import re

import yfinance as yf

import reference_data as ref
import regions

SECTOR_NAMES = {
    "technology": "Technology",
    "financial_services": "Financials",
    "healthcare": "Health Care",
    "consumer_cyclical": "Consumer Discretionary",
    "communication_services": "Communication Services",
    "industrials": "Industrials",
    "consumer_defensive": "Consumer Staples",
    "energy": "Energy",
    "utilities": "Utilities",
    "realestate": "Real Estate",
    "basic_materials": "Materials",
}
SECTOR_CATEGORIES = {
    "technology": "Technology",
    "health": "Health Care",
    "financial": "Financials",
    "energy": "Energy",
    "utilities": "Utilities",
    "real estate": "Real Estate",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "industrials": "Industrials",
    "communications": "Communication Services",
    "natural resources": "Materials",
}
# effective breadth, on the same scale reference_data uses (SPY = 50), not a raw holdings count
BREADTH_BY_CATEGORY = [
    ("target-date", 60), ("allocation", 60), ("total", 60), ("large blend", 50), ("large value", 40),
    ("large growth", 40), ("mid-cap", 60), ("small", 100), ("foreign", 50), ("world", 60), ("global", 60),
    ("emerging", 60), ("government", 10), ("bond", 100), ("intermediate", 100), ("short-term", 100),
    ("long-term", 100), ("corporate", 100), ("high yield", 100), ("muni", 100), ("inflation", 100),
    ("precious", 1), ("commodit", 1),
]
DEFAULT_BREADTH = 40
STOCK_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,5}$")

_cache = {}


def breadth_for(category):
    cat = (category or "").lower()
    for key, breadth in BREADTH_BY_CATEGORY:
        if key in cat:
            return breadth
    return DEFAULT_BREADTH


def countries_for(category):
    cat = (category or "").lower()
    if "emerging" in cat:
        return dict(regions.FUND_COUNTRY_MIX["VWO"])
    if any(k in cat for k in ("foreign", "europe", "japan", "pacific", "international")):
        return dict(regions.FUND_COUNTRY_MIX["EFA"])
    if "world" in cat or "global" in cat:
        return {"United States": 60, **{c: round(p * 0.4, 1) for c, p in regions.FUND_COUNTRY_MIX["EFA"].items()}}
    return None


def looks_like_stock(symbol):
    s = str(symbol)
    if not STOCK_TICKER.match(s):
        return False
    return not (len(s) == 5 and s.endswith("X"))


def fetch(ticker):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception:
        return None
    if info.get("quoteType") not in ("ETF", "MUTUALFUND"):
        return None

    def grab(attr):
        try:
            return getattr(tk.funds_data, attr)
        except Exception:
            return None

    name = info.get("longName") or info.get("shortName") or ticker
    overview = grab("fund_overview") or {}
    category = overview.get("categoryName") or info.get("category") or ""
    cat = category.lower()

    assets_raw = grab("asset_classes") or {}
    stock = max(0.0, float(assets_raw.get("stockPosition") or 0)) * 100
    bond = max(0.0, float(assets_raw.get("bondPosition") or 0)) * 100
    cash = max(0.0, float(assets_raw.get("cashPosition") or 0)) * 100

    weightings = grab("sector_weightings") or {}
    mix = {SECTOR_NAMES[k]: round(float(v) * 100, 1) for k, v in weightings.items() if k in SECTOR_NAMES and v and v > 0}

    top = {}
    holdings = grab("top_holdings")
    if holdings is not None and "Holding Percent" in getattr(holdings, "columns", []):
        for symbol, share in holdings["Holding Percent"].items():
            if looks_like_stock(symbol) and share and share > 0:
                top[str(symbol)] = round(float(share) * 100, 2)

    if bond >= 70 or (stock == 0 and "bond" in cat):
        sector = "Bonds"
    elif "precious" in cat or "gold" in name.lower():
        sector = "Gold"
    else:
        sector = next((s for k, s in SECTOR_CATEGORIES.items() if k in cat), "Index")

    entry = {"sector": sector, "br": breadth_for(category), "name": name, "category": category}
    if sector not in ("Bonds", "Gold"):
        if mix:
            entry["mix"] = mix
        if top:
            entry["top"] = top
    if stock + bond + cash > 0:
        entry["assets"] = {"Stocks": stock, "Bonds": bond, "Cash": cash}
    countries = countries_for(category)
    if countries:
        entry["countries"] = countries
    return entry


def register(tickers):
    found = {}
    for t in tickers:
        if t in ref.SECTOR_MAP:
            continue
        if t in ref.FUND_SPEC:
            found[t] = ref.FUND_SPEC[t]
            continue
        if t not in _cache:
            _cache[t] = fetch(t)
        if _cache[t]:
            ref.FUND_SPEC[t] = _cache[t]
            found[t] = _cache[t]
    return found


def apply(entries):
    for t, entry in entries.items():
        ref.FUND_SPEC.setdefault(t, entry)


def describe(ticker, entry):
    parts = [ticker]
    if entry.get("name"):
        parts.append(f" — {entry['name']}")
    if entry.get("category"):
        parts.append(f", {entry['category']}")
    breadth = entry.get("br", 1)
    if breadth > 1:
        parts.append(f" (counted as about {breadth} separate companies)")
    return "".join(parts)
