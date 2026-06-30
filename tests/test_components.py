from __future__ import annotations

import csv
import gzip
import io

import pytest

from gaia import operations
from gaia.messages import (
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
from gaia.exporting import RESULT_HEADER, write_results_csv
from gaia.operations import (
    GaiaDbOperation,
    GaiaDownloadOperation,
)
from gaia.processes import GaiaBenchmarkProcess
from gaia.services import GaiaBenchmarkService


def configure(component, tmp_path, *, boundaries: str = "000000,003112,005264"):
    component.ArchiveUrlTemplate = "https://example.invalid/EpochPhotometry_%s.csv.gz"
    component.FileBoundaries = boundaries
    component.OutputDir = str(tmp_path)
    component.RequestTimeoutSeconds = 99
    component.HttpTimeoutSeconds = 7
    component.DbBatchSize = 2
    return component


class FakeConnection:
    def __init__(self):
        self.commit_count = 0
        self.closed = False
        self.cursor_result = None

    def cursor(self):
        return self.cursor_result

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []
        self.executemany_calls: list[tuple[str, list[tuple]]] = []
        self.fetchone_result = (0,)
        self.fetchmany_results: list[list[tuple]] = []
        self.closed = False

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), tuple(params)))

    def executemany(self, sql, batch):
        self.executemany_calls.append((" ".join(sql.split()), list(batch)))

    def fetchone(self):
        return self.fetchone_result

    def fetchmany(self, _size):
        if self.fetchmany_results:
            return self.fetchmany_results.pop(0)
        return []

    def close(self):
        self.closed = True


