#!/usr/bin/env bash
# Launch the annotator using the project virtualenv.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install PySide6-Essentials
fi

exec ./.venv/bin/python -m annotator "$@"
