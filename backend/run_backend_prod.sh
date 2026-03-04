#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQ_FILE="$ROOT_DIR/backend/requirements.txt"
PORT="${PORT:-5000}"
WORKERS="${WEB_CONCURRENCY:-2}"
THREADS="${GUNICORN_THREADS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-180}"

cd "$ROOT_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[backend] Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
export PATH="$VENV_DIR/bin:$PATH"

for bin_dir in /opt/homebrew/bin /usr/local/bin; do
  if [[ -d "$bin_dir" ]]; then
    export PATH="$bin_dir:$PATH"
  fi
done

if ! "$VENV_PY" -c "import flask, yt_dlp, gunicorn" >/dev/null 2>&1; then
  echo "[backend] Installing backend Python dependencies"
  "$VENV_PY" -m pip install -r "$REQ_FILE"
fi

exec "$VENV_DIR/bin/gunicorn" \
  --workers "$WORKERS" \
  --threads "$THREADS" \
  --worker-class gthread \
  --bind "0.0.0.0:${PORT}" \
  --timeout "$TIMEOUT" \
  --access-logfile - \
  --error-logfile - \
  backend.wsgi:app
