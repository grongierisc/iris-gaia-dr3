from __future__ import annotations

from dataclasses import dataclass

from iop import Message


@dataclass
class GaiaBenchmarkRequest(Message):
    run_name: str = "gaia-dr3-first-20"


@dataclass
class StateRequest(Message):
    run_name: str
    action: str
    error_message: str = ""
    results_file: str = ""
    result_count: int = 0


@dataclass
class FileRequest(Message):
    run_name: str
    file_range: str
    url: str = ""
    local_path: str = ""


@dataclass
class FileResult(Message):
    run_name: str
    file_range: str
    local_path: str = ""


@dataclass
class ComputeResult(Message):
    run_name: str
    result_count: int
    results_file: str
