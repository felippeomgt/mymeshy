#!/usr/bin/env bash
# Start backend (port 8420) and frontend dev server (port 5173).
# Backend runs in the background; Ctrl-C stops both. (Windows: scripts\dev.ps1.)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Backend:  http://127.0.0.1:8420  (API docs: /docs)"
echo "Frontend: http://localhost:5173"

"$root/.venv/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8420 --app-dir "$root/backend" &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

( cd "$root/frontend" && npm run dev )
