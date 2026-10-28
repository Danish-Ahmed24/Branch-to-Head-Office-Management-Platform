#!/usr/bin/env bash
set -euo pipefail
cd /workspace/Branch-to-Head-Office-Management-Platform
python -m venv /workspace/.venvs/shiplens
/workspace/.venvs/shiplens/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
npm --prefix frontend ci --cache /tmp/shiplens-npm-cache
npm --prefix frontend run build
python scripts/cloud_build.py
