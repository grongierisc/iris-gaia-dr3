from __future__ import annotations

import csv
import gzip
import hashlib
import os
import urllib.request
from contextlib import contextmanager, suppress

import iris
from iop import BusinessOperation

from .messages import ComputeResult, FileRequest, FileResult, StateRequest
from .models import DownloadFile, PhotometryChange, SourceFluxAggregate
from .parsing import aggregate_source_flux
from .runtime import GaiaSettings

DOWNLOAD_TABLE = DownloadFile._classname
SOURCE_TABLE = SourceFluxAggregate._classname
CHANGE_TABLE = PhotometryChange._classname


@contextmanager
def db():
    connection = iris.dbapi.connect()
    cursor = connection.cursor()
    try:
        yield cursor, connection
    finally:
        for handle in (cursor, connection):
            with suppress(Exception):
                handle.close()


class GaiaRunStateOperation(GaiaSettings, BusinessOperation):
    def on_message(self, request: StateRequest) -> StateRequest:
        if request.action == "prepare":
            self._prepare(request.run_name)
        elif request.action == "complete":
            self.error_file.unlink(missing_ok=True)
            self.done_file.touch()
        elif request.action == "failed":
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.error_file.write_text(request.error_message, encoding="utf-8")
        else:
            raise ValueError(f"Unknown Gaia run action: {request.action}")
        return request

    def _prepare(self, run_name: str) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        for marker in (
            self.done_file,
            self.error_file,
            self.results_file,
            self.results_file.with_suffix(".csv.tmp"),
        ):
            marker.unlink(missing_ok=True)
        for file_range in self.file_ranges:
            path = self.download_file(file_range)
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)

        with db() as (cursor, connection):
            for table in (DOWNLOAD_TABLE, SOURCE_TABLE, CHANGE_TABLE):
                cursor.execute(f"DELETE FROM {table} WHERE run_name = ?", (run_name,))
            connection.commit()


class GaiaDownloadOperation(GaiaSettings, BusinessOperation):
    def on_message(self, request: FileRequest) -> FileResult:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        path = self.download_file(request.file_range)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.unlink(missing_ok=True)
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(request.url, timeout=self.http_timeout) as response:
                with temp.open("wb") as output:
                    for chunk in iter(lambda: response.read(self.download_chunk_size), b""):
                        digest.update(chunk)
                        output.write(chunk)
            with gzip.open(temp, "rb") as compressed:
                compressed.read(1)
            os.replace(temp, path)
            result = FileResult(
                request.run_name,
                request.file_range,
                str(path),
                path.stat().st_size,
                digest.hexdigest(),
            )
            self._record(request, result, "downloaded")
            return result
        except Exception as error:
            temp.unlink(missing_ok=True)
            self._record(
                request,
                FileResult(request.run_name, request.file_range, str(path)),
                "failed",
                repr(error),
            )
            raise

    def _record(
        self,
        request: FileRequest,
        result: FileResult,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with db() as (cursor, connection):
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
                    result.local_path,
                    result.size_bytes,
                    result.sha256,
                    status,
                    error_message,
                ),
            )
            connection.commit()


class GaiaImportOperation(GaiaSettings, BusinessOperation):
    def on_message(self, request: FileRequest) -> FileResult:
        count = 0
        batch: list[tuple] = []
        with db() as (cursor, connection):
            cursor.execute(
                f"DELETE FROM {SOURCE_TABLE} WHERE run_name = ? AND file_range = ?",
                (request.run_name, request.file_range),
            )
            connection.commit()

            with gzip.open(request.local_path, "rt", encoding="utf-8", newline="") as input_file:
                reader = csv.reader(line for line in input_file if line and line[0] != "#")
                next(reader, None)
                for row in reader:
                    if len(row) <= 16:
                        continue
                    stats = aggregate_source_flux(int(row[1]), row[11], row[16])
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
                    count += 1
                    if len(batch) >= self.db_batch_size:
                        self._insert(cursor, connection, batch)
                        batch.clear()
            if batch:
                self._insert(cursor, connection, batch)
        return FileResult(request.run_name, request.file_range, request.local_path, count=count)

    def _insert(self, cursor, connection, batch: list[tuple]) -> None:
        cursor.executemany(
            f"INSERT INTO {SOURCE_TABLE} "
            "(run_name,file_range,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        connection.commit()


class GaiaComputeOperation(GaiaSettings, BusinessOperation):
    def on_message(self, request: StateRequest) -> ComputeResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with db() as (cursor, connection):
            cursor.execute(f"DELETE FROM {CHANGE_TABLE} WHERE run_name = ?", (request.run_name,))
            cursor.execute(
                f"""
                INSERT INTO {CHANGE_TABLE}
                    (run_name,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change)
                SELECT run_name,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change
                FROM (
                    SELECT ? AS run_name, source_id, bp_min_flux, bp_max_flux, rp_min_flux, rp_max_flux,
                        CASE
                            WHEN bp_change IS NULL THEN rp_change
                            WHEN rp_change IS NULL THEN bp_change
                            WHEN bp_change > rp_change THEN bp_change
                            ELSE rp_change
                        END AS percentage_change
                    FROM (
                        SELECT source_id, bp_min_flux, bp_max_flux, rp_min_flux, rp_max_flux,
                            CASE WHEN bp_min_flux IS NULL OR bp_min_flux = 0
                                THEN NULL ELSE ((bp_max_flux - bp_min_flux) / bp_min_flux) * 100 END AS bp_change,
                            CASE WHEN rp_min_flux IS NULL OR rp_min_flux = 0
                                THEN NULL ELSE ((rp_max_flux - rp_min_flux) / rp_min_flux) * 100 END AS rp_change
                        FROM (
                            SELECT source_id,
                                MIN(bp_min_flux) AS bp_min_flux,
                                MAX(bp_max_flux) AS bp_max_flux,
                                MIN(rp_min_flux) AS rp_min_flux,
                                MAX(rp_max_flux) AS rp_max_flux
                            FROM {SOURCE_TABLE}
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
                f"SELECT COUNT(*) FROM {CHANGE_TABLE} WHERE run_name = ?",
                (request.run_name,),
            )
            count = int(cursor.fetchone()[0])
            self._write_results(cursor, request.run_name)
        return ComputeResult(request.run_name, count, str(self.results_file))

    def _write_results(self, cursor, run_name: str) -> None:
        cursor.execute(
            f"SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
            f"FROM {CHANGE_TABLE} WHERE run_name = ? ORDER BY source_id",
            (run_name,),
        )
        temp = self.results_file.with_suffix(".csv.tmp")
        with temp.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            while rows := cursor.fetchmany(1000):
                writer.writerows(rows)
        os.replace(temp, self.results_file)
