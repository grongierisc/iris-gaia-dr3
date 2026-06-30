#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
logs_pid=""
cleanup() {
  [ -n "$logs_pid" ] || return 0
  kill "$logs_pid" >/dev/null 2>&1 || true
  wait "$logs_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker compose down --remove-orphans >&2 || true
rm -f output/results.csv output/results.done output/results.err output/results.lock
rm -rf output/downloads
docker compose up --build -d --force-recreate iris >&2
docker compose logs -f iris >&2 &
logs_pid=$!
for _ in $(seq 1 1800);do
  [ -f output/results.done ]&&cat output/results.csv&&exit 0
  [ -f output/results.err ]&&cat output/results.err >&2&&exit 1
  sleep 2
done
exit 1
