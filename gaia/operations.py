from __future__ import annotations

import csv
import gzip
import shutil
from contextlib import suppress

import iris
import requests
from iop import BusinessOperation

from .messages import ComputeResult, FileRequest, FileResult, GaiaBenchmarkRequest, PrepareRunResult
from .models import PhotometryChange, SourceFluxAggregate
from .parsing import source_flux_aggregate_batches
from .runtime import GaiaSettings

# iris-persistence creates these IRIS class-backed tables from models.py
SOURCE_TABLE = SourceFluxAggregate._classname
CHANGE_TABLE = PhotometryChange._classname

RESULT_HEADER = (
    "source_id",
    "bp_min_flux",
    "bp_max_flux",
    "rp_min_flux",
    "rp_max_flux",
    "percentage_change",
)


class GaiaDownloadOperation(GaiaSettings, BusinessOperation):
    # Business Operation: one request downloads one Gaia .csv.gz archive
    def on_init(self) -> None:
        # on_init is called once when IoP starts this operation worker
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.http_session = requests.Session()

    def on_tear_down(self) -> None:
        # Close the HTTP connection pool when IoP stops this operation worker
        session = getattr(self, "http_session", None)
        if session is not None:
            session.close()

    def on_message(self, request: FileRequest) -> FileResult:
        path = self.download_file(request.file_range)

        # Reuse a file when a previous run already downloaded a readable gzip
        if path.exists():
            self._verify(path)
            return FileResult(request.run_name, request.file_range, str(path))

        try:
            with self.http_session.get(
                request.url,
                stream=True,
                timeout=self.http_timeout,
            ) as response:
                response.raise_for_status()
                with path.open("wb") as output:
                    shutil.copyfileobj(response.raw, output)
            self._verify(path)
            return FileResult(request.run_name, request.file_range, str(path))
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _verify(self, path) -> None:
        # Reading one byte is enough to catch a corrupt or non-gzip file early
        with gzip.open(path, "rb") as compressed:
            compressed.read(1)


class GaiaDbOperation(GaiaSettings):
    def on_init(self) -> None:
        # DBAPI connections are created once per IoP operation worker
        self.db_connection = iris.dbapi.connect()
        self.db_cursor = self.db_connection.cursor()

    def on_tear_down(self) -> None:
        # Close DBAPI resources when IoP stops this operation worker
        for handle_name in ("db_cursor", "db_connection"):
            handle = getattr(self, handle_name, None)
            if handle is not None:
                with suppress(Exception):
                    handle.close()


class GaiaPrepareRunOperation(GaiaDbOperation, BusinessOperation):
    # Business Operation: clear old output markers and persistent rows for one run
    def on_message(self, request: GaiaBenchmarkRequest) -> PrepareRunResult:
        # Files are used as simple run markers for the challenge script
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        for marker in (
            self.done_file,
            self.error_file,
            self.results_file,
        ):
            marker.unlink(missing_ok=True)

        # Persistent rows are scoped by run_name, so deleting the current run is repeatable
        for table in (SOURCE_TABLE, CHANGE_TABLE):
            self.db_cursor.execute(f"DELETE FROM {table} WHERE run_name = ?", (request.run_name,))
        self.db_connection.commit()
        return PrepareRunResult(request.run_name)


class GaiaImportOperation(GaiaDbOperation, BusinessOperation):
    # Business Operation: one request imports one downloaded archive
    def on_message(self, request: FileRequest) -> FileResult:
        # Make re-importing the same file idempotent for this run
        self.db_cursor.execute(
            f"DELETE FROM {SOURCE_TABLE} WHERE run_name = ? AND file_range = ?",
            (request.run_name, request.file_range),
        )
        self.db_connection.commit()

        # parsing.py yields ready-to-insert aggregate rows in DB-sized batches
        for batch in source_flux_aggregate_batches(
            run_name=request.run_name,
            file_range=request.file_range,
            local_path=request.local_path,
            batch_size=self.db_batch_size,
        ):
            self._insert(batch)
        return FileResult(request.run_name, request.file_range, request.local_path)

    def _insert(self, batch: list[tuple]) -> None:
        # executemany keeps import fast while the persistent table remains class-backed
        self.db_cursor.executemany(
            f"INSERT INTO {SOURCE_TABLE} "
            "(run_name,file_range,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        self.db_connection.commit()


class GaiaComputeOperation(GaiaDbOperation, BusinessOperation):
    # Business Operation: compute final rows inside IRIS with one set-oriented SQL insert
    def on_message(self, request: GaiaBenchmarkRequest) -> ComputeResult:
        # Recompute is safe because previous final rows for this run are removed first
        self.db_cursor.execute(f"DELETE FROM {CHANGE_TABLE} WHERE run_name = ?", (request.run_name,))
        self.db_cursor.execute(
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
        self.db_connection.commit()
        self.db_cursor.execute(
            f"SELECT COUNT(*) FROM {CHANGE_TABLE} WHERE run_name = ?",
            (request.run_name,),
        )
        count = int(self.db_cursor.fetchone()[0])
        return ComputeResult(request.run_name, count, "")


class GaiaCsvExportOperation(GaiaDbOperation, BusinessOperation):
    # Business Operation: export final persistent rows to the challenge CSV file
    def on_init(self) -> None:
        super().on_init()
        # The output directory is prepared once when the worker starts
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def on_message(self, request: ComputeResult) -> ComputeResult:
        # The final file is sorted to make repeated runs easy to compare
        self.db_cursor.execute(
            f"SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
            f"FROM {CHANGE_TABLE} WHERE run_name = ? ORDER BY source_id",
            (request.run_name,),
        )
        with self.results_file.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            # The challenge output starts with one header row
            writer.writerow(RESULT_HEADER)
            while rows := self.db_cursor.fetchmany(1000):
                writer.writerows(rows)
        return ComputeResult(request.run_name, request.result_count, str(self.results_file))
