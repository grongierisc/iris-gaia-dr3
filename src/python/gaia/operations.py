from __future__ import annotations

import csv
import gzip
import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Any

import iris
from iop import BusinessOperation

from .config import (
    DB_BATCH_SIZE,
    DONE_FILE,
    DOWNLOAD_DIR,
    ERROR_FILE,
    FIRST_20_FILE_RANGES,
    OUTPUT_DIR,
    RESULTS_FILE,
    archive_file_name,
)
from .messages import (
    ComputeResultsRequest,
    ComputeResultsResult,
    DownloadFileRequest,
    DownloadFileResult,
    ImportFileRequest,
    ImportFileResult,
    MarkRunCompleteRequest,
    MarkRunFailedRequest,
    PrepareRunRequest,
    PrepareRunResult,
)
from .models import DownloadFile, PhotometryChange, SourceFluxAggregate
from .parsing import aggregate_source_flux

DOWNLOAD_TABLE = DownloadFile._classname
SOURCE_AGGREGATE_TABLE = SourceFluxAggregate._classname
PHOTOMETRY_CHANGE_TABLE = PhotometryChange._classname
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _connect():
    return iris.dbapi.connect()


def _close_quietly(handle: Any) -> None:
    close = getattr(handle, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _fetch_count(cursor) -> int:
    row = cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


class GaiaRunStateOperation(BusinessOperation):
    def prepare_run(self, request: PrepareRunRequest) -> PrepareRunResult:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for marker in (DONE_FILE, ERROR_FILE, RESULTS_FILE, RESULTS_FILE.with_suffix(".csv.tmp")):
            marker.unlink(missing_ok=True)
        for file_range in FIRST_20_FILE_RANGES:
            file_path = DOWNLOAD_DIR / archive_file_name(file_range)
            file_path.unlink(missing_ok=True)
            Path(f"{file_path}.tmp").unlink(missing_ok=True)

        connection = _connect()
        cursor = connection.cursor()
        try:
            for table_name in (
                DOWNLOAD_TABLE,
                SOURCE_AGGREGATE_TABLE,
                PHOTOMETRY_CHANGE_TABLE,
            ):
                cursor.execute(f"DELETE FROM {table_name} WHERE run_name = ?", (request.run_name,))
            connection.commit()
        finally:
            _close_quietly(cursor)
            _close_quietly(connection)

        return PrepareRunResult(
            run_name=request.run_name,
            file_count=len(FIRST_20_FILE_RANGES),
        )

    def mark_run_complete(self, request: MarkRunCompleteRequest) -> MarkRunCompleteRequest:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ERROR_FILE.unlink(missing_ok=True)
        DONE_FILE.touch()
        return request

    def mark_run_failed(self, request: MarkRunFailedRequest) -> MarkRunFailedRequest:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ERROR_FILE.write_text(request.error_message, encoding="utf-8")
        return request


class GaiaDownloadOperation(BusinessOperation):
    def on_message(self, request: DownloadFileRequest) -> DownloadFileResult:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target_path = DOWNLOAD_DIR / archive_file_name(request.file_range)
        temp_path = Path(f"{target_path}.tmp")
        temp_path.unlink(missing_ok=True)

        try:
            sha256 = hashlib.sha256()
            with urllib.request.urlopen(request.url, timeout=120) as response:
                with temp_path.open("wb") as output_file:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        sha256.update(chunk)
                        output_file.write(chunk)

            with gzip.open(temp_path, "rb") as compressed_file:
                compressed_file.read(1)

            os.replace(temp_path, target_path)
            size_bytes = target_path.stat().st_size
            digest = sha256.hexdigest()
            self._record_download(
                request=request,
                local_path=str(target_path),
                size_bytes=size_bytes,
                sha256=digest,
                status="downloaded",
                error_message=None,
            )
            return DownloadFileResult(
                run_name=request.run_name,
                file_range=request.file_range,
                local_path=str(target_path),
                size_bytes=size_bytes,
                sha256=digest,
            )
        except Exception as error:
            temp_path.unlink(missing_ok=True)
            self._record_download(
                request=request,
                local_path=str(target_path),
                size_bytes=0,
                sha256="",
                status="failed",
                error_message=repr(error),
            )
            raise

    def _record_download(
        self,
        *,
        request: DownloadFileRequest,
        local_path: str,
        size_bytes: int,
        sha256: str,
        status: str,
        error_message: str | None,
    ) -> None:
        connection = _connect()
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"DELETE FROM {DOWNLOAD_TABLE} WHERE run_name = ? AND file_range = ?",
                (request.run_name, request.file_range),
            )
            cursor.execute(
                f"INSERT INTO {DOWNLOAD_TABLE} "
                "(run_name,file_range,url,local_path,size_bytes,sha256,status,error_message) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    request.run_name,
                    request.file_range,
                    request.url,
                    local_path,
                    size_bytes,
                    sha256,
                    status,
                    error_message,
                ),
            )
            connection.commit()
        finally:
            _close_quietly(cursor)
            _close_quietly(connection)


