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
# used only when Yahoo Finance can't be reached, so a common index fund is never mistaken for one stock
COMMON_FUNDS = {
    "FSKAX": ("Fidelity Total Market Index", "Total Market"), "VTSAX": ("Vanguard Total Stock Market Index", "Total Market"),
    "SWTSX": ("Schwab Total Stock Market Index", "Total Market"), "ITOT": ("iShares Core S&P Total U.S. Stock Market", "Total Market"),
    "SCHB": ("Schwab U.S. Broad Market", "Total Market"),
    "FXAIX": ("Fidelity 500 Index", "Large Blend"), "VFIAX": ("Vanguard 500 Index", "Large Blend"),
    "SWPPX": ("Schwab S&P 500 Index", "Large Blend"), "IVV": ("iShares Core S&P 500", "Large Blend"),
    "SCHX": ("Schwab U.S. Large-Cap", "Large Blend"),
    "QQQM": ("Invesco Nasdaq 100", "Large Growth"), "VUG": ("Vanguard Growth", "Large Growth"), "SCHG": ("Schwab U.S. Large-Cap Growth", "Large Growth"),
    "VTV": ("Vanguard Value", "Large Value"), "SCHD": ("Schwab U.S. Dividend Equity", "Large Value"),
    "VXUS": ("Vanguard Total International Stock", "Foreign Large Blend"), "VTIAX": ("Vanguard Total International Stock Index", "Foreign Large Blend"),
    "FTIHX": ("Fidelity Total International Index", "Foreign Large Blend"), "IXUS": ("iShares Core MSCI Total International", "Foreign Large Blend"),
    "VEA": ("Vanguard Developed Markets", "Foreign Large Blend"), "IEMG": ("iShares Core MSCI Emerging Markets", "Diversified Emerging Mkts"),
    "VT": ("Vanguard Total World Stock", "World Stock"),
    "FXNAX": ("Fidelity U.S. Bond Index", "Intermediate Core Bond"), "VBTLX": ("Vanguard Total Bond Market Index", "Intermediate Core Bond"),
    "BNDX": ("Vanguard Total International Bond", "Global Bond"), "SCHZ": ("Schwab U.S. Aggregate Bond", "Intermediate Core Bond"),
    "IAU": ("iShares Gold Trust", "Commodities Focused Gold"),
}
STOCK_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,5}$")
PLAIN_COUNTRY = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,39}$")


def _key(text):
    return re.sub(r"[^a-z]", "", str(text or "").lower())


# Yahoo's stock sectors ("Financial Services", sectorKey "financial-services") and the app's own names, both mapped to the app's names
STOCK_SECTORS = {**{_key(k): v for k, v in SECTOR_NAMES.items()}, **{_key(s): s for s in ref.EQUITY_SECTORS}}

_cache = {}
# stocks whose sector/country were added to ref.SECTOR_MAP / regions.COUNTRY_OVERRIDES while the app runs, and where that came from
STOCK_INFO = {}


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


def from_table(ticker):
    name, category = COMMON_FUNDS[ticker]
    cat = category.lower()
    if "bond" in cat:
        entry = {"sector": "Bonds", "br": breadth_for(category), "assets": {"Stocks": 0, "Bonds": 100, "Cash": 0}}
    elif "gold" in cat:
        entry = {"sector": "Gold", "br": 1}
    else:
        entry = {"sector": "Index", "br": breadth_for(category), "assets": {"Stocks": 100, "Bonds": 0, "Cash": 0}}
        if "foreign" in cat or "emerging" in cat:
            entry["mix"] = dict(ref.FUND_SPEC["VWO" if "emerging" in cat else "EFA"]["mix"])
        else:
            entry["mix"] = dict(ref.SP500)
            if "growth" not in cat and "value" not in cat and "world" not in cat:
                entry["top"] = dict(ref.VTI_TOP if "total" in cat else ref.SP_TOP)
    entry.update({"name": name, "category": category})
    countries = countries_for(category)
    if countries:
        entry["countries"] = countries
    return entry


def stock_sector(info):
    for raw in (info.get("sector"), info.get("sectorKey")):
        if raw and _key(raw) in STOCK_SECTORS:
            return STOCK_SECTORS[_key(raw)]
    return None


def plain_country(value):
    country = str(value or "").strip()
    return country if PLAIN_COUNTRY.match(country) and len(country.split()) <= 4 else None


def fetch(ticker):
    """A fund's composition; {"kind": "stock", "sector", "country"} for a stock (either may be None);
    False if Yahoo says it is something else; None if Yahoo could not be reached."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception:
        return None
    if not info.get("quoteType"):
        return None
    if info.get("quoteType") == "EQUITY":
        return {"kind": "stock", "sector": stock_sector(info), "country": plain_country(info.get("country"))}
    if info.get("quoteType") not in ("ETF", "MUTUALFUND"):
        return False

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
    """Looks up tickers the app doesn't know. Returns {"funds": {ticker: fund entry}, "stocks": {ticker: {"sector", "country"}}}."""
    found, stocks = {}, {}
    for t in tickers:
        if t in ref.SECTOR_MAP:
            continue
        if t in ref.FUND_SPEC:
            found[t] = ref.FUND_SPEC[t]
            continue
        if t not in _cache:
            entry = fetch(t)
            if entry is None:
                entry = from_table(t) if t in COMMON_FUNDS else None
            else:
                _cache[t] = entry
        else:
            entry = _cache[t]
        if entry and entry.get("kind") == "stock":
            stocks[t] = {"sector": entry["sector"], "country": entry["country"]}
        elif entry:
            ref.FUND_SPEC[t] = entry
            found[t] = entry
    apply_stocks(stocks)
    return {"funds": found, "stocks": stocks}


def apply(entries):
    for t, entry in entries.items():
        ref.FUND_SPEC.setdefault(t, entry)


def apply_stocks(stocks, source="yahoo"):
    """Records each stock's sector and country for the whole app. Never replaces a sector or country already known."""
    for t, item in stocks.items():
        if t in ref.FUND_SPEC or t in ref.SECTOR_MAP:
            continue
        sector = item.get("sector")
        country = plain_country(item.get("country"))
        if sector not in ref.EQUITY_SECTORS:
            if source != "yahoo":
                continue
            sector = None
        if country:
            regions.COUNTRY_OVERRIDES.setdefault(t, country)
        if sector:
            STOCK_INFO.setdefault(t, {"sector": sector, "country": country, "source": source})
            ref.SECTOR_MAP.setdefault(t, sector)


def estimated_by(ticker):
    return STOCK_INFO.get(ticker, {}).get("source")


def unknown_sector(tickers):
    return [t for t in tickers if t not in ref.FUND_SPEC and t not in ref.SECTOR_MAP]


def describe(ticker, entry):
    parts = [ticker]
    if entry.get("name"):
        parts.append(f" — {entry['name']}")
    if entry.get("category"):
        parts.append(f", {entry['category']}")
    breadth = entry.get("br", 1)
    if breadth > 1:
        parts.append(f" (counted as about {breadth} separate holdings)")
    return "".join(parts)
