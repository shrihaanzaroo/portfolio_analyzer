import pandas as pd
import pytest

import engine
import funds
import llm_csv
import reference_data as ref
import regions
import tips

FIVE = ["WM", "MMM", "KR", "TJX", "ZTS"]
STOCK_INFO = {
    "WM": {"quoteType": "EQUITY", "sector": "Industrials", "country": "United States"},
    "MMM": {"quoteType": "EQUITY", "sector": "Industrials", "country": "United States"},
    "KR": {
        "quoteType": "EQUITY",
        "sector": "Consumer Defensive",
        "country": "United States",
    },
    "TJX": {
        "quoteType": "EQUITY",
        "sector": "Consumer Cyclical",
        "country": "United States",
    },
    "ZTS": {"quoteType": "EQUITY", "sector": "Healthcare", "country": "United States"},
    "TSM": {"quoteType": "EQUITY", "sectorKey": "technology", "country": "Taiwan"},
    "ASML": {"quoteType": "EQUITY", "sector": "Technology", "country": "Netherlands"},
    "JPM": {
        "quoteType": "EQUITY",
        "sector": "Healthcare",
        "country": "Mars",
    },  # already in the built-in table
    "NOSEC": {"quoteType": "EQUITY", "country": "Canada"},
    "WEIRD": {
        "quoteType": "EQUITY",
        "sector": "Crypto Stuff",
        "country": "<script>alert(1)</script>",
    },
    "FNDX": {"quoteType": "ETF", "longName": "Fake Fund", "category": "Large Blend"},
    "BTC-USD": {"quoteType": "CRYPTOCURRENCY"},
}
ALL = FIVE + ["TSM", "ASML", "JPM", "NOSEC", "WEIRD", "FNDX", "BTC-USD"]
# saved before conftest.py swaps in a fake for each test
REAL_CLASSIFY = llm_csv.classify_stocks


@pytest.fixture
def yahoo_knows(yahoo):
    """Yahoo answers for the tickers in STOCK_INFO, and FNDX looks like a 30% tech / 70% health fund."""
    yahoo.info.update({t: dict(v) for t, v in STOCK_INFO.items()})
    yahoo.fund_data = {
        "fund_overview": {"categoryName": "Large Blend"},
        "asset_classes": {
            "stockPosition": 0.99,
            "bondPosition": 0,
            "cashPosition": 0.01,
        },
        "sector_weightings": {"technology": 0.3, "healthcare": 0.7},
        "top_holdings": pd.DataFrame({"Holding Percent": [0.05]}, index=["AAPL"]),
    }
    return yahoo


def test_register_sorts_funds_from_stocks(yahoo_knows):
    """Funds and stocks come back separately; built-in stocks and crypto are not looked up as stocks."""
    out = funds.register(ALL)
    assert list(out["funds"]) == ["FNDX"]
    assert "JPM" not in out["stocks"] and "BTC-USD" not in out["stocks"]
    assert ref.FUND_SPEC["FNDX"]["mix"] == {"Technology": 30.0, "Health Care": 70.0}


def test_yahoo_sector_names_become_the_apps_names(yahoo_knows):
    """Yahoo's sector names ("Consumer Defensive", sectorKey "technology") map to the app's names."""
    funds.register(ALL)
    assert {t: ref.spec_lookup(t)["sector"] for t in FIVE} == {
        "WM": "Industrials",
        "MMM": "Industrials",
        "KR": "Consumer Staples",
        "TJX": "Consumer Discretionary",
        "ZTS": "Health Care",
    }
    assert ref.spec_lookup("TSM")["sector"] == "Technology"
    assert (
        engine.sector_concentration({t: 0.2 for t in FIVE})["sectors"][0]["sector"]
        == "Industrials"
    )


def test_yahoo_country_is_used(yahoo_knows):
    """A stock's home country from Yahoo shows up in the country mix."""
    funds.register(ALL)
    assert {"country": "Taiwan", "pct": 50.0} in regions.country_mix(
        {"TSM": 0.5, "AAPL": 0.5}
    )
    assert regions.country_lookup("ASML") == {"Netherlands": 100}


