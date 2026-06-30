from __future__ import annotations

from typing import TypeVar

from iop import BusinessProcess, Message, TargetSettingRef, target

from .messages import (
    ComputeResult,
    FileRequest,
    FileResult,
    GaiaBenchmarkRequest,
    StateRequest,
)
from .runtime import GaiaSettings

T = TypeVar("T", bound=Message)


class GaiaBenchmarkProcess(GaiaSettings, BusinessProcess):
    RunStateOperation = target()
    DownloadOperation = target()
    ImportOperation = target()
    ComputeOperation = target()

    def on_message(self, request: GaiaBenchmarkRequest):
        try:
            self.send_request_sync(
                self.RunStateOperation,
                StateRequest(request.run_name, "prepare"),
                timeout=self.request_timeout,
            )
            downloads = self._multi(
                self.DownloadOperation,
                [
                    FileRequest(request.run_name, file_range, url=self.archive_url(file_range))
                    for file_range in self.file_ranges
                ],
                FileResult,
                "Download Gaia DR3 files",
            )
            self._multi(
                self.ImportOperation,
                [
                    FileRequest(result.run_name, result.file_range, local_path=result.local_path)
                    for result in downloads
                ],
                FileResult,
                "Import Gaia DR3 files",
            )
            result = self.send_request_sync(
                self.ComputeOperation,
                StateRequest(request.run_name, "compute"),
                timeout=self.request_timeout,
            )
            if not isinstance(result, ComputeResult):
                raise TypeError(f"Unexpected compute response: {type(result).__name__}")
            self.send_request_sync(
                self.RunStateOperation,
                StateRequest(
                    request.run_name,
                    "complete",
                    results_file=result.results_file,
                    result_count=result.result_count,
                ),
                timeout=self.request_timeout,
            )
            return result
        except Exception as error:
            self._mark_failed(request.run_name, repr(error))
            raise

    def _multi(
        self,
        target: str | TargetSettingRef,
        requests: list[Message],
        expected: type[T],
        description: str,
    ) -> list[T]:
        responses = self.send_multi_request_sync(
            [(target, request) for request in requests],
            timeout=self.request_timeout,
            description=description,
        )
        results: list[T] = []
        for response_target, request, response, status in responses:
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

    def _mark_failed(self, run_name: str, error_message: str) -> None:
        try:
            self.send_request_sync(
                self.RunStateOperation,
                StateRequest(run_name, "failed", error_message=error_message),
                timeout=self.request_timeout,
            )
        except Exception as mark_error:
            self.log_error(f"Could not mark Gaia run failed: {mark_error!r}")
