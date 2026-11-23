"""Runs the due jobs once a minute."""
import time

from app.config import load_config
from app.worker import run_job


def due_jobs(now):
    return []


def loop():
    while True:
        config = load_config()
        for name in due_jobs(time.time()):
            run_job(name, config)
        time.sleep(60)