def test_built_in_entries_are_never_overwritten(yahoo_knows):
    """Yahoo can't change a sector or country the app already knew (JPM stays Financials)."""
    sectors_before, countries_before = (
        dict(ref.SECTOR_MAP),
        dict(regions.COUNTRY_OVERRIDES),
    )
    funds.register(ALL)
    assert (
        ref.SECTOR_MAP["JPM"] == "Financials" and "JPM" not in regions.COUNTRY_OVERRIDES
    )
    assert all(ref.SECTOR_MAP[k] == v for k, v in sectors_before.items())
    assert all(regions.COUNTRY_OVERRIDES[k] == v for k, v in countries_before.items())


def test_bad_sector_or_country_is_ignored(yahoo_knows):
    """An unknown sector is dropped and a country that isn't plain text is never stored."""
    funds.register(ALL)
    assert (
        "NOSEC" not in ref.SECTOR_MAP and regions.COUNTRY_OVERRIDES["NOSEC"] == "Canada"
    )
    assert "WEIRD" not in ref.SECTOR_MAP and "WEIRD" not in regions.COUNTRY_OVERRIDES
    assert funds.unknown_sector(FIVE + ["NOSEC", "WEIRD", "FNDX", "TSM"]) == [
        "NOSEC",
        "WEIRD",
    ]
    assert funds.estimated_by("WM") == "yahoo"


def test_sector_examples_in_tips_do_not_change(yahoo_knows):
    """Looked-up stocks never appear as the example tickers the tips suggest."""
    before = tips.sector_examples()
    funds.register(ALL)
    funds.apply_stocks(
        {"NOSEC": {"sector": "Materials", "country": "Chile"}}, source="ai"
    )
    assert tips.sector_examples() == before


def test_stocks_without_a_sector_are_asked_again(yahoo_knows):
    """Funds and stocks with a sector are remembered; stocks Yahoo gave no sector for are looked up again."""
    funds.register(ALL)
    yahoo_knows.calls.clear()
    funds.register(["NOSEC", "WEIRD", "FNDX", "WM"])
    assert yahoo_knows.calls == ["NOSEC", "WEIRD"]
    assert "FNDX" in funds._cache and "NOSEC" not in funds._cache


def test_unreachable_yahoo_is_retried_later(yahoo):
    """When Yahoo can't be reached nothing is remembered, so the next lookup tries again."""
    yahoo.down.add("XYZ")
    assert funds.register(["XYZ"]) == {"funds": {}, "stocks": {}}
    assert "XYZ" not in funds._cache
    yahoo.down.discard("XYZ")
    yahoo.info["XYZ"] = {"quoteType": "EQUITY", "sector": "Energy", "country": "Norway"}
    funds.register(["XYZ"])
    assert yahoo.calls == ["XYZ", "XYZ"]
    assert ref.SECTOR_MAP["XYZ"] == "Energy"


def test_common_fund_falls_back_to_the_table_when_offline(yahoo):
    """A well-known index fund is still treated as a fund when Yahoo is down (but not remembered)."""
    yahoo.down.add("VXUS")
    assert list(funds.register(["VXUS"])["funds"]) == ["VXUS"]
    assert "VXUS" not in funds._cache


def test_ai_answers_fill_gaps_but_never_overwrite(yahoo_knows):
    """AI sectors only fill unknown stocks, never replace Yahoo's, and invalid sectors are skipped."""
    funds.register(ALL)
    funds.apply_stocks(
        {
            "NOSEC": {"sector": "Materials", "country": "Chile"},
            "WM": {"sector": "Energy", "country": "France"},
            "BAD": {"sector": "Crypto", "country": "Peru"},
        },
        source="ai",
    )
    assert (
        ref.SECTOR_MAP["NOSEC"] == "Materials"
        and regions.COUNTRY_OVERRIDES["NOSEC"] == "Canada"
    )
    assert (
        ref.SECTOR_MAP["WM"] == "Industrials"
        and regions.COUNTRY_OVERRIDES["WM"] == "United States"
    )
    assert "BAD" not in ref.SECTOR_MAP and "BAD" not in regions.COUNTRY_OVERRIDES
    assert funds.estimated_by("NOSEC") == "ai" and funds.estimated_by("WM") == "yahoo"


