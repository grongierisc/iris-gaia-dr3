from __future__ import annotations

from dataclasses import dataclass

from iop import Message


# IoP components exchange small dataclass messages with primitive fields
@dataclass
class GaiaBenchmarkRequest(Message):
    run_name: str = "gaia-dr3-first-20"


@dataclass
class PrepareRunRequest(Message):
    run_name: str


@dataclass
class PrepareRunResult(Message):
    run_name: str


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


@dataclass
class ImportFileRequest(Message):
    run_name: str
    file_range: str
    local_path: str


@dataclass
class ImportFileResult(Message):
    run_name: str
    file_range: str
    imported_rows: int


@dataclass
class ComputeRequest(Message):
    run_name: str


@dataclass
class ComputeResult(Message):
    run_name: str
    result_count: int


@dataclass
class ExportCsvRequest(Message):
    run_name: str
    result_count: int


@dataclass
class ExportCsvResult(Message):
    run_name: str
    result_count: int
    results_file: str
