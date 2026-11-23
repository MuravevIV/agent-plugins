"""Reads the app's settings."""
import json
import os
from pathlib import Path

DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3
DEFAULT_PATH = "config.json"


def load_config():
    """Settings from the config file, with defaults for whatever it leaves out."""
    path = Path(os.environ.get("APP_CONFIG", DEFAULT_PATH))
    settings = {"timeout": DEFAULT_TIMEOUT, "retries": DEFAULT_RETRIES}
    if path.is_file():
        settings.update(json.loads(path.read_text(encoding="utf-8")))
    return settings
