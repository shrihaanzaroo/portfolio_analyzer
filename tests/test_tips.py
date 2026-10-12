import re

import numpy as np
import pandas as pd
import pytest

import engine
import history
import same_direction
import scorecard
import tips

PORTFOLIOS = [
    {"AAPL": 0.2, "MSFT": 0.2, "NVDA": 0.15, "GOOGL": 0.15, "META": 0.15, "AMD": 0.15},
    {"JPM": 0.3, "BAC": 0.3, "WFC": 0.2, "C": 0.2},
    {"SPY": 0.4, "BND": 0.2, "GLD": 0.1, "JPM": 0.1, "XOM": 0.1, "PG": 0.1},
    {"AAPL": 0.5, "BND": 0.5},
    {"SPY": 0.4, "VTI": 0.3, "QQQ": 0.3},
    {"AAPL": 0.7, "MSFT": 0.3},
]
# words that would tell the reader what to do (the Check-Up describes, it doesn't advise)
COMMANDS = re.compile(
    r"(^|[.!?]\s+)(Trim|Keep|Sell|Buy|Add|Consider|Move|Swap|Reduce|Put)\b"
)


def all_texts(advice):
    texts = [d["text"] for d in advice["dimensions"]] + [
        d["short"] for d in advice["dimensions"]
    ]
    texts += [t[k] for t in advice["tips"] for k in ("title", "why", "action")]
    return " | ".join(texts)


@pytest.mark.parametrize("weights", PORTFOLIOS)
def test_no_correlation_written_as_a_percent(weights, returns3):
    """Correlation is never described as "moves match X%" or similar."""
    blob = all_texts(tips.build_tips(weights, returns3, 1.0))
    for old in ("moves match", "in sync", "match the others"):
        assert old not in blob
    assert not re.search(r"match about \d", blob)


@pytest.mark.parametrize("weights", PORTFOLIOS)
def test_of_the_time_only_describes_same_direction_days(weights, returns3):
    """Any "of the time" sentence is about days moving the same way, not a correlation."""
    blob = all_texts(tips.build_tips(weights, returns3, 1.0))
    for sentence in re.findall(r"[^.]*of the time[^.]*", blob):
        assert (
            "moved in the same direction" in sentence
            or "would match about half the time" in sentence
        )


@pytest.mark.parametrize("weights", PORTFOLIOS)
def test_duplicates_ring_shows_the_measured_same_direction_share(weights, returns3):
    """The Duplicates ring's text quotes the share measured by same_direction.portfolio_share."""
    advice = tips.build_tips(weights, returns3, 1.0)
    dup = next(d for d in advice["dimensions"] if d["label"] == "Duplicates")
    share = same_direction.portfolio_share(weights, returns3)
    if share is not None:
        assert (
            f"moved in the same direction about {share * 100:.0f}% of the time"
            in dup["text"]
        )


@pytest.mark.parametrize("invested", [1.0, 0.6])
@pytest.mark.parametrize("weights", PORTFOLIOS)
def test_actions_never_give_orders(weights, invested, returns3):
    """No tip's action starts a sentence with a command like "Trim" or "Keep it", or says "you should"."""
    for tip in tips.build_tips(weights, returns3, invested)["tips"]:
        assert not COMMANDS.search(tip["action"]), tip["action"]
        assert "you should" not in tip["action"].lower()
        assert "Keep it" not in tip["action"]


@pytest.fixture
def safety_net_market(market):
    """Adds SPEC (bumpy, unrelated to stocks) and BONDY (calm, rises a little when stocks fall)."""
    p, mkt, rng, n = market.prices, market.mkt, market.rng, market.n
    p["SPEC"] = 100 * np.cumprod(1 + 0.1 * mkt + rng.normal(0, 0.04, n))
    p["BONDY"] = 100 * np.cumprod(1 - 0.08 * mkt + rng.normal(0.0001, 0.003, n))
    return history.window(engine.compute_returns(p), 3)


BASE = {"AAPL": 0.3, "MSFT": 0.3, "NVDA": 0.2}


def test_bumpy_unrelated_stock_is_not_called_a_safety_net(safety_net_market):
    """A volatile stock that just moves independently is not labelled a safety net."""
    r3 = safety_net_market
    weights = {**BASE, "SPEC": 0.2}
    assert engine.hedge_detection(weights, r3, 0.30)[0][
        "SPEC"
    ]  # low correlation on its own isn't enough
    titles = [t["title"] for t in tips.build_tips(weights, r3, 1.0)["tips"]]
    assert "SPEC acts as a safety net" not in titles
    assert "Nothing here tends to hold up when the rest falls" in titles


