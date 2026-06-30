#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rm -f output/results.csv output/results.csv.tmp output/results.done output/results.err output/results.lock
rm -rf output/downloads
docker compose up --build -d --force-recreate iris >&2
for _ in $(seq 1 1800);do
  [ -f output/results.done ]&&cat output/results.csv&&exit 0
  [ -f output/results.err ]&&cat output/results.err >&2&&exit 1
  sleep 2
done
docker compose logs iris >&2
exit 1
