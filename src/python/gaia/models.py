from __future__ import annotations

from typing import Optional

from iris_persistence import Field, Index, Model


class DownloadFile(Model):
    run_name: str = Field(required=True, max_length=128)
    file_range: str = Field(required=True, max_length=32)
    url: str = Field(required=True, max_length=512)
    local_path: str = Field(required=True, max_length=512)
    size_bytes: int = Field(required=True)
    sha256: str = Field(required=True, max_length=64)
    status: str = Field(required=True, max_length=32)
    error_message: Optional[str] = Field(default=None, max_length=2048)

    class Meta:
        classname = "GaiaDR3.DownloadFile"
        validate_on_init = False
        indexes = [
            Index("DownloadRunFileIdx", properties="run_name,file_range"),
            Index("DownloadStatusIdx", properties="run_name,status"),
        ]


class SourceFluxAggregate(Model):
    run_name: str = Field(required=True, max_length=128)
    file_range: str = Field(required=True, max_length=32)
    source_id: int = Field(required=True)
    bp_min_flux: Optional[float] = Field(default=None)
    bp_max_flux: Optional[float] = Field(default=None)
    rp_min_flux: Optional[float] = Field(default=None)
    rp_max_flux: Optional[float] = Field(default=None)

    class Meta:
        classname = "GaiaDR3.SourceFluxAggregate"
        validate_on_init = False
        indexes = [
            Index("SourceAggregateRunIdx", properties="run_name"),
            Index("SourceAggregateSourceIdx", properties="run_name,source_id"),
        ]


class PhotometryChange(Model):
    run_name: str = Field(required=True, max_length=128)
    source_id: int = Field(required=True)
    bp_min_flux: Optional[float] = Field(default=None)
    bp_max_flux: Optional[float] = Field(default=None)
    rp_min_flux: Optional[float] = Field(default=None)
    rp_max_flux: Optional[float] = Field(default=None)
    percentage_change: float = Field(required=True)

    class Meta:
        classname = "GaiaDR3.PhotometryChange"
        validate_on_init = False
        indexes = [
            Index("PhotometryChangeRunIdx", properties="run_name"),
            Index("PhotometryChangeSourceIdx", properties="run_name,source_id"),
        ]


PERSISTENT_MODEL_SPECS = [
    "src.python.gaia.models:DownloadFile",
    "src.python.gaia.models:SourceFluxAggregate",
    "src.python.gaia.models:PhotometryChange",
]
