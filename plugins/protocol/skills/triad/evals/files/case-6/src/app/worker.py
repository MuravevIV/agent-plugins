"""Runs one job. Gets its settings from the caller."""


def run_job(name, config):
    for attempt in range(config["retries"]):
        if try_once(name, config["timeout"]):
            return True
    return False


def try_once(name, timeout):
    return True
