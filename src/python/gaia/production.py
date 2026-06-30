from __future__ import annotations

from iop import Production

from .operations import GaiaSqlOperation
from .processes import GaiaBenchmarkProcess
from .services import GaiaBenchmarkService


prod = Production("GaiaDR3.Production", testing_enabled=True)

service = prod.service(
    "GaiaBenchmarkService",
    GaiaBenchmarkService,
    adapter_settings={"CallInterval": 1},
)
process = prod.process("GaiaBenchmarkProcess", GaiaBenchmarkProcess)
operation = prod.operation("GaiaSqlOperation", GaiaSqlOperation)
service.connect(GaiaBenchmarkService.Output, process)
process.connect(GaiaBenchmarkProcess.SqlOperation, operation)
