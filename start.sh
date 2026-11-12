#!/usr/bin/env sh
# Start QE Connect on macOS or Linux. Needs Python 3.10 or newer.
set -e
cd "$(dirname "$0")"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "QE Connect needs Python 3.10 or newer: https://www.python.org/downloads/"; exit 1; fi
if [ ! -x .venv/bin/python ]; then echo "Creating QE Connect's Python environment..."; "$PY" -m venv .venv; fi
LOCK=backend/requirements.lock
if grep -qi postgresql .env 2>/dev/null; then LOCK=backend/requirements-postgres.lock; fi
if ! cmp -s "$LOCK" .venv/installed.lock; then
  echo "Installing QE Connect's components. The first run takes a minute or two..."
  .venv/bin/python -m pip install --disable-pip-version-check -q --require-hashes -r "$LOCK"
  cp "$LOCK" .venv/installed.lock
fi
cd backend
exec ../.venv/bin/python -m app --open "$@"
