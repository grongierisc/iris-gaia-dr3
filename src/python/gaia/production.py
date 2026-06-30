from __future__ import annotations

from iop import Production

from .config import DOWNLOAD_POOL_SIZE, IMPORT_POOL_SIZE
from .operations import (
    GaiaComputeOperation,
    GaiaDownloadOperation,
    GaiaImportOperation,
    GaiaRunStateOperation,
)
from .processes import GaiaBenchmarkProcess
from .services import GaiaBenchmarkService


prod = Production("GaiaDR3.Production", testing_enabled=True, actor_pool_size=8)

service = prod.service(
    "GaiaBenchmarkService",
    GaiaBenchmarkService,
    adapter_settings={"CallInterval": 1},
)
process = prod.process("GaiaBenchmarkProcess", GaiaBenchmarkProcess)
run_state_operation = prod.operation("GaiaRunStateOperation", GaiaRunStateOperation)
download_operation = prod.operation(
    "GaiaDownloadOperation",
    GaiaDownloadOperation,
    pool_size=DOWNLOAD_POOL_SIZE,
)
import_operation = prod.operation(
    "GaiaImportOperation",
    GaiaImportOperation,
    pool_size=IMPORT_POOL_SIZE,
)
compute_operation = prod.operation("GaiaComputeOperation", GaiaComputeOperation)

service.connect(GaiaBenchmarkService.Output, process)
process.connect(GaiaBenchmarkProcess.RunStateOperation, run_state_operation)
process.connect(GaiaBenchmarkProcess.DownloadOperation, download_operation)
process.connect(GaiaBenchmarkProcess.ImportOperation, import_operation)
process.connect(GaiaBenchmarkProcess.ComputeOperation, compute_operation)
