#!/bin/bash
# Setup script for macOS/Linux
set -eu
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [ -e ".venv" ]; then
    if [ ! -x ".venv/bin/python" ]; then
        echo "The existing .venv is incomplete or was created for another operating system." >&2
        echo "Rename .venv to an unused backup name, then rerun ./setup.sh." >&2
        exit 1
    fi
else
    python_command=""
    for candidate in python3.9 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
                "$candidate" core/runtime.py >/dev/null 2>&1; then
            python_command="$candidate"
            break
        fi
    done
    if [ -z "$python_command" ]; then
        echo "Python 3.9.12 or newer is required. Install Python from https://www.python.org/downloads/" >&2
        echo "Make python3.9 or a newer python3 available on PATH, then rerun ./setup.sh." >&2
        exit 1
    fi

    echo "Creating Python virtual environment..."
    "$python_command" -m venv .venv
fi

".venv/bin/python" core/runtime.py

echo "Installing dependencies..."
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

echo "Setup complete! You can now use run.sh to launch the application."
