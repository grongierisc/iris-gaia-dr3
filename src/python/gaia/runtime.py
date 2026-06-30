from __future__ import annotations

from typing import Annotated

from pathlib import Path

from iop import Setting


class GaiaSettings:
    ArchiveUrlTemplate: Annotated[str, Setting(data_type=str, required=True, category="Gaia")]
    FileBoundaries: Annotated[str, Setting(data_type=str, required=True, category="Gaia")]
    OutputDir: Annotated[str, Setting(data_type=str, required=True, category="Gaia")]
    RequestTimeoutSeconds: Annotated[int, Setting(data_type=int, required=True, category="Gaia")]
    HttpTimeoutSeconds: Annotated[int, Setting(data_type=int, required=True, category="Gaia")]
    DbBatchSize: Annotated[int, Setting(data_type=int, required=True, category="Gaia")]

    @property
    def output_dir(self) -> Path:
        return Path(str(self.OutputDir))

    @property
    def download_dir(self) -> Path:
        return self.output_dir / "downloads"

    @property
    def results_file(self) -> Path:
        return self.output_dir / "results.csv"

    @property
    def done_file(self) -> Path:
        return self.output_dir / "results.done"

    @property
    def error_file(self) -> Path:
        return self.output_dir / "results.err"

    @property
    def lock_file(self) -> Path:
        return self.output_dir / "results.lock"

    @property
    def file_ranges(self) -> tuple[str, ...]:
        values = [int(item) for item in str(self.FileBoundaries).split(",") if item.strip()]
        return tuple(f"{start:06d}-{end - 1:06d}" for start, end in zip(values, values[1:]))

    @property
    def request_timeout(self) -> int:
        return int(self.RequestTimeoutSeconds)

    @property
    def http_timeout(self) -> int:
        return int(self.HttpTimeoutSeconds)

    @property
    def db_batch_size(self) -> int:
        return int(self.DbBatchSize)

    def archive_url(self, file_range: str) -> str:
        return str(self.ArchiveUrlTemplate) % file_range

    def archive_file_name(self, file_range: str) -> str:
        return f"EpochPhotometry_{file_range}.csv.gz"

    def download_file(self, file_range: str) -> Path:
        return self.download_dir / self.archive_file_name(file_range)
