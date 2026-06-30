from __future__ import annotations

import os

from pathlib import Path

from src.python.gaia.production import build_production

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

# Try to write to the output directory to ensure it is writable before starting the production, if not, use a temporary directory
try:
    Path(GAIA_SETTINGS["OutputDir"]).mkdir(parents=True, exist_ok=True)
    test_file = Path(GAIA_SETTINGS["OutputDir"]) / "test_write.tmp"
    with test_file.open("w") as f:
        f.write("test")
    test_file.unlink()
except Exception:
    import tempfile

    temp_dir = tempfile.mkdtemp(prefix="gaia_output_")
    GAIA_SETTINGS["OutputDir"] = temp_dir
    print(f"Warning: Could not write to the specified output directory. Using temporary directory: {temp_dir}")

prod = build_production(
    GAIA_SETTINGS,
    actor_pool_size=int(os.getenv("GAIA_ACTOR_POOL", "8")),
    download_pool_size=int(os.getenv("GAIA_DOWNLOAD_POOL", "8")),
    import_pool_size=int(os.getenv("GAIA_IMPORT_POOL", "8")),
)

PRODUCTIONS = [prod]
