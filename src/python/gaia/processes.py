from __future__ import annotations

from iop import BusinessProcess, target

from typing import TypeVar

from . import operations
from .messages import (
    FileRequest,
    FileResult,
    GaiaBenchmarkRequest,
)
from .runtime import GaiaSettings

T = TypeVar("T")

class GaiaBenchmarkProcess(GaiaSettings, BusinessProcess):

    # Targets for sending messages to Business Operations declared in production.py
    DownloadOperation = target()
    ImportOperation = target()
    ComputeOperation = target()
    ExportOperation = target()

    def on_message(self, request: GaiaBenchmarkRequest):
        try:
            # Start from a clean run: remove old markers and rows for this run name
            self._prepare(request.run_name)

            # Download the 20 Gaia files in parallel
            downloads = self._send_parallel(
                self.DownloadOperation,
                [
                    FileRequest(request.run_name, file_range, url=self.archive_url(file_range))
                    for file_range in self.file_ranges
                ],
                FileResult,
                "Download Gaia DR3 files",
            )

            # Import the downloaded files in parallel
            self._send_parallel(
                self.ImportOperation,
                [
                    FileRequest(result.run_name, result.file_range, local_path=result.local_path)
                    for result in downloads
                ],
                FileResult,
                "Import Gaia DR3 files",
            )

            # Compute final rows in IRIS,
            result = self.send_request_sync(
                self.ComputeOperation,
                request,
                timeout=self.request_timeout,
            )

            # Export the final results to a CSV file
            result = self.send_request_sync(
                self.ExportOperation,
                result,
                timeout=self.request_timeout,
            )

            # Write the success marker watched by RunChallenge.sh
            self._complete()
            return result
        except Exception as error:
            # Write the failure marker watched by RunChallenge.sh, then keep the IoP error visible
            self._fail(repr(error))
            raise

    def _send_parallel(
        self,
        target,
        requests: list[T],
        expected,
        description: str,
    ) -> list[T]:
        # send_multi_request_sync fans out one request per file and waits for all responses
        responses = self.send_multi_request_sync(
            [(target, request) for request in requests],
            timeout=self.request_timeout,
            description=description,
        )
        results: list[T] = []
        for response_target, request, response, status in responses:
            # IoP returns a status for each response; 1 means success
            if status != 1:
                raise RuntimeError(
                    f"{response_target} failed with status {status} "
                    f"for {type(request).__name__}"
                )
            if not isinstance(response, expected):
                raise TypeError(
                    f"{response_target} returned {type(response).__name__}, "
                    f"expected {expected.__name__}"
                )
            results.append(response)
        return results

    def _prepare(self, run_name: str) -> None:
        # Files are used as simple run markers for the challenge script
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        for marker in (
            self.done_file,
            self.error_file,
            self.results_file,
            self.results_file.with_suffix(".csv.tmp"),
        ):
            marker.unlink(missing_ok=True)

        # Persistent rows are scoped by run_name, so deleting the current run is repeatable
        with operations.db() as (cursor, connection):
            for table in (operations.SOURCE_TABLE, operations.CHANGE_TABLE):
                cursor.execute(f"DELETE FROM {table} WHERE run_name = ?", (run_name,))
            connection.commit()

    def _complete(self) -> None:
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
