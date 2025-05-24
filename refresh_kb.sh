#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV_PY="./venv/bin/python"

echo "[$(date)] Running site_scraper…"
"$VENV_PY" site_scraper.py

echo "[$(date)] Regenerating embeddings…"
"$VENV_PY" generate_embeddings.py
