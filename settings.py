from __future__ import annotations

import os

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

prod = build_production(
    GAIA_SETTINGS,
    actor_pool_size=int(os.getenv("GAIA_ACTOR_POOL", "8")),
    download_pool_size=int(os.getenv("GAIA_DOWNLOAD_POOL", "8")),
    import_pool_size=int(os.getenv("GAIA_IMPORT_POOL", "8")),
)

PRODUCTIONS = [prod]
