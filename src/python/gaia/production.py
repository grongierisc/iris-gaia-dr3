from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iop import Production

from .operations import (
    GaiaComputeOperation,
    GaiaDownloadOperation,
    GaiaImportOperation,
    GaiaRunStateOperation,
)
from .processes import GaiaBenchmarkProcess
from .services import GaiaBenchmarkService


def build_production(
    gaia_settings: Mapping[str, Any],
    *,
    actor_pool_size: int,
    download_pool_size: int,
    import_pool_size: int,
) -> Production:
    prod = Production(
        "GaiaDR3.Production",
        testing_enabled=True,
        actor_pool_size=actor_pool_size,
    )
    service = prod.service(
        "GaiaBenchmarkService",
        GaiaBenchmarkService,
        settings=gaia_settings,
        adapter_settings={"CallInterval": 1},
    )
    process = prod.process(
        "GaiaBenchmarkProcess",
        GaiaBenchmarkProcess,
        settings=gaia_settings,
    )
    run_state = prod.operation(
        "GaiaRunStateOperation",
        GaiaRunStateOperation,
        settings=gaia_settings,
    )
    download = prod.operation(
        "GaiaDownloadOperation",
        GaiaDownloadOperation,
        settings=gaia_settings,
        pool_size=download_pool_size,
    )
    import_ = prod.operation(
        "GaiaImportOperation",
        GaiaImportOperation,
        settings=gaia_settings,
        pool_size=import_pool_size,
    )
    compute = prod.operation(
        "GaiaComputeOperation",
        GaiaComputeOperation,
        settings=gaia_settings,
    )

    service.connect(GaiaBenchmarkService.Output, process)
    process.connect(GaiaBenchmarkProcess.RunStateOperation, run_state)
    process.connect(GaiaBenchmarkProcess.DownloadOperation, download)
    process.connect(GaiaBenchmarkProcess.ImportOperation, import_)
    process.connect(GaiaBenchmarkProcess.ComputeOperation, compute)
    return prod
