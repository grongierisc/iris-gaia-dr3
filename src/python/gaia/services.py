from __future__ import annotations

from iop import PollingBusinessService, target

from .messages import GaiaBenchmarkRequest
from .runtime import GaiaSettings


class GaiaBenchmarkService(GaiaSettings, PollingBusinessService):

    # Target for sending benchmark requests to the Gaia benchmark process
    Output = target()

    def on_poll(self):
        # Create the output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Check if the benchmark has already been completed or failed
        if self.done_file.exists() or self.error_file.exists():
            return

        # If the lock file exists, it means another process is already running the benchmark
        if self.lock_file.exists():
            return

        # Create the lock file to indicate that the benchmark is in progress
        self.lock_file.touch()

        # Send a benchmark request to the Gaia benchmark process
        self.send_request_async(self.Output, GaiaBenchmarkRequest())
