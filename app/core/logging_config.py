"""Minimal structured request logging."""

import logging
import json
import time

logger = logging.getLogger("dizi.api")


def setup_logging():
    """Configure structured logging for the application."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False


def log_request(method: str, path: str, status: int, duration_ms: float):
    """Emit a structured request log line."""
    logger.info(json.dumps({
        "ts": time.time(),
        "method": method,
        "path": path,
        "status": status,
        "dur_ms": round(duration_ms, 2),
    }))


setup_logging()
