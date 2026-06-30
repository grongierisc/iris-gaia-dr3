#!/usr/bin/env bash
set -e
cd /irisdev/app
iop --init
PYTHONPATH=/irisdev/app iris-persistence apply \
  src.python.gaia.models:SourceFluxAggregate \
  src.python.gaia.models:PhotometryChange \
  --to gaia-dr3-persistence-v1 \
  --yes
iop --migrate settings.py
iop --default GaiaDR3.Production
iop --start GaiaDR3.Production --detach
