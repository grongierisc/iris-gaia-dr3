from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from iop import Production

from .operations import (
    GaiaComputeOperation,
    GaiaCsvExportOperation,
    GaiaDownloadOperation,
    GaiaImportOperation,
    GaiaPrepareRunOperation,
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
    # The Production object is the IoP message graph
    prod = Production(
        "GaiaDR3.Production",
        testing_enabled=True,
        actor_pool_size=actor_pool_size,
    )

    # Business Service: starts the benchmark
    service = prod.service(
        "GaiaBenchmarkService",
        GaiaBenchmarkService,
        settings=gaia_settings,
        adapter_settings={"CallInterval": 1},
    )

    # Business Process: orchestrates the whole workflow
    process = prod.process(
        "GaiaBenchmarkProcess",
        GaiaBenchmarkProcess,
        settings=gaia_settings,
    )

    # Business Operations: isolate side effects and heavy work
    prepare = prod.operation(
        "GaiaPrepareRunOperation",
        GaiaPrepareRunOperation,
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
    export = prod.operation(
        "GaiaCsvExportOperation",
        GaiaCsvExportOperation,
        settings=gaia_settings,
    )

    # Routes: messages flow Service -> Process -> Operations
    service.connect(GaiaBenchmarkService.Output, process)
    process.connect(GaiaBenchmarkProcess.PrepareOperation, prepare)
    process.connect(GaiaBenchmarkProcess.DownloadOperation, download)
    process.connect(GaiaBenchmarkProcess.ImportOperation, import_)
    process.connect(GaiaBenchmarkProcess.ComputeOperation, compute)
    process.connect(GaiaBenchmarkProcess.ExportOperation, export)
    return prod
