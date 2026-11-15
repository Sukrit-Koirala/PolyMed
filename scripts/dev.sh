#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
(cd frontend && npm ci --no-audit --no-fund)
if [ -f .env ]; then set -a; . ./.env; set +a; fi
python -m backend.app.cli migrate
python -m backend.app.cli seed
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM
cd frontend
npm run dev
