from __future__ import annotations

from iop import BusinessProcess, target

from .messages import GaiaBenchmarkRequest


class GaiaBenchmarkProcess(BusinessProcess):
    SqlOperation = target()

    def on_message(self, request: GaiaBenchmarkRequest):
        self.send_request_async(self.SqlOperation, request)
        return request
