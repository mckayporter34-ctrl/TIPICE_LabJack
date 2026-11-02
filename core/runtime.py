"""Python version check shared by setup scripts and application entry points.

Keep this module free of application dependencies and newer Python syntax so an
older interpreter can display the upgrade instructions before importing the GUI.
"""

import sys


REQUIRED_PYTHON = (3, 14)


def require_python():
    """Accept any Python 3.14 patch release and reject other minor versions."""
    if sys.version_info[:2] != REQUIRED_PYTHON:
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(
            "TIPICE LabJack requires Python 3.14.x; found Python {}.\n"
            "Install Python 3.14. If .venv already exists, rename it to an unused "
            "backup name, then run setup.bat (Windows) or ./setup.sh (macOS/Linux)."
            .format(current)
        )


if __name__ == "__main__":
    require_python()
