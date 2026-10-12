import pytest

import engine
import same_direction
import scorecard

TECH = {
    "AAPL": 0.2,
    "MSFT": 0.2,
    "NVDA": 0.15,
    "GOOGL": 0.15,
    "META": 0.15,
    "AMD": 0.15,
}

# name: (weights, share of money invested, expected letter, expected ring points in page order)
# Recorded from the app as it is now, on the made-up market in conftest.py. If one changes, the grading changed.
PORTFOLIOS = {
    "six tech": (TECH, 1.0, "C", [3, 0, 1, 2, 2, 4]),
    "six tech + 30% cash": (TECH, 0.7, "C", [3, 0, 1, 2, 2, 4]),
    "spy+bonds+gold+other": (
        {"SPY": 0.4, "BND": 0.2, "GLD": 0.1, "JPM": 0.1, "XOM": 0.1, "PG": 0.1},
        1.0,
        "B",
        [4, 4, 1, 4, 2, 3],
    ),
    "spy+bonds+gold+other+efa": (
        {
            "SPY": 0.35,
            "BND": 0.2,
            "GLD": 0.1,
            "JPM": 0.1,
            "XOM": 0.1,
            "PG": 0.05,
            "EFA": 0.1,
        },
        1.0,
        "B",
        [4, 4, 3, 4, 2, 2],
    ),
    "single stock": ({"AAPL": 1.0}, 1.0, "D", [0, 0, 1, 2, 2, 4]),
    "single VTI": ({"VTI": 1.0}, 1.0, "B", [4, 3, 1, 3, 1, 4]),
    "three funds": ({"SPY": 0.4, "VTI": 0.3, "QQQ": 0.3}, 1.0, "C", [4, 3, 1, 3, 1, 1]),
    "banks + cash": (
        {"JPM": 0.3, "BAC": 0.3, "WFC": 0.2, "C": 0.2},
        0.55,
        "C",
        [2, 0, 1, 3, 2, 4],
    ),
    "mixed old candidates": (
        {"AAPL": 0.3, "JNJ": 0.2, "XOM": 0.2, "NEE": 0.15, "BND": 0.15},
        0.9,
        "B",
        [3, 3, 1, 4, 2, 4],
    ),
    "bonds + gold only": ({"BND": 0.6, "GLD": 0.4}, 1.0, "B", [4, 4, 1, 4, 2, 4]),
    "five other industries": (
        {t: 0.2 for t in ["WM", "MMM", "KR", "TJX", "ZTS"]},
        1.0,
        "C",
        [3, 0, 1, 4, 2, 4],
    ),
    "spy + efa + vwo + bnd, 50% cash": (
        {"SPY": 0.4, "EFA": 0.2, "VWO": 0.1, "BND": 0.3},
        0.5,
        "B",
        [4, 4, 4, 4, 2, 3],
    ),
}

# (group, ring label, graded category) in the order the rings appear
RING_ORDER = [
    ("Spread out", "Companies", "Diversification"),
    ("Spread out", "Industries", "Sector balance"),
    ("Spread out", "Countries", "Countries"),
    ("How it behaves", "Steadiness", "Volatility"),
    ("How it behaves", "Consistency", "Consistency"),
    ("How it behaves", "Duplicates", "No duplicate bets"),
]
LEVEL = {4: "good", 3: "good", 2: "medium", 1: "high", 0: "high"}


@pytest.mark.parametrize("name", PORTFOLIOS)
def test_grade_letter_and_ring_points_stay_the_same(name, returns3):
    """Each sample portfolio keeps the letter and ring points recorded for it."""
    weights, invested, letter, points = PORTFOLIOS[name]
    card = scorecard.grade(weights, returns3, invested)
    assert card["overall"] == letter
    assert [d["score"] for d in card["dimensions"]] == points


@pytest.mark.parametrize("name", PORTFOLIOS)
def test_rings_are_exactly_the_graded_categories(name, returns3):
    """There is one ring per graded category, in page order, with the same points and colour level."""
    weights, invested, _, _ = PORTFOLIOS[name]
    card = scorecard.grade(weights, returns3, invested)
    dims = card["dimensions"]
    assert [(d["group"], d["label"], d["category"]) for d in dims] == RING_ORDER
    assert {d["category"]: d["score"] for d in dims} == card["points"]
    assert all(d["level"] == LEVEL[d["score"]] for d in dims)


@pytest.mark.parametrize("name", PORTFOLIOS)
def test_score_is_the_average_of_the_rings(name, returns3):
    """The 0-4 score is the plain average of the category points."""
    weights, invested, _, _ = PORTFOLIOS[name]
    card = scorecard.grade(weights, returns3, invested)
    assert (
        abs(sum(card["points"].values()) / len(card["points"]) - card["score"]) < 1e-9
    )


def test_five_rings_when_the_sp500_is_missing(returns3):
    """Without S&P 500 prices the Steadiness ring is left out and the letter is unchanged."""
    no_spy = returns3.copy()
    no_spy["SPY"] = float("nan")
    card = scorecard.grade(TECH, no_spy, 1.0)
    assert card["overall"] == "C"
    assert "Volatility" not in card["points"]
    assert [d["label"] for d in card["dimensions"]] == [
        "Companies",
        "Industries",
        "Countries",
        "Consistency",
        "Duplicates",
    ]


def test_no_independence_ring(returns3):
    """The old "Independence" ring is gone (it was folded into Duplicates)."""
    card = scorecard.grade(TECH, returns3, 1.0)
    assert not any(d["label"] == "Independence" for d in card["dimensions"])


@pytest.mark.parametrize(
    "weights", [TECH, {"SPY": 0.4, "VTI": 0.3, "QQQ": 0.3}, {"AAPL": 1.0}]
)
def test_ring_short_texts_match_the_measured_numbers(weights, returns3):
    """Duplicates, Consistency and Steadiness rings show numbers worked out from the same returns."""
    card = scorecard.grade(weights, returns3, 1.0)
    rings = {d["label"]: d for d in card["dimensions"]}

    pairs = len(engine.redundant_pairs(weights, returns3, 0.75))
    expected = (
        "No near-duplicates"
        if pairs == 0
        else f"{pairs} near-duplicate pair{'' if pairs == 1 else 's'}"
    )
    assert rings["Duplicates"]["short"] == expected

    share = same_direction.portfolio_share(weights, returns3)
    assert (
        share is None
        or f"about {share * 100:.0f}% of the time" in rings["Duplicates"]["text"]
    )

    win = engine.rolling_win_rate(weights, returns3[list(weights)])["win_rate"]
    assert rings["Consistency"]["short"] == f"Up in {win * 100:.0f}% of months"

    ratio = engine.portfolio_vol(weights, returns3[list(weights)]) / engine.ann_vol(
        returns3["SPY"]
    )
    assert rings["Steadiness"]["short"] == f"{ratio:.1f}× the market's swings"


def test_one_company_never_scores_above_d(returns3):
    """A single stock is capped at D however calm it has been."""
    assert scorecard.grade({"JNJ": 1.0}, returns3, 1.0)["overall"] in ("D", "F")
