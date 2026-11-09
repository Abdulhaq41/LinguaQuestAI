#!/usr/bin/env bash
set -euo pipefail
cd /app
if [ -z "${WEBAPP_URL:-}" ]; then
    export WEBAPP_URL="${RENDER_EXTERNAL_URL:?Set WEBAPP_URL or use Render external URL}"
fi
python -m alembic upgrade head
exec python -m uvicorn services.api.hosted:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
