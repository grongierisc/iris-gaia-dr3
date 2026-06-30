from __future__ import annotations

from dataclasses import dataclass

from iop import Message


@dataclass
class GaiaBenchmarkRequest(Message):
    """Request one Gaia DR3 benchmark run."""

    run_name: str = "gaia-dr3-first-20"


@dataclass
class PrepareRunRequest(Message):
    run_name: str


@dataclass
class PrepareRunResult(Message):
    run_name: str
    file_count: int


@dataclass
class DownloadFileRequest(Message):
    run_name: str
    file_range: str
    url: str


@dataclass
class DownloadFileResult(Message):
    run_name: str
    file_range: str
    local_path: str
    size_bytes: int
    sha256: str


@dataclass
class ImportFileRequest(Message):
    run_name: str
    file_range: str
    local_path: str


@dataclass
class ImportFileResult(Message):
    run_name: str
    file_range: str
    source_count: int


@dataclass
class ComputeResultsRequest(Message):
    run_name: str


@dataclass
class ComputeResultsResult(Message):
    run_name: str
    result_count: int
    results_file: str


@dataclass
class MarkRunCompleteRequest(Message):
    run_name: str
    results_file: str
    result_count: int


@dataclass
class MarkRunFailedRequest(Message):
    run_name: str
    error_message: str
