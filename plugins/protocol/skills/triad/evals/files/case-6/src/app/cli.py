"""Command line entry point."""
import sys

from app.config import load_config
from app.worker import run_job


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    config = load_config()
    for name in argv:
        run_job(name, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
