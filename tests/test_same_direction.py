import numpy as np
import pandas as pd

import same_direction


def two_random_series():
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0, 0.01, 5000)), pd.Series(rng.normal(0, 0.01, 5000))


def test_unrelated_series_match_about_half_the_time():
    """Two independent coin-flip series move the same way on roughly 50% of days."""
    a, b = two_random_series()
    assert abs(same_direction.same_direction_share(a, b) - 0.5) < 0.03


def test_a_series_always_matches_itself():
    """A series compared with itself moves the same way every day."""
    a, _ = two_random_series()
    assert same_direction.same_direction_share(a, a) == 1.0


def test_missing_days_are_skipped_and_flat_days_count_as_no_match():
    """NaN days are left out of the count; days with a zero return never count as the same direction."""
    a, _ = two_random_series()
    a2 = a.copy()
    a2.iloc[:10] = np.nan
    a2.iloc[10:20] = 0.0
    assert abs(same_direction.same_direction_share(a2, a) - 4980 / 4990) < 1e-12


def test_no_shared_days_gives_none():
    """When the two series never have data on the same day there is nothing to measure."""
    a = pd.Series([np.nan, 1.0])
    b = pd.Series([1.0, np.nan])
    assert same_direction.same_direction_share(a, b) is None
