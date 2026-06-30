from __future__ import annotations

import csv

RESULT_HEADER = (
    "source_id",
    "bp_min_flux",
    "bp_max_flux",
    "rp_min_flux",
    "rp_max_flux",
    "percentage_change",
)


def write_results_csv(path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(RESULT_HEADER)
        writer.writerows(rows)