def test_calm_holding_that_holds_up_is_a_safety_net(safety_net_market):
    """A calm holding that held up on the worst days is labelled a safety net."""
    titles = [
        t["title"]
        for t in tips.build_tips({**BASE, "BONDY": 0.2}, safety_net_market, 1.0)["tips"]
    ]
    assert "BONDY acts as a safety net" in titles


@pytest.mark.parametrize(
    "n, bets, expected",
    [
        (2, 1.0, None),  # fewer than three holdings: nothing to say
        (6, 3.0, None),  # at least half as many bets as holdings
        (6, 1.9, "high"),  # clearly overlapping
        (10, 2.5, "medium"),  # an ordinary mix of stocks
        (10, 3.5, None),  # more than an ordinary mix of stocks
    ],
)
def test_few_bets_level(n, bets, expected):
    """The real-bets note level follows the cut-offs (high under 2, medium under 3, only when under half the holdings)."""
    assert tips.few_bets_level(n, bets) == expected


# ---- real-bets note on a one-factor model: each stock = beta * market + its own noise ----
DAYS = 252 * 3 + 5
MKT_SD = 0.0105
TECH = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD"]
TEN = ["JPM", "XOM", "JNJ", "PG", "NEE", "HD", "CAT", "LIN", "O", "NFLX"]
# ten more are drawn too, so the random numbers match the study the cut-offs came from
TWENTY = TEN + ["BAC", "CVX", "PFE", "KO", "DUK", "MCD", "DE", "SHW", "PLD", "DIS"]


def one_factor_universe(seed, tech_rho=0.6, div_rho=0.27):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-10-09", periods=DAYS)
    mkt = rng.normal(0.0004, MKT_SD, DAYS)

    def stock(rho, annual_vol):
        sd = annual_vol / np.sqrt(252)
        return np.sqrt(rho) * sd / MKT_SD * mkt + rng.normal(
            0, sd * np.sqrt(1 - rho), DAYS
        )

    cols = {t: stock(tech_rho, rng.uniform(0.30, 0.35)) for t in TECH}
    cols.update({t: stock(div_rho, rng.uniform(0.25, 0.30)) for t in TWENTY})
    cols["SPY"] = mkt + rng.normal(0, 0.0005, DAYS)
    cols["VTI"] = 1.02 * mkt + rng.normal(0, 0.0012, DAYS)
    cols["QQQ"] = 1.2 * mkt + rng.normal(0, 0.004, DAYS)
    cols["BND"] = 0.02 * mkt + rng.normal(0.0001, 0.0033, DAYS)
    cols["GLD"] = 0.05 * mkt + rng.normal(0.0002, 0.009, DAYS)
    return pd.DataFrame(cols, index=idx)


REAL_BETS_CASES = {
    "six tech stocks": (
        {
            "AAPL": 0.2,
            "MSFT": 0.2,
            "NVDA": 0.15,
            "GOOGL": 0.15,
            "META": 0.15,
            "AMD": 0.15,
        },
        {"high"},
    ),
    "ten stocks, ten industries": ({t: 0.1 for t in TEN}, {"medium", None}),
    "S&P fund + bonds + gold + 3 stocks": (
        {"SPY": 0.4, "BND": 0.2, "GLD": 0.1, "JPM": 0.1, "XOM": 0.1, "PG": 0.1},
        {None},
    ),
    "three overlapping stock funds": ({"SPY": 0.4, "VTI": 0.3, "QQQ": 0.3}, {"high"}),
}


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("name", REAL_BETS_CASES)
def test_real_bets_note_level(name, seed):
    """The real-bets note appears at the expected level (or not at all) for typical portfolios."""
    weights, allowed = REAL_BETS_CASES[name]
    rets = one_factor_universe(seed)
    level = tips.few_bets_level(len(weights), float(scorecard.real_bets(weights, rets)))
    assert level in allowed
    shown = [
        t["level"]
        for t in tips.build_tips(weights, rets, 1.0)["tips"]
        if "real bets" in t["title"]
    ]
    assert shown in ([level], [])
    if level == "high":
        assert shown == ["high"]


def test_medium_real_bets_note_is_calm():
    """An ordinary stock mix gets a "Worth knowing" note that doesn't say "only"."""
    rets = one_factor_universe(2, div_rho=0.3)
    advice = tips.build_tips({t: 0.1 for t in TEN}, rets, 1.0)
    note = next(t for t in advice["tips"] if "real bets" in t["title"])
    assert note["level"] == "medium"
    assert "only" not in note["title"]
