"""Logging configuration shared by the API and the data pipeline."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not any(getattr(h, "_crisees", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S"))
        handler._crisees = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level.upper())
    # Quiet noisy third-party loggers.
    for name in ("urllib3", "fiona", "pyogrio", "botocore"):
        logging.getLogger(name).setLevel(logging.WARNING)
