#!/usr/bin/env bash
set -e
cd /irisdev/app
iop --init
iris-persistence apply \
  gaia.models:SourceFluxAggregate \
  gaia.models:PhotometryChange \
  --backup-dir /tmp/iris/app/persistence-backup \
  --to gaia-dr3-persistence-v1 \
  --yes
iop --migrate settings.py
iop --default GaiaDR3.Production
iop --start GaiaDR3.Production --detach
