#!/usr/bin/env bash
# Runs the API (Django, :8000) and the web app (Next.js, :3000) together.
# Ctrl+C stops both.
#
#   ./dev.sh            start both
#   ./dev.sh --setup    first apply migrations and seed the dropdown presets, then start both
#
# Output from each server is prefixed [api] or [web].

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

PYTHON="$ROOT/backend/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "No virtualenv at backend/.venv. Create it first:" >&2
  echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [ ! -d "$ROOT/web/node_modules" ]; then
  echo "Web dependencies are missing. Run:  cd web && npm install" >&2
  exit 1
fi

# The PDF engine (WeasyPrint) needs Homebrew's libraries, which macOS doesn't
# search by default. (This is also why the server must not be started through
# `nohup` or similar: macOS strips this variable from protected programs.)
if command -v brew >/dev/null 2>&1; then
  export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
fi

for port in "$API_PORT" "$WEB_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop whatever is using it, or set API_PORT / WEB_PORT." >&2
    exit 1
  fi
done

if [ "${1:-}" = "--setup" ]; then
  echo "Applying migrations and seeding presets..."
  (cd "$ROOT/backend" && "$PYTHON" manage.py migrate && "$PYTHON" manage.py seed_presets) || exit 1
fi

# Job control gives each server its own process group, so stopping one stops
# everything under it (the reloader, npm, node), not just the shell around it.
set -m
pids=()
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping..."
  for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null; done
  sleep 1
  # Whatever is still holding the two ports is ours: they were free when we started.
  for port in "$API_PORT" "$WEB_PORT"; do
    lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null
  done
  wait 2>/dev/null
}
trap cleanup INT TERM EXIT

prefix() { sed -u "s/^/[$1] /"; }

(cd "$ROOT/backend" && exec "$PYTHON" manage.py runserver "$API_PORT" 2>&1 | prefix api) &
pids+=($!)
(cd "$ROOT/web" && exec npm run dev -- --port "$WEB_PORT" 2>&1 | prefix web) &
pids+=($!)

echo "API  http://localhost:$API_PORT"
echo "Web  http://localhost:$WEB_PORT   (Ctrl+C stops both)"

# Stop everything as soon as either server exits.
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do sleep 1; done
