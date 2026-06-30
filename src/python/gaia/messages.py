from __future__ import annotations

from dataclasses import dataclass

from iop import Message


@dataclass
class GaiaBenchmarkRequest(Message):
    """Request one Gaia DR3 benchmark run."""

    run_name: str = "gaia-dr3-first-20"