def test_classify_stocks_keeps_only_valid_answers(monkeypatch):
    """The AI's reply is cleaned: unknown tickers, bad sectors and odd countries are dropped."""
    reply = {
        "stocks": [
            {"ticker": "aaa", "sector": "materials", "country": "Chile"},
            {"ticker": "BBB", "sector": "Crypto", "country": "Peru"},
            {
                "ticker": "CCC",
                "sector": "Energy",
                "country": "The Republic of Somewhere Very Long Name",
            },
            {"ticker": "DDD", "sector": "Utilities", "country": "<b>x</b>"},
            {"ticker": "ZZZ", "sector": "Energy", "country": "Norway"},
            {"ticker": "EEE", "sector": None, "country": "Japan"},
            "junk",
        ]
    }
    monkeypatch.setattr(llm_csv, "_ask", lambda messages, cfg: (reply, "model"))
    got = REAL_CLASSIFY(["AAA", "BBB", "CCC", "DDD", "EEE"])
    assert got == {
        "AAA": {"sector": "Materials", "country": "Chile"},
        "CCC": {"sector": "Energy", "country": None},
        "DDD": {"sector": "Utilities", "country": None},
    }


# ---- AI answers expire ----


@pytest.fixture
def ai_filled(yahoo):
    """WM and KR come from Yahoo; AIX, NOSEC2 and FRESH get sectors from the AI."""
    yahoo.info.update(
        {
            "WM": STOCK_INFO["WM"],
            "KR": STOCK_INFO["KR"],
            "NOSEC2": {"quoteType": "EQUITY", "country": "Canada"},
            "AIX": {"quoteType": "EQUITY"},
            "FRESH": {"quoteType": "EQUITY"},
        }
    )
    funds.register(["WM", "KR", "NOSEC2", "AIX", "FRESH"])
    funds.apply_stocks(
        {
            "AIX": {"sector": "Materials", "country": "Chile"},
            "NOSEC2": {"sector": "Energy", "country": "Peru"},
            "FRESH": {"sector": "Utilities", "country": "Spain"},
            "WM": {"sector": "Energy", "country": "France"},
            "JPM": {"sector": "Energy", "country": "France"},
        },
        source="ai",
    )
    return yahoo


def make_old(*tickers):
    for t in tickers:
        funds.STOCK_INFO[t]["at"] -= 86401


def test_ai_remembers_what_it_added(ai_filled):
    """The AI entry records which of sector/country it inserted itself."""
    assert funds.STOCK_INFO["AIX"]["added"] == ["sector", "country"]
    assert funds.STOCK_INFO["NOSEC2"]["added"] == [
        "sector"
    ]  # Yahoo had already given the country
    assert (
        ref.SECTOR_MAP["WM"] == "Industrials" and ref.SECTOR_MAP["JPM"] == "Financials"
    )


def test_old_ai_answers_expire(ai_filled):
    """After a day, AI sectors and countries are removed; Yahoo's country stays."""
    make_old("AIX", "NOSEC2")
    funds.expire_ai()
    assert (
        "AIX" not in ref.SECTOR_MAP
        and "AIX" not in regions.COUNTRY_OVERRIDES
        and "AIX" not in funds.STOCK_INFO
    )
    assert (
        "NOSEC2" not in ref.SECTOR_MAP
        and regions.COUNTRY_OVERRIDES["NOSEC2"] == "Canada"
    )
    assert funds.unknown_sector(["AIX", "NOSEC2"]) == ["AIX", "NOSEC2"]


def test_fresh_ai_answers_and_yahoo_answers_stay(ai_filled):
    """Expiry leaves recent AI answers, Yahoo answers and built-in sectors alone."""
    built_in = {t: ref.SECTOR_MAP[t] for t in ["JPM", "AAPL", "MSFT"]}
    make_old("AIX", "NOSEC2")
    funds.expire_ai()
    assert (
        ref.SECTOR_MAP["FRESH"] == "Utilities" and funds.estimated_by("FRESH") == "ai"
    )
    assert ref.SECTOR_MAP["WM"] == "Industrials" and funds.estimated_by("WM") == "yahoo"
    assert {t: ref.SECTOR_MAP[t] for t in built_in} == built_in


# ---- Yahoo replaces AI ----


