from __future__ import annotations

import os

from iop import PollingBusinessService, target

from .config import DONE_FILE, ERROR_FILE, LOCK_FILE
from .messages import GaiaBenchmarkRequest


class GaiaBenchmarkService(PollingBusinessService):
    Output = target()

    def on_poll(self):
        if DONE_FILE.exists() or ERROR_FILE.exists():
            return

        try:
            file_descriptor = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(file_descriptor)
        except FileExistsError:
            return

        self.send_request_async(self.Output, GaiaBenchmarkRequest())
