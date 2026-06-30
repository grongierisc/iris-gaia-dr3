from __future__ import annotations

from dataclasses import dataclass

from iop import Message


# IoP components exchange small dataclass messages with primitive fields
@dataclass
class GaiaBenchmarkRequest(Message):
    run_name: str = "gaia-dr3-first-20"


@dataclass
class PrepareRunResult(Message):
    run_name: str


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
