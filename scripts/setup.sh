#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
.venv/bin/python -m pip install -e . --no-deps