def patch_db(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection()
    connection.cursor_result = cursor
    monkeypatch.setattr(operations.iris.dbapi, "connect", lambda: connection)
    return cursor, connection


def test_service_poll_creates_lock_and_sends_once(tmp_path):
    service = configure(GaiaBenchmarkService(), tmp_path)
    service.Output = "GaiaBenchmarkProcess"
    sent = []
    service.send_request_async = lambda target, request: sent.append((target, request))

    service.on_poll()
    service.on_poll()

    assert service.lock_file.exists()
    assert len(sent) == 1
    assert sent[0][0] == "GaiaBenchmarkProcess"
    assert isinstance(sent[0][1], GaiaBenchmarkRequest)


def test_process_orchestrates_prepare_download_import_compute_complete(tmp_path):
    process = configure(GaiaBenchmarkProcess(), tmp_path, boundaries="000000,000002,000005")
    process.PrepareOperation = "prepare"
    process.DownloadOperation = "download"
    process.ImportOperation = "import"
    process.ComputeOperation = "compute"
    process.ExportOperation = "export"
    sync_calls = []
    async_calls = []
    logs = []

    def send_request_sync(target, request, timeout=-1, description=None):
        sync_calls.append((target, request, timeout, description))
        if target == "prepare":
            return PrepareRunResult(request.run_name)
        if target == "compute":
            return ComputeResult(request.run_name, 2)
        if target == "export":
            return ExportCsvResult(request.run_name, request.result_count, "output/results.csv")
        return request

    async def send_request_async_ng(target, request, timeout=-1, description=None):
        async_calls.append((target, request, timeout, description))
        if target == "download":
            return DownloadFileResult(request.run_name, request.file_range, f"/tmp/{request.file_range}.csv.gz")
        if target == "import":
            return ImportFileResult(request.run_name, request.file_range, 10)
        return request

    process.send_request_sync = send_request_sync
    process.send_request_async_ng = send_request_async_ng
    process.log_info = lambda message, *args, **kwargs: logs.append(message)

    result = process.on_message(GaiaBenchmarkRequest("run-1"))

    assert result == ExportCsvResult("run-1", 2, "output/results.csv")
    assert [call[0] for call in sync_calls] == ["prepare", "compute", "export"]
    assert [type(call[1]) for call in sync_calls] == [
        PrepareRunRequest,
        ComputeRequest,
        ExportCsvRequest,
    ]
    assert {call[2] for call in sync_calls + async_calls} == {99}
    assert process.done_file.exists()
    assert not process.error_file.exists()
    download_requests = [request for target, request, _timeout, _description in async_calls if target == "download"]
    assert {request.file_range for request in download_requests} == {"000000-000001", "000002-000004"}
    assert {request.url.rsplit("/", 1)[-1] for request in download_requests} == {
        "EpochPhotometry_000000-000001.csv.gz",
        "EpochPhotometry_000002-000004.csv.gz",
    }
    import_requests = [request for target, request, _timeout, _description in async_calls if target == "import"]
    assert {request.local_path for request in import_requests} == {
        "/tmp/000000-000001.csv.gz",
        "/tmp/000002-000004.csv.gz",
    }
    download_logs = [log for log in logs if log.startswith("Download Gaia DR3 files:")]
    import_logs = [log for log in logs if log.startswith("Import Gaia DR3 files:")]
    assert len(download_logs) == 2
    assert len(import_logs) == 2
    assert {log.rsplit(" ", 1)[-1] for log in download_logs} == {"000000-000001", "000002-000004"}
    assert {log.rsplit(" ", 1)[-1] for log in import_logs} == {"000000-000001", "000002-000004"}


def test_process_marks_run_failed_when_downstream_call_fails(tmp_path):
    process = configure(GaiaBenchmarkProcess(), tmp_path)
    process.PrepareOperation = "prepare"
    process.DownloadOperation = "download"
    sync_calls = []
    async_calls = []

    def send_request_sync(target, request, timeout=-1, description=None):
        sync_calls.append((target, request, timeout, description))
        if target == "prepare":
            return PrepareRunResult(request.run_name)
        raise AssertionError("compute/export should not be called")

    async def send_request_async_ng(target, request, timeout=-1, description=None):
        async_calls.append((target, request, timeout, description))
        raise RuntimeError("download failed")

    process.send_request_sync = send_request_sync
    process.send_request_async_ng = send_request_async_ng

    with pytest.raises(RuntimeError, match="download failed"):
        process.on_message(GaiaBenchmarkRequest("run-2"))

    assert "download failed" in process.error_file.read_text(encoding="utf-8")
    assert not process.done_file.exists()
    assert [call[0] for call in sync_calls] == ["prepare"]
    assert async_calls[0][0] == "download"


def test_db_operation_prepares_run_and_clears_persistent_rows(tmp_path, monkeypatch):
    cursor, connection = patch_db(monkeypatch)
    operation = configure(GaiaDbOperation(), tmp_path, boundaries="000000,000002")
    operation.on_init()
    for path in (
        operation.done_file,
        operation.error_file,
        operation.results_file,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale", encoding="utf-8")

    result = operation.prepare_run(PrepareRunRequest("run-3"))

    assert result == PrepareRunResult("run-3")
    assert not operation.done_file.exists()
    assert not operation.error_file.exists()
    assert not operation.results_file.exists()
    assert [params for _sql, params in cursor.executed] == [("run-3",), ("run-3",)]
    assert connection.commit_count == 1
    operation.on_tear_down()
    assert cursor.closed
    assert connection.closed


def test_db_operation_parses_gzip_and_batches_aggregate_rows(tmp_path, monkeypatch):
    cursor, connection = patch_db(monkeypatch)
    operation = configure(GaiaDbOperation(), tmp_path)
    operation.on_init()
    input_file = tmp_path / "input.csv.gz"
    rows = [
        [f"h{i}" for i in range(17)],
        ["0", "42", *[""] * 9, "[10.0, 5.0]", *[""] * 4, "[3.0, 9.0]"],
        ["0", "43", *[""] * 9, "[NaN]", *[""] * 4, ""],
        ["0", "44", *[""] * 9, "[7.0]", *[""] * 4, "[1.0, 2.0]"],
    ]
    with gzip.open(input_file, "wt", encoding="utf-8", newline="") as output:
        output.write("#comment\n")
        csv.writer(output).writerows(rows)

    result = operation.import_file(ImportFileRequest("run-4", "000000-003111", str(input_file)))

    assert result == ImportFileResult("run-4", "000000-003111", 2)
    assert connection.commit_count == 2
    assert len(cursor.executemany_calls) == 1
    inserted_rows = [row for _sql, batch in cursor.executemany_calls for row in batch]
    assert inserted_rows == [
        ("run-4", "000000-003111", 42, 5.0, 10.0, 3.0, 9.0),
        ("run-4", "000000-003111", 44, 7.0, 7.0, 1.0, 2.0),
    ]
    operation.on_tear_down()
    assert cursor.closed
    assert connection.closed


def test_download_operation_writes_readable_local_file(tmp_path, monkeypatch):
    operation = configure(GaiaDownloadOperation(), tmp_path)
    payload = gzip.compress(b"hello")
    calls = []
    session_closed = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            pass

        raw = io.BytesIO(payload)

    class Session:
        def get(self, url, stream, timeout):
            calls.append((url, stream, timeout))
            return Response()

        def close(self):
            session_closed.append(True)

    monkeypatch.setattr(operations.requests, "Session", Session)
    operation.on_init()

    result = operation.on_message(
        DownloadFileRequest(
            "run-5",
            "000000-003111",
            "https://example.invalid/EpochPhotometry_000000-003111.csv.gz",
        )
    )

    assert gzip.open(result.local_path, "rb").read() == b"hello"
    assert result == DownloadFileResult("run-5", "000000-003111", result.local_path)
    assert calls == [
        ("https://example.invalid/EpochPhotometry_000000-003111.csv.gz", True, 7),
    ]
    operation.on_tear_down()
    assert session_closed == [True]


def test_db_operation_computes_with_lifecycle_db_connection(tmp_path, monkeypatch):
    cursor, connection = patch_db(monkeypatch)
    cursor.fetchone_result = (2,)
    operation = configure(GaiaDbOperation(), tmp_path)
    operation.on_init()

    result = operation.compute_results(ComputeRequest("run-6"))

    assert result == ComputeResult("run-6", 2)
    assert [params for _sql, params in cursor.executed] == [
        ("run-6",),
        ("run-6", "run-6"),
        ("run-6",),
    ]
    assert connection.commit_count == 1
    operation.on_tear_down()
    assert cursor.closed
    assert connection.closed


def test_db_operation_exports_results_file(tmp_path, monkeypatch):
    cursor, connection = patch_db(monkeypatch)
    cursor.fetchmany_results = [
        [(1, 2.0, 3.0, 4.0, 5.0, 150.0)],
        [(2, 6.0, 7.0, 8.0, 9.0, 175.0)],
    ]
    operation = configure(GaiaDbOperation(), tmp_path)
    operation.on_init()

    result = operation.export_csv(ExportCsvRequest("run-6", 2))

    assert result == ExportCsvResult("run-6", 2, str(operation.results_file))
    assert operation.results_file.read_text(encoding="utf-8").splitlines() == [
        "source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change",
        "1,2.0,3.0,4.0,5.0,150.0",
        "2,6.0,7.0,8.0,9.0,175.0",
    ]
    operation.on_tear_down()
    assert cursor.closed
    assert connection.closed


def test_write_results_csv_writes_header_and_rows(tmp_path):
    path = tmp_path / "results.csv"

    write_results_csv(path, [(1, 2.0, 3.0, 4.0, 5.0, 150.0)])

    assert path.read_text(encoding="utf-8").splitlines() == [
        ",".join(RESULT_HEADER),
        "1,2.0,3.0,4.0,5.0,150.0",
    ]
