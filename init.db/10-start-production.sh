#!/usr/bin/env bash
set -e
cd /irisdev/app
iop --init
iop --migrate settings.py
iop --default GaiaDR3.Production
iop --start GaiaDR3.Production --detach
