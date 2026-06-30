from __future__ import annotations

from dataclasses import is_dataclass
from typing import get_type_hints

from iop import Message

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
from gaia.models import (
    PERSISTENT_MODEL_SPECS,
    PhotometryChange,
    SourceFluxAggregate,
)

MESSAGE_TYPES = [
    GaiaBenchmarkRequest,
    PrepareRunRequest,
    PrepareRunResult,
    DownloadFileRequest,
    DownloadFileResult,
    ImportFileRequest,
    ImportFileResult,
    ComputeRequest,
    ComputeResult,
    ExportCsvRequest,
    ExportCsvResult,
]


def test_internal_messages_are_dataclass_iop_messages():
    for message_type in MESSAGE_TYPES:
        assert is_dataclass(message_type)
        assert issubclass(message_type, Message)


def test_internal_message_fields_are_primitive_serialization_contracts():
    allowed_types = {str, int}
    for message_type in MESSAGE_TYPES:
        declared_fields = set(message_type.__dataclass_fields__) - {"_iris_id"}
        hints = get_type_hints(message_type)
        for field_name in declared_fields:
            field_type = hints[field_name]
            assert field_type in allowed_types


def test_message_construction_uses_primitive_values():
    request = DownloadFileRequest(
        run_name="gaia-dr3-first-20",
        file_range="000000-003111",
        url="https://example.invalid/EpochPhotometry_000000-003111.csv.gz",
    )
    import_request = ImportFileRequest(
        run_name=request.run_name,
        file_range=request.file_range,
        local_path="/tmp/EpochPhotometry_000000-003111.csv.gz",
    )

    assert request.run_name == "gaia-dr3-first-20"
    assert request.file_range == "000000-003111"
    assert request.url.endswith(".csv.gz")
    assert import_request.local_path.endswith(".csv.gz")


def test_persistent_models_use_expected_iris_class_names():
    assert SourceFluxAggregate._classname == "GaiaDR3.SourceFluxAggregate"
    assert PhotometryChange._classname == "GaiaDR3.PhotometryChange"
    assert PERSISTENT_MODEL_SPECS == [
        "gaia.models:SourceFluxAggregate",
        "gaia.models:PhotometryChange",
    ]
