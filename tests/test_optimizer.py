import pytest

import engine
import funds
import optimizer
import reference_data as ref
import regions
import report
import scorecard

SECTOR_FUNDS = {
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLP": "Consumer Staples",
    "XLF": "Financials",
    "XLU": "Utilities",
}
TECH_HOLDINGS = {"AAPL": 22, "MSFT": 20, "NVDA": 18, "GOOGL": 14, "META": 14, "AMD": 12}


@pytest.mark.parametrize("ticker", SECTOR_FUNDS)
def test_sector_funds_have_their_industry_without_yahoo(ticker):
    """Each industry fund the scenarios try is known offline, so it never counts as "Other"."""
    sector = SECTOR_FUNDS[ticker]
    assert ticker in optimizer.CANDIDATES
    assert ref.spec_lookup(ticker)["sector"] == sector
    assert engine.sector_concentration({ticker: 1.0})["sectors"][0]["sector"] == sector
    assert regions.country_lookup(ticker) == {"United States": 100}
    assert regions.asset_mix({ticker: 1.0})[0]["asset"] == "Stocks"
    assert scorecard.is_fund(ticker)


def test_single_stocks_are_no_longer_candidates():
    """The old single-stock candidates were replaced by industry funds."""
    for old in ("JNJ", "XOM", "PG", "JPM", "NEE"):
        assert old not in optimizer.CANDIDATES


def test_sector_funds_register_without_asking_yahoo(yahoo):
    """Registering an industry fund uses the built-in entry; Yahoo isn't called."""
    assert list(funds.register(["XLV", "XLF"])["funds"]) == ["XLV", "XLF"]
    assert yahoo.calls == []


def test_suggest_swaps_finds_swaps_for_a_tech_heavy_mix(prices, returns3):
    """A six-tech-stock portfolio gets at least one what-if swap."""
    swaps = optimizer.suggest_swaps(TECH_HOLDINGS, prices, returns3, 0.0, k=3)
    assert 1 <= len(swaps) <= 3
    for swap in swaps:
        assert swap["buy_ticker"] in optimizer.CANDIDATES
        assert swap["sell_ticker"] in TECH_HOLDINGS


def test_every_candidate_is_tried(prices, returns3, monkeypatch):
    """suggest_swaps tries buying every candidate fund."""
    tried = set()
    real_metrics = optimizer.metrics

    def spy_metrics(holdings, price_of, returns, invested_share):
        tried.update(holdings)
        return real_metrics(holdings, price_of, returns, invested_share)

    monkeypatch.setattr(optimizer, "metrics", spy_metrics)
    optimizer.suggest_swaps(TECH_HOLDINGS, prices, returns3, 0.0, k=3)
    assert set(optimizer.CANDIDATES) <= tried


def test_report_explains_the_fixed_candidate_list():
    """The downloadable report describes tips neutrally and says only a short fixed list of funds is tried."""
    html = report.build_html(
        {
            "date": "d",
            "basis": "b",
            "grade": "C",
            "verdict": "v",
            "holdings": 1,
            "true_bets": 1.0,
            "biggest": "X",
            "biggest_pct": 1,
            "dimensions": [],
            "tips": [{"level": "good", "title": "t", "why": "w", "action": "a"}],
            "weights": [],
            "assets": [],
            "countries": [],
            "sectors": [],
            "funds": [],
            "performance": [],
            "performance_range": "",
            "steady": "",
            "crashes": [],
            "scenarios": [],
            "method": [],
        }
    )
    assert "What usually changes this:" in html
    assert "What would help" not in html
    assert "Only a short fixed list of broad funds is tried" in html
