#!/usr/bin/env sh
set -eu
python -m backend.app.cli migrate
if [ "${DEMO_MODE:-true}" = "true" ]; then
  python -m backend.app.cli seed
fi
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
