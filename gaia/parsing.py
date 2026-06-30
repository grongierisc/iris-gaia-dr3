from __future__ import annotations

import csv
import gzip
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Optional

AggregateRow = tuple[str, str, int, Optional[float], Optional[float], Optional[float], Optional[float]]


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


def source_flux_aggregate_batches(
    *,
    run_name: str,
    file_range: str,
    local_path: str,
    batch_size: int,
) -> Iterator[list[AggregateRow]]:
    batch: list[AggregateRow] = []
    with gzip.open(local_path, "rt", encoding="utf-8", newline="") as input_file:
        reader = csv.reader(line for line in input_file if line and line[0] != "#")
        next(reader, None)
        for row in reader:
            if len(row) <= 16:
                continue
            stats = aggregate_source_flux(int(row[1]), row[11], row[16])
            if not stats.has_flux:
                continue
            batch.append(
                (
                    run_name,
                    file_range,
                    stats.source_id,
                    stats.bp_min_flux,
                    stats.bp_max_flux,
                    stats.rp_min_flux,
                    stats.rp_max_flux,
                )
            )
            if len(batch) >= max(1, batch_size):
                yield batch
                batch = []
    if batch:
        yield batch


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
