from __future__ import annotations

import gzip
import shutil
from contextlib import suppress

import iris
import requests
from iop import BusinessOperation

from .messages import (
    ComputeRequest,
    ComputeResult,
    DownloadFileRequest,
    DownloadFileResult,
    ExportCsvRequest,
    ExportCsvResult,
    ImportFileRequest,
    ImportFileResult,
    PrepareRunRequest,
    PrepareRunResult,
)
from .exporting import write_results_csv
from .models import PhotometryChange, SourceFluxAggregate
from .parsing import source_flux_aggregate_batches
from .runtime import GaiaSettings

# iris-persistence creates these IRIS class-backed tables from models.py
SOURCE_TABLE = SourceFluxAggregate._classname
CHANGE_TABLE = PhotometryChange._classname

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

    def on_message(self, request: DownloadFileRequest) -> DownloadFileResult:
        path = self.download_file(request.file_range)

        # Reuse a file when a previous run already downloaded a readable gzip
        if path.exists():
            self._verify(path)
            return DownloadFileResult(request.run_name, request.file_range, str(path))

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
            return DownloadFileResult(request.run_name, request.file_range, str(path))
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _verify(self, path) -> None:
        # Reading one byte is enough to catch a corrupt or non-gzip file early
        with gzip.open(path, "rb") as compressed:
            compressed.read(1)


class GaiaDbOperation(GaiaSettings, BusinessOperation):
    # Business Operation: all IRIS DB work, routed by request message type
    def on_init(self) -> None:
        # DBAPI connections are created once per IoP operation worker
        self.db_connection = iris.dbapi.connect()
        self.db_cursor = self.db_connection.cursor()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def on_tear_down(self) -> None:
        # Close DBAPI resources when IoP stops this operation worker
        for handle_name in ("db_cursor", "db_connection"):
            handle = getattr(self, handle_name, None)
            if handle is not None:
                with suppress(Exception):
                    handle.close()

    def prepare_run(self, request: PrepareRunRequest) -> PrepareRunResult:
        # Clear old output markers and persistent rows for one run
        # Files are used as simple run markers for the challenge script
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

    def import_file(self, request: ImportFileRequest) -> ImportFileResult:
        # Import one downloaded archive into the source aggregate table
        # Make re-importing the same file idempotent for this run
        self.db_cursor.execute(
            f"DELETE FROM {SOURCE_TABLE} WHERE run_name = ? AND file_range = ?",
            (request.run_name, request.file_range),
        )
        self.db_connection.commit()

        # parsing.py yields ready-to-insert aggregate rows in DB-sized batches
        imported_rows = 0
        for batch in source_flux_aggregate_batches(
            run_name=request.run_name,
            file_range=request.file_range,
            local_path=request.local_path,
            batch_size=self.db_batch_size,
        ):
            imported_rows += len(batch)
            self._insert(batch)
        return ImportFileResult(request.run_name, request.file_range, imported_rows)

    def _insert(self, batch: list[tuple]) -> None:
        # executemany keeps import fast while the persistent table remains class-backed
        self.db_cursor.executemany(
            f"INSERT INTO {SOURCE_TABLE} "
            "(run_name,file_range,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        self.db_connection.commit()

    def compute_results(self, request: ComputeRequest) -> ComputeResult:
        # Compute final rows inside IRIS with one set-oriented SQL insert
        # Recompute is safe because previous final rows for this run are removed first
        # %NOCHECK %NOLOCK: safe because run rows were just deleted and this is the only writer
        # bp_change > 100 OR rp_change > 100 is equivalent to greatest(bp,rp) > 100 with NULLs
        self.db_cursor.execute(f"DELETE FROM {CHANGE_TABLE} WHERE run_name = ?", (request.run_name,))
        self.db_cursor.execute(
            f"""
            INSERT %NOCHECK %NOLOCK INTO {CHANGE_TABLE}
                (run_name,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change)
            SELECT ? AS run_name, source_id, bp_min_flux, bp_max_flux, rp_min_flux, rp_max_flux,
                CASE
                    WHEN bp_change IS NULL THEN rp_change
                    WHEN rp_change IS NULL THEN bp_change
                    WHEN bp_change > rp_change THEN bp_change
                    ELSE rp_change
                END AS percentage_change
            FROM (
                SELECT source_id,
                    MIN(bp_min_flux) AS bp_min_flux,
                    MAX(bp_max_flux) AS bp_max_flux,
                    MIN(rp_min_flux) AS rp_min_flux,
                    MAX(rp_max_flux) AS rp_max_flux,
                    CASE WHEN MIN(bp_min_flux) IS NULL OR MIN(bp_min_flux) = 0
                        THEN NULL ELSE ((MAX(bp_max_flux) - MIN(bp_min_flux)) / MIN(bp_min_flux)) * 100 END AS bp_change,
                    CASE WHEN MIN(rp_min_flux) IS NULL OR MIN(rp_min_flux) = 0
                        THEN NULL ELSE ((MAX(rp_max_flux) - MIN(rp_min_flux)) / MIN(rp_min_flux)) * 100 END AS rp_change
                FROM {SOURCE_TABLE}
                WHERE run_name = ?
                GROUP BY source_id
            ) aggregated
            WHERE bp_change > 100 OR rp_change > 100
            """,
            (request.run_name, request.run_name),
        )
        self.db_connection.commit()
        self.db_cursor.execute(
            f"SELECT COUNT(*) FROM {CHANGE_TABLE} WHERE run_name = ?",
            (request.run_name,),
        )
        count = int(self.db_cursor.fetchone()[0])
        return ComputeResult(request.run_name, count)

    def export_csv(self, request: ExportCsvRequest) -> ExportCsvResult:
        # Select final persistent rows; CSV formatting lives in exporting.py
        # The final file is sorted to make repeated runs easy to compare
        self.db_cursor.execute(
            f"SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
            f"FROM {CHANGE_TABLE} WHERE run_name = ? ORDER BY source_id",
            (request.run_name,),
        )
        write_results_csv(self.results_file, self._result_rows())
        return ExportCsvResult(request.run_name, request.result_count, str(self.results_file))

    def _result_rows(self):
        while rows := self.db_cursor.fetchmany(1000):
            yield from rows
