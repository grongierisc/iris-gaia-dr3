from __future__ import annotations

from settings import FIRST_20_FILE_BOUNDARIES, GAIA_SETTINGS, PRODUCTIONS
from gaia.runtime import GaiaSettings


def test_settings_module_owns_gaia_runtime_config():
    assert GAIA_SETTINGS["FileBoundaries"] == ",".join(FIRST_20_FILE_BOUNDARIES)
    assert GAIA_SETTINGS["ArchiveUrlTemplate"].endswith("EpochPhotometry_%s.csv.gz")


def test_file_boundaries_expand_to_file_ranges():
    settings = GaiaSettings()
    settings.FileBoundaries = "000000,003112,005264"
    assert settings.file_ranges == ("000000-003111", "003112-005263")


def test_production_passes_gaia_settings_to_components():
    prod = PRODUCTIONS[0]
    for item in prod.items:
        for name, value in GAIA_SETTINGS.items():
            assert item.host_settings[name] == value
