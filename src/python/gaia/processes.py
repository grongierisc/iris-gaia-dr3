from __future__ import annotations

from typing import TypeVar

from iop import BusinessProcess, Message, target

from .config import FIRST_20_FILE_RANGES, REQUEST_TIMEOUT_SECONDS, archive_url
from .messages import (
    ComputeResultsRequest,
    ComputeResultsResult,
    DownloadFileRequest,
    DownloadFileResult,
    GaiaBenchmarkRequest,
    ImportFileRequest,
    ImportFileResult,
    MarkRunCompleteRequest,
    MarkRunFailedRequest,
    PrepareRunRequest,
)

TMessage = TypeVar("TMessage", bound=Message)


class GaiaBenchmarkProcess(BusinessProcess):
    RunStateOperation = target()
    DownloadOperation = target()
    ImportOperation = target()
    ComputeOperation = target()

    def on_message(self, request: GaiaBenchmarkRequest):
        try:
            self.send_request_sync(
                self.RunStateOperation,
                PrepareRunRequest(run_name=request.run_name),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            download_results = self._send_download_requests(request.run_name)
            self._send_import_requests(request.run_name, download_results)

            compute_result = self.send_request_sync(
                self.ComputeOperation,
                ComputeResultsRequest(run_name=request.run_name),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if not isinstance(compute_result, ComputeResultsResult):
                raise TypeError(f"Unexpected compute response: {type(compute_result).__name__}")

            self.send_request_sync(
                self.RunStateOperation,
                MarkRunCompleteRequest(
                    run_name=request.run_name,
                    results_file=compute_result.results_file,
                    result_count=compute_result.result_count,
                ),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            return compute_result
        except Exception as error:
            self._mark_failed(request.run_name, repr(error))
            raise

    def _send_download_requests(self, run_name: str) -> list[DownloadFileResult]:
        target_requests = [
            (
                self.DownloadOperation,
                DownloadFileRequest(
                    run_name=run_name,
                    file_range=file_range,
                    url=archive_url(file_range),
                ),
            )
            for file_range in FIRST_20_FILE_RANGES
        ]
        responses = self.send_multi_request_sync(
            target_requests,
            timeout=REQUEST_TIMEOUT_SECONDS,
            description="Download Gaia DR3 epoch photometry files",
        )
        return self._checked_multi_responses(responses, DownloadFileResult)

    def _send_import_requests(
        self,
        run_name: str,
        download_results: list[DownloadFileResult],
    ) -> list[ImportFileResult]:
        target_requests = [
            (
                self.ImportOperation,
                ImportFileRequest(
                    run_name=run_name,
                    file_range=result.file_range,
                    local_path=result.local_path,
                ),
            )
            for result in download_results
        ]
        responses = self.send_multi_request_sync(
            target_requests,
            timeout=REQUEST_TIMEOUT_SECONDS,
            description="Import Gaia DR3 epoch photometry files",
        )
        return self._checked_multi_responses(responses, ImportFileResult)

    def _checked_multi_responses(
        self,
        responses: list[tuple[str, Message, object, int]],
        expected_type: type[TMessage],
    ) -> list[TMessage]:
        checked: list[TMessage] = []
        for target, request, response, status in responses:
            if status != 1:
                raise RuntimeError(
                    f"{target} failed with status {status} for {type(request).__name__}"
                )
            if not isinstance(response, expected_type):
                raise TypeError(
                    f"{target} returned {type(response).__name__}, "
                    f"expected {expected_type.__name__}"
                )
            checked.append(response)
        return checked

    def _mark_failed(self, run_name: str, error_message: str) -> None:
        try:
            self.send_request_sync(
                self.RunStateOperation,
                MarkRunFailedRequest(run_name=run_name, error_message=error_message),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as mark_error:
            self.log_error(f"Could not mark Gaia run failed: {mark_error!r}")
