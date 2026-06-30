from __future__ import annotations

import os
from pathlib import Path

ARCHIVE_URL_TEMPLATE = (
    "https://cdn.gea.esac.esa.int/Gaia/gdr3/Photometry/epoch_photometry/"
    "EpochPhotometry_%s.csv.gz"
)

FIRST_20_FILE_RANGES = [
    "000000-003111",
    "003112-005263",
    "005264-006601",
    "006602-007952",
    "007953-010234",
    "010235-012597",
    "012598-014045",
    "014046-015369",
    "015370-016240",
    "016241-017018",
    "017019-017658",
    "017659-018028",
    "018029-018472",
    "018473-019161",
    "019162-019657",
    "019658-020091",
    "020092-020493",
    "020494-020747",
    "020748-020984",
    "020985-021233",
]

OUTPUT_DIR = Path("/irisdev/app/output")
DOWNLOAD_DIR = OUTPUT_DIR / "downloads"
RESULTS_FILE = OUTPUT_DIR / "results.csv"
DONE_FILE = OUTPUT_DIR / "results.done"
ERROR_FILE = OUTPUT_DIR / "results.err"
LOCK_FILE = OUTPUT_DIR / "results.lock"

DOWNLOAD_POOL_SIZE = int(os.getenv("GAIA_DOWNLOAD_POOL", "4"))
IMPORT_POOL_SIZE = int(os.getenv("GAIA_IMPORT_POOL", "4"))
DB_BATCH_SIZE = int(os.getenv("GAIA_DB_BATCH_SIZE", "10000"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("GAIA_REQUEST_TIMEOUT_SECONDS", "1800"))


def archive_url(file_range: str) -> str:
    return ARCHIVE_URL_TEMPLATE % file_range


def archive_file_name(file_range: str) -> str:
    return f"EpochPhotometry_{file_range}.csv.gz"