class GaiaImportOperation(BusinessOperation):
    def on_message(self, request: ImportFileRequest) -> ImportFileResult:
        source_count = 0
        batch: list[tuple[str, str, int, float | None, float | None, float | None, float | None]] = []

        connection = _connect()
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"DELETE FROM {SOURCE_AGGREGATE_TABLE} WHERE run_name = ? AND file_range = ?",
                (request.run_name, request.file_range),
            )
            connection.commit()

            with gzip.open(request.local_path, "rt", encoding="utf-8", newline="") as input_file:
                reader = csv.reader(line for line in input_file if line and line[0] != "#")
                next(reader, None)
                for row in reader:
                    if len(row) <= 16:
                        continue
                    stats = aggregate_source_flux(
                        source_id=int(row[1]),
                        bp_flux=row[11],
                        rp_flux=row[16],
                    )
                    if not stats.has_flux:
                        continue
                    batch.append(
                        (
                            request.run_name,
                            request.file_range,
                            stats.source_id,
                            stats.bp_min_flux,
                            stats.bp_max_flux,
                            stats.rp_min_flux,
                            stats.rp_max_flux,
                        )
                    )
                    source_count += 1
                    if len(batch) >= DB_BATCH_SIZE:
                        self._insert_aggregates(cursor, connection, batch)
                        batch.clear()

            if batch:
                self._insert_aggregates(cursor, connection, batch)

            return ImportFileResult(
                run_name=request.run_name,
                file_range=request.file_range,
                source_count=source_count,
            )
        finally:
            _close_quietly(cursor)
            _close_quietly(connection)

    def _insert_aggregates(self, cursor, connection, batch: list[tuple]) -> None:
        cursor.executemany(
            f"INSERT INTO {SOURCE_AGGREGATE_TABLE} "
            "(run_name,file_range,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        connection.commit()


class GaiaComputeOperation(BusinessOperation):
    def on_message(self, request: ComputeResultsRequest) -> ComputeResultsResult:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        connection = _connect()
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"DELETE FROM {PHOTOMETRY_CHANGE_TABLE} WHERE run_name = ?",
                (request.run_name,),
            )
            cursor.execute(
                f"""
                INSERT INTO {PHOTOMETRY_CHANGE_TABLE}
                    (run_name,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change)
                SELECT
                    run_name,
                    source_id,
                    bp_min_flux,
                    bp_max_flux,
                    rp_min_flux,
                    rp_max_flux,
                    percentage_change
                FROM (
                    SELECT
                        ? AS run_name,
                        source_id,
                        bp_min_flux,
                        bp_max_flux,
                        rp_min_flux,
                        rp_max_flux,
                        CASE
                            WHEN bp_change IS NULL THEN rp_change
                            WHEN rp_change IS NULL THEN bp_change
                            WHEN bp_change > rp_change THEN bp_change
                            ELSE rp_change
                        END AS percentage_change
                    FROM (
                        SELECT
                            source_id,
                            bp_min_flux,
                            bp_max_flux,
                            rp_min_flux,
                            rp_max_flux,
                            CASE
                                WHEN bp_min_flux IS NULL OR bp_min_flux = 0 THEN NULL
                                ELSE ((bp_max_flux - bp_min_flux) / bp_min_flux) * 100
                            END AS bp_change,
                            CASE
                                WHEN rp_min_flux IS NULL OR rp_min_flux = 0 THEN NULL
                                ELSE ((rp_max_flux - rp_min_flux) / rp_min_flux) * 100
                            END AS rp_change
                        FROM (
                            SELECT
                                source_id,
                                MIN(bp_min_flux) AS bp_min_flux,
                                MAX(bp_max_flux) AS bp_max_flux,
                                MIN(rp_min_flux) AS rp_min_flux,
                                MAX(rp_max_flux) AS rp_max_flux
                            FROM {SOURCE_AGGREGATE_TABLE}
                            WHERE run_name = ?
                            GROUP BY source_id
                        )
                    )
                )
                WHERE percentage_change > 100
                """,
                (request.run_name, request.run_name),
            )
            connection.commit()

            cursor.execute(
                f"SELECT COUNT(*) FROM {PHOTOMETRY_CHANGE_TABLE} WHERE run_name = ?",
                (request.run_name,),
            )
            result_count = _fetch_count(cursor)
            self._write_results(cursor, request.run_name)

            return ComputeResultsResult(
                run_name=request.run_name,
                result_count=result_count,
                results_file=str(RESULTS_FILE),
            )
        finally:
            _close_quietly(cursor)
            _close_quietly(connection)

    def _write_results(self, cursor, run_name: str) -> None:
        cursor.execute(
            f"SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
            f"FROM {PHOTOMETRY_CHANGE_TABLE} WHERE run_name = ? ORDER BY source_id",
            (run_name,),
        )

        temp_file = RESULTS_FILE.with_suffix(".csv.tmp")
        with temp_file.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.writer(output_file)
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                writer.writerows(rows)

        os.replace(temp_file, RESULTS_FILE)
