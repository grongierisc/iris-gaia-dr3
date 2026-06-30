from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SourceFluxStats:
    source_id: int
    bp_min_flux: Optional[float]
    bp_max_flux: Optional[float]
    rp_min_flux: Optional[float]
    rp_max_flux: Optional[float]

    @property
    def has_flux(self) -> bool:
        return self.bp_min_flux is not None or self.rp_min_flux is not None


def valid_flux_values(array_text: str) -> Iterator[float]:
    """Yield finite numeric values from a Gaia ECSV array cell."""

    text = (array_text or "").strip()
    if not (text.startswith("[") and text.endswith("]")):
        return

    for raw_value in text[1:-1].split(","):
        value_text = raw_value.strip()
        if not value_text:
            continue
        try:
            value = float(value_text)
        except ValueError:
            continue
        if math.isfinite(value):
            yield value


def flux_rows(source_id: int, band: str, values: Iterable[float]) -> Iterator[tuple[int, str, float]]:
    for value in values:
        yield source_id, band, value


def min_max(values: Iterable[float]) -> tuple[Optional[float], Optional[float]]:
    iterator = iter(values)
    try:
        first = next(iterator)
    except StopIteration:
        return None, None

    min_value = first
    max_value = first
    for value in iterator:
        if value < min_value:
            min_value = value
        if value > max_value:
            max_value = value
    return min_value, max_value


def aggregate_source_flux(source_id: int, bp_flux: str, rp_flux: str) -> SourceFluxStats:
    bp_min_flux, bp_max_flux = min_max(valid_flux_values(bp_flux))
    rp_min_flux, rp_max_flux = min_max(valid_flux_values(rp_flux))
    return SourceFluxStats(
        source_id=source_id,
        bp_min_flux=bp_min_flux,
        bp_max_flux=bp_max_flux,
        rp_min_flux=rp_min_flux,
        rp_max_flux=rp_max_flux,
    )


def flux_percentage_change(
    min_flux: Optional[float],
    max_flux: Optional[float],
) -> Optional[float]:
    if min_flux is None or max_flux is None or min_flux == 0:
        return None
    return ((max_flux - min_flux) / min_flux) * 100


def max_percentage_change(
    bp_min_flux: Optional[float],
    bp_max_flux: Optional[float],
    rp_min_flux: Optional[float],
    rp_max_flux: Optional[float],
) -> Optional[float]:
    changes = [
        change
        for change in (
            flux_percentage_change(bp_min_flux, bp_max_flux),
            flux_percentage_change(rp_min_flux, rp_max_flux),
        )
        if change is not None
    ]
    if not changes:
        return None
    return max(changes)
