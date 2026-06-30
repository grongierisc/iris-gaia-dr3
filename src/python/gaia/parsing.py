from __future__ import annotations

import math
from collections.abc import Iterable, Iterator


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
