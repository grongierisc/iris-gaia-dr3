from __future__ import annotations

import os

from gaia.production import build_production

def _check_folder_writable(folder: str) -> bool:
    """Check if a folder is writable by attempting to create and delete a temporary file."""
    try:
        test_file = os.path.join(folder, "temp_test_file")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False

ARCHIVE_URL_TEMPLATE = (
    "https://cdn.gea.esac.esa.int/Gaia/gdr3/Photometry/epoch_photometry/"
    "EpochPhotometry_%s.csv.gz"
)
FIRST_20_FILE_BOUNDARIES = [
    "000000",
    "003112",
    "005264",
    "006602",
    "007953",
    "010235",
    "012598",
    "014046",
    "015370",
    "016241",
    "017019",
    "017659",
    "018029",
    "018473",
    "019162",
    "019658",
    "020092",
    "020494",
    "020748",
    "020985",
    "021234",
]

GAIA_SETTINGS = {
    "ArchiveUrlTemplate": ARCHIVE_URL_TEMPLATE,
    "FileBoundaries": ",".join(FIRST_20_FILE_BOUNDARIES),
    "OutputDir": os.getenv("GAIA_OUTPUT_DIR", "/irisdev/app/output"),
    "RequestTimeoutSeconds": int(os.getenv("GAIA_REQUEST_TIMEOUT_SECONDS", "1800")),
    "HttpTimeoutSeconds": int(os.getenv("GAIA_HTTP_TIMEOUT_SECONDS", "120")),
    "DbBatchSize": int(os.getenv("GAIA_DB_BATCH_SIZE", "10000")),
}

# Check if the output directory is writable, if not, use a temporary directory
if not _check_folder_writable(GAIA_SETTINGS["OutputDir"]):
    GAIA_SETTINGS["OutputDir"] = os.getenv("GAIA_OUTPUT_DIR", "/tmp/iris/app/output")

prod = build_production(
    GAIA_SETTINGS,
    actor_pool_size=int(os.getenv("GAIA_ACTOR_POOL", "8")),
    download_pool_size=int(os.getenv("GAIA_DOWNLOAD_POOL", "8")),
    import_pool_size=int(os.getenv("GAIA_IMPORT_POOL", "8")),
)

PRODUCTIONS = [prod]
