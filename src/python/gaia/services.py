from __future__ import annotations

import os

from iop import PollingBusinessService, target

from .messages import GaiaBenchmarkRequest
from .runtime import GaiaSettings


class GaiaBenchmarkService(GaiaSettings, PollingBusinessService):
    Output = target()

    def on_poll(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.done_file.exists() or self.error_file.exists():
            return
        try:
            fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            return
        self.send_request_async(self.Output, GaiaBenchmarkRequest())
