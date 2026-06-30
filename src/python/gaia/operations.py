from __future__ import annotations

import csv
import gzip
import io
import os
import urllib.request

import iris
from iop import BusinessOperation

from .config import ARCHIVE_URL_TEMPLATE, DONE_FILE, ERROR_FILE, FIRST_20_FILE_RANGES, OUTPUT_DIR, RESULTS_FILE
from .messages import GaiaBenchmarkRequest
from .parsing import flux_rows, valid_flux_values


class GaiaSqlOperation(BusinessOperation):
    def on_message(self, request: GaiaBenchmarkRequest):
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            connection = iris.dbapi.connect()
            cursor = connection.cursor()

            self._replace_schema(cursor)
            self._load_flux_rows(cursor, connection)
            self._calculate_results(cursor, connection)
            self._write_results(cursor)

            DONE_FILE.touch()
        except Exception as error:
            ERROR_FILE.write_text(repr(error), encoding="utf-8")
            raise

        return request

    def _replace_schema(self, cursor) -> None:
        for table_name in ("GaiaDR3.PhotometryFlux", "GaiaDR3.PhotometryChange"):
            try:
                cursor.execute(f"DROP TABLE {table_name}")
            except Exception:
                pass

        cursor.execute(
            "CREATE TABLE GaiaDR3.PhotometryFlux("
            "source_id BIGINT,"
            "band VARCHAR(2),"
            "flux DOUBLE)"
        )
        cursor.execute(
            "CREATE TABLE GaiaDR3.PhotometryChange("
            "source_id BIGINT,"
            "bp_min_flux DOUBLE,"
            "bp_max_flux DOUBLE,"
            "rp_min_flux DOUBLE,"
            "rp_max_flux DOUBLE,"
            "percentage_change DOUBLE)"
        )

    def _load_flux_rows(self, cursor, connection) -> None:
        insert_sql = "INSERT INTO GaiaDR3.PhotometryFlux VALUES(?,?,?)"
        batch: list[tuple[int, str, float]] = []

        for file_range in FIRST_20_FILE_RANGES:
            with urllib.request.urlopen(ARCHIVE_URL_TEMPLATE % file_range, timeout=120) as response:
                with gzip.GzipFile(fileobj=response) as compressed_file:
                    text_file = io.TextIOWrapper(compressed_file, encoding="utf-8")
                    reader = csv.reader(line for line in text_file if line and line[0] != "#")
                    next(reader)

                    for row in reader:
                        source_id = int(row[1])
                        batch.extend(flux_rows(source_id, "BP", valid_flux_values(row[11])))
                        batch.extend(flux_rows(source_id, "RP", valid_flux_values(row[16])))

                        if len(batch) >= 10_000:
                            cursor.executemany(insert_sql, batch)
                            connection.commit()
                            batch.clear()

        if batch:
            cursor.executemany(insert_sql, batch)
            connection.commit()

        cursor.execute("CREATE INDEX PhotometryFluxIdx ON GaiaDR3.PhotometryFlux(source_id,band)")
        connection.commit()

    def _calculate_results(self, cursor, connection) -> None:
        cursor.execute(
            """
            INSERT INTO GaiaDR3.PhotometryChange
            SELECT
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
                        MIN(CASE WHEN band = 'BP' THEN flux END) AS bp_min_flux,
                        MAX(CASE WHEN band = 'BP' THEN flux END) AS bp_max_flux,
                        MIN(CASE WHEN band = 'RP' THEN flux END) AS rp_min_flux,
                        MAX(CASE WHEN band = 'RP' THEN flux END) AS rp_max_flux
                    FROM GaiaDR3.PhotometryFlux
                    GROUP BY source_id
                )
            )
            """
        )
        cursor.execute(
            "DELETE FROM GaiaDR3.PhotometryChange "
            "WHERE percentage_change IS NULL OR percentage_change <= 100"
        )
        connection.commit()

    def _write_results(self, cursor) -> None:
        cursor.execute(
            "SELECT source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change "
            "FROM GaiaDR3.PhotometryChange ORDER BY source_id"
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