@pytest.fixture
def late_yahoo(yahoo):
    """LATE, LATE2, LATE3 first get AI sectors; then Yahoo learns about them."""
    for t in ["LATE", "LATE2", "LATE3"]:
        yahoo.info[t] = {"quoteType": "EQUITY"}
    yahoo.info["WM"] = STOCK_INFO["WM"]
    funds.register(["LATE", "LATE2", "LATE3", "WM"])
    funds.apply_stocks(
        {
            t: {"sector": "Materials", "country": "Chile"}
            for t in ["LATE", "LATE2", "LATE3"]
        },
        source="ai",
    )
    yahoo.info["LATE"] = {
        "quoteType": "EQUITY",
        "sector": "Energy",
        "country": "Norway",
    }  # both
    yahoo.info["LATE2"] = {"quoteType": "EQUITY", "sector": "Technology"}  # sector only
    yahoo.info["LATE3"] = {"quoteType": "EQUITY", "country": "Mexico"}  # country only
    yahoo.calls.clear()
    funds.register(["LATE", "LATE2", "LATE3", "WM"])
    return yahoo


def test_ai_estimated_stocks_are_asked_again(late_yahoo):
    """Stocks with only an AI sector are looked up on Yahoo again (WM's Yahoo answer is remembered, so it isn't)."""
    assert late_yahoo.calls == ["LATE", "LATE2", "LATE3"]


def test_yahoo_sector_and_country_replace_the_ai(late_yahoo):
    """When Yahoo has both, its answer replaces the AI's and is remembered."""
    assert (
        ref.SECTOR_MAP["LATE"] == "Energy"
        and regions.COUNTRY_OVERRIDES["LATE"] == "Norway"
    )
    assert funds.estimated_by("LATE") == "yahoo" and "LATE" in funds._cache


def test_yahoo_sector_drops_the_ai_country(late_yahoo):
    """When Yahoo has a sector but no country, the AI's country is dropped."""
    assert (
        ref.SECTOR_MAP["LATE2"] == "Technology"
        and "LATE2" not in regions.COUNTRY_OVERRIDES
    )
    assert funds.estimated_by("LATE2") == "yahoo"


def test_yahoo_country_only_keeps_the_ai_sector(late_yahoo):
    """When Yahoo has only a country, it replaces the AI's country and the AI sector stays (still marked AI)."""
    assert (
        ref.SECTOR_MAP["LATE3"] == "Materials"
        and regions.COUNTRY_OVERRIDES["LATE3"] == "Mexico"
    )
    assert (
        funds.STOCK_INFO["LATE3"]["added"] == ["sector"] and "LATE3" not in funds._cache
    )


def test_yahoo_answers_never_expire_or_get_taken_back(late_yahoo):
    """The AI can't replace a Yahoo answer, and expiry only removes the AI's own sector."""
    funds.apply_stocks(
        {"LATE": {"sector": "Materials", "country": "Chile"}}, source="ai"
    )
    funds.STOCK_INFO["LATE3"]["at"] -= 86401
    funds.expire_ai(max_age=86400)
    assert (
        ref.SECTOR_MAP["LATE"] == "Energy" and ref.SECTOR_MAP["LATE2"] == "Technology"
    )
    assert (
        "LATE3" not in ref.SECTOR_MAP and regions.COUNTRY_OVERRIDES["LATE3"] == "Mexico"
    )


# ---- currency ----


def test_currency_is_captured_from_yahoo(yahoo):
    """A stock's quote currency is remembered; unknown or built-in tickers count as US dollars."""
    yahoo.info["7203.T"] = {
        "quoteType": "EQUITY",
        "sector": "Consumer Cyclical",
        "country": "Japan",
        "currency": "JPY",
    }
    funds.register(["7203.T", "AAPL"])
    assert funds.currency_of("7203.T") == "JPY"
    assert funds.currency_of("AAPL") == "USD"
    assert funds.currency_of("NEVER-SEEN") == "USD"


def test_fund_currency_is_captured(yahoo):
    """A fund's currency from Yahoo is remembered too."""
    yahoo.info["EUFND"] = {
        "quoteType": "ETF",
        "longName": "Euro Fund",
        "category": "Europe Stock",
        "currency": "EUR",
    }
    funds.register(["EUFND"])
    assert funds.currency_of("EUFND") == "EUR"
