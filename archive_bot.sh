#!/usr/bin/env bash
set -euo pipefail

cd /root
ARCHIVE="aktuba_bot_FULL_$(date +%Y%m%d_%H%M).zip"

zip -r "$ARCHIVE" aktuba_bot \
  -x "**/venv/*" \
  -x "**/.venv/*" \
  -x "**/__pycache__/*" \
  -x "**/*.pyc" \
  -x "**/*.pyo" \
  -x "**/.pytest_cache/*" \
  -x "**/.mypy_cache/*" \
  -x "**/.ruff_cache/*" \
  -x "**/.cache/*" \
  -x "**/.git/*" \
  -x "**/*.log" \
  -x "**/*.sqlite" \
  -x "**/*.db" \
  -x "**/.env" \
  -x "**/.env.*" \
  -x "**/downloads/*" \
  -x "**/uploads/*" \
  -x "**/media/*" \
  -x "**/reports_pdf/*"

echo "OK: $ARCHIVE"
ls -lh "$ARCHIVE"
