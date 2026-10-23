"""Historian settings shared by the desktop app and standalone service."""

import json
import logging
import os
from pathlib import Path


_path = Path(__file__).resolve().parents[1] / ".historian.local.json"
try:
    _local = json.loads(_path.read_text()) if _path.exists() else {}
    if not isinstance(_local, dict):
        raise ValueError("Historian settings must be a JSON object.")
except (OSError, ValueError):
    logging.warning("Could not load local historian settings; using environment settings.")
    _local = {}


def _setting(name, default=""):
    return os.environ.get(name, _local.get(name, default))


INFLUX_URL = _setting("INFLUX_URL", "http://10.5.112.172:8086")
INFLUX_TOKEN = _setting("INFLUX_TOKEN")
INFLUX_ORG = _setting("INFLUX_ORG", "BYUChemE")
INFLUX_BUCKET = _setting("INFLUX_BUCKET", "UOLab")
