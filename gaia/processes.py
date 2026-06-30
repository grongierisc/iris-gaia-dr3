from __future__ import annotations

import asyncio

from iop import BusinessProcess, target

from .messages import (
    ComputeRequest,
    ComputeResult,
    DownloadFileRequest,
    DownloadFileResult,
    ExportCsvRequest,
    ExportCsvResult,
    GaiaBenchmarkRequest,
    ImportFileRequest,
    ImportFileResult,
    PrepareRunRequest,
    PrepareRunResult,
)
from .runtime import GaiaSettings


class GaiaBenchmarkProcess(GaiaSettings, BusinessProcess):

    # Targets for sending messages to Business Operations declared in production.py
    PrepareOperation = target()
    DownloadOperation = target()
    ImportOperation = target()
    ComputeOperation = target()
    ExportOperation = target()

    def on_message(self, request: GaiaBenchmarkRequest):
        try:
            # Start from a clean run: remove old markers and rows for this run name
            self.log_info(f"Preparing Gaia run {request.run_name}", to_console=True)
            self._expect(
                self.send_request_sync(
                    self.PrepareOperation,
                    PrepareRunRequest(request.run_name),
                    timeout=self.request_timeout,
                    description="Prepare Gaia run",
                ),
                PrepareRunResult,
                self.PrepareOperation,
            )

            # Download the 20 Gaia files in parallel
            self.log_info(f"Downloading Gaia DR3 files for run {request.run_name}", to_console=True)
            downloads = asyncio.run(
                self._send_parallel(
                    self.DownloadOperation,
                    [
                        DownloadFileRequest(request.run_name, file_range, self.archive_url(file_range))
                        for file_range in self.file_ranges
                    ],
                    DownloadFileResult,
                    "Download Gaia DR3 files",
                )
            )

            # Import the downloaded files in parallel
            self.log_info(f"Importing Gaia DR3 files for run {request.run_name}", to_console=True)
            asyncio.run(
                self._send_parallel(
                    self.ImportOperation,
                    [
                        ImportFileRequest(result.run_name, result.file_range, result.local_path)
                        for result in downloads
                    ],
                    ImportFileResult,
                    "Import Gaia DR3 files",
                )
            )

            # Compute final rows in IRIS
            self.log_info(f"Computing final rows for run {request.run_name}", to_console=True)
            result = self._expect(
                self.send_request_sync(
                    self.ComputeOperation,
                    ComputeRequest(request.run_name),
                    timeout=self.request_timeout,
                    description="Compute final rows",
                ),
                ComputeResult,
                self.ComputeOperation,
            )

            # Export the final results to a CSV file
            self.log_info(f"Exporting final results for run {request.run_name}", to_console=True)
            result = self._expect(
                self.send_request_sync(
                    self.ExportOperation,
                    ExportCsvRequest(result.run_name, result.result_count),
                    timeout=self.request_timeout,
                    description="Export final results",
                ),
                ExportCsvResult,
                self.ExportOperation,
            )

            # Write the success marker watched by RunChallenge.sh
            self._complete()
            return result

        except Exception as error:
            # Write the failure marker watched by RunChallenge.sh, then keep the IoP error visible
            self._fail(repr(error))
            raise

    def _expect(self, response, expected, target):
        if not isinstance(response, expected):
            raise TypeError(
                f"{target} returned {type(response).__name__}, "
                f"expected {expected.__name__}"
            )
        return response

    async def _send_parallel(
        self,
        target,
        requests,
        expected,
        description: str,
    ):
        # send_request_async_ng lets the process log each file as soon as it completes
        tasks = [
            asyncio.create_task(
                self.send_request_async_ng(
                    target,
                    request,
                    timeout=self.request_timeout,
                    description=f"{description}: {request.file_range}",
                )
            )
            for request in requests
        ]
        results = []
        completed = 0
        try:
            for done in asyncio.as_completed(tasks):
                result = self._expect(await done, expected, target)
                results.append(result)
                completed += 1
                self.log_info(
                    f"{description}: {completed}/{len(tasks)} {result.file_range}",
                    to_console=True,
                )
        except Exception:
            for task in tasks:
                task.cancel()
            raise
        return results

    def _complete(self) -> None:
        self.log_info("Gaia run completed successfully", to_console=True)
        self.error_file.unlink(missing_ok=True)
        self.done_file.touch()

    def _fail(self, error_message: str) -> None:
        try:
            # Do not let a marker-write problem hide the original workflow error
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.done_file.unlink(missing_ok=True)
            self.error_file.write_text(error_message, encoding="utf-8")
        except Exception as error:
            self.log_error(f"Could not mark Gaia run failed: {error!r}")
