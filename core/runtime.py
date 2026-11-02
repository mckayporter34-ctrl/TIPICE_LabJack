"""Python version check shared by setup scripts and application entry points.

Keep this module free of application dependencies and newer Python syntax so an
older interpreter can display the version instructions before importing the GUI.
"""

import sys


MINIMUM_PYTHON = (3, 9, 12)


def require_python():
    """Support the lab's Python 3.9.12 baseline and newer Python versions."""
    if sys.version_info[:3] < MINIMUM_PYTHON:
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(
            "TIPICE LabJack requires Python 3.9.12 or newer; found Python {}.\n"
            "Install Python 3.9.12 or newer. If .venv already exists, rename it to an unused "
            "backup name, then run setup.bat (Windows) or ./setup.sh (macOS/Linux)."
            .format(current)
        )


if __name__ == "__main__":
    require_python()
