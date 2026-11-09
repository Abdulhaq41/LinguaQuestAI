#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
.venv/bin/alembic upgrade head
(cd apps/miniapp && npm ci && npm run build)
