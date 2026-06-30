from __future__ import annotations

import csv
import gzip
import os
from contextlib import contextmanager, suppress

import iris
import requests
from iop import BusinessOperation

from .messages import ComputeResult, FileRequest, FileResult, GaiaBenchmarkRequest
from .models import PhotometryChange, SourceFluxAggregate
from .parsing import source_flux_aggregate_batches
from .runtime import GaiaSettings

# iris-persistence creates these IRIS class-backed tables from models.py
SOURCE_TABLE = SourceFluxAggregate._classname
CHANGE_TABLE = PhotometryChange._classname

# Downloads are streamed, so large Gaia files are never loaded fully in memory
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
RESULT_HEADER = (
    "source_id",
    "bp_min_flux",
    "bp_max_flux",
    "rp_min_flux",
    "rp_max_flux",
    "percentage_change",
)


@contextmanager
def db():
    # Small DBAPI helper used by operations that need direct SQL speed
    connection = iris.dbapi.connect()
    cursor = connection.cursor()
    try:
        yield cursor, connection
    finally:
        for handle in (cursor, connection):
            with suppress(Exception):
                handle.close()


class GaiaDownloadOperation(GaiaSettings, BusinessOperation):
    # Business Operation: one request downloads one Gaia .csv.gz archive
    def on_message(self, request: FileRequest) -> FileResult:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        path = self.download_file(request.file_range)
        temp = path.with_suffix(path.suffix + ".tmp")

        # Reuse a file when a previous run already downloaded a readable gzip
        if path.exists():
            self._verify(path)
            return FileResult(request.run_name, request.file_range, str(path))

        temp.unlink(missing_ok=True)
        try:
            # Write to a temporary file first, then atomically rename on success
            with requests.get(request.url, stream=True, timeout=self.http_timeout) as response:
                response.raise_for_status()
                with temp.open("wb") as output:
                    for chunk in response.iter_content(DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            output.write(chunk)
            self._verify(temp)
            os.replace(temp, path)
            return FileResult(request.run_name, request.file_range, str(path))
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def _verify(self, path) -> None:
        # Reading one byte is enough to catch a corrupt or non-gzip file early
        with gzip.open(path, "rb") as compressed:
            compressed.read(1)


class GaiaImportOperation(GaiaSettings, BusinessOperation):
    # Business Operation: one request imports one downloaded archive
    def on_message(self, request: FileRequest) -> FileResult:
        with db() as (cursor, connection):
            # Make re-importing the same file idempotent for this run
            cursor.execute(
                f"DELETE FROM {SOURCE_TABLE} WHERE run_name = ? AND file_range = ?",
                (request.run_name, request.file_range),
            )
            connection.commit()

            # parsing.py yields ready-to-insert aggregate rows in DB-sized batches
            for batch in source_flux_aggregate_batches(
                run_name=request.run_name,
                file_range=request.file_range,
                local_path=request.local_path,
                batch_size=self.db_batch_size,
            ):
                self._insert(cursor, connection, batch)
        return FileResult(request.run_name, request.file_range, request.local_path)

    def _insert(self, cursor, connection, batch: list[tuple]) -> None:
        # executemany keeps import fast while the persistent table remains class-backed
        cursor.executemany(
            f"INSERT INTO {SOURCE_TABLE} "
            "(run_name,file_range,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        connection.commit()


class GaiaComputeOperation(GaiaSettings, BusinessOperation):
    # Business Operation: compute final rows inside IRIS with one set-oriented SQL insert
    def on_message(self, request: GaiaBenchmarkRequest) -> ComputeResult:
        with db() as (cursor, connection):
            # Recompute is safe because previous final rows for this run are removed first
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
        return ComputeResult(request.run_name, count, "")


class GaiaCsvExportOperation(GaiaSettings, BusinessOperation):
    # Business Operation: export final persistent rows to the challenge CSV file
    def on_message(self, request: ComputeResult) -> ComputeResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temp = self.results_file.with_suffix(".csv.tmp")
        with db() as (cursor, _):
            # The final file is sorted to make repeated runs easy to compare
            cursor.execute(
                f"SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
                f"FROM {CHANGE_TABLE} WHERE run_name = ? ORDER BY source_id",
                (request.run_name,),
            )
            with temp.open("w", newline="", encoding="utf-8") as output:
                writer = csv.writer(output)
                # The challenge output starts with one header row
                writer.writerow(RESULT_HEADER)
                while rows := cursor.fetchmany(1000):
                    writer.writerows(rows)
        os.replace(temp, self.results_file)
        return ComputeResult(request.run_name, request.result_count, str(self.results_file))
