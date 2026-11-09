#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload &
api_pid=$!
cleanup() { kill "$api_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
cd apps/miniapp
npm run dev
