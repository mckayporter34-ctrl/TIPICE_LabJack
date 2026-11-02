#!/bin/bash
# Run script for macOS/Linux
set -eu
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Please run ./setup.sh first." >&2
    exit 1
fi

".venv/bin/python" core/runtime.py

echo "Launching application..."
exec ".venv/bin/python" main.py
