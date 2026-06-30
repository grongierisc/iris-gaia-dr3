from __future__ import annotations

from src.python.gaia.parsing import (
    aggregate_source_flux,
    max_percentage_change,
    min_max,
    valid_flux_values,
)


def test_valid_flux_values_keeps_only_finite_numbers():
    values = list(valid_flux_values("[1, 2.5, NaN, Infinity, -inf, null, , -3]"))

    assert values == [1.0, 2.5, -3.0]


def test_valid_flux_values_ignores_blank_or_non_array_cells():
    assert list(valid_flux_values("")) == []
    assert list(valid_flux_values("null")) == []
    assert list(valid_flux_values("[]")) == []


def test_min_max_returns_none_pair_for_empty_values():
    assert min_max([]) == (None, None)


def test_aggregate_source_flux_computes_band_min_max():
    stats = aggregate_source_flux(
        source_id=42,
        bp_flux="[10.0, 5.5, 12.25]",
        rp_flux="[3.0, NaN, 9.0]",
    )

    assert stats.source_id == 42
    assert stats.bp_min_flux == 5.5
    assert stats.bp_max_flux == 12.25
    assert stats.rp_min_flux == 3.0
    assert stats.rp_max_flux == 9.0
    assert stats.has_flux


def test_aggregate_source_flux_marks_empty_bands():
    stats = aggregate_source_flux(source_id=7, bp_flux="[NaN]", rp_flux="")

    assert stats.bp_min_flux is None
    assert stats.bp_max_flux is None
    assert stats.rp_min_flux is None
    assert stats.rp_max_flux is None
    assert not stats.has_flux


def test_max_percentage_change_matches_sql_rules():
    assert max_percentage_change(10.0, 25.0, 5.0, 7.0) == 150.0
    assert max_percentage_change(None, None, 4.0, 10.0) == 150.0
    assert max_percentage_change(0.0, 10.0, None, None) is None
    assert max_percentage_change(None, None, None, None) is None
