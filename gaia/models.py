from __future__ import annotations

from typing import Optional

from iris_persistence import Field, Index, Model


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
        indexes = [
            Index("SourceAggregateRunIdx", properties="run_name"),
            Index("SourceAggregateSourceIdx", properties="run_name,source_id"),
            Index(
                "SourceAggregateComputeCoverIdx",
                properties="run_name,source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux",
            ),
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
        indexes = [
            Index("PhotometryChangeRunIdx", properties="run_name"),
            Index("PhotometryChangeSourceIdx", properties="run_name,source_id"),
        ]


PERSISTENT_MODEL_SPECS = [
    "gaia.models:SourceFluxAggregate",
    "gaia.models:PhotometryChange",
]
