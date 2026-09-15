"""
Central logging setup for node-agent.

Design goals:
- Debuggable on a live node without SSH-ing in and grepping raw text —
  structured, consistent format with request context where possible.
- Never log secrets: AGENT_TOKEN, private keys, or full config files
  must never reach a log line, even at DEBUG level. Call sites are
  responsible for redacting before logging; this module just sets the
  format/level.
- Uvicorn's own loggers are aligned to the same level so `docker logs`
  gives one coherent stream instead of two different formats.
"""

import logging
import sys


LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if configure_logging() is called twice
    # (e.g. under a test runner that imports main twice).
    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    # Keep noisy third-party loggers at a sane level even when we're at
    # DEBUG ourselves — docker-py in particular is extremely verbose at
    # DEBUG and will drown out our own log lines.
    logging.getLogger("docker").setLevel(
        "DEBUG" if level == "DEBUG" else "WARNING"
    )
    logging.getLogger("urllib3").setLevel("WARNING")

    # Uvicorn's access/error loggers — align format so lines look the
    # same whether they come from our code or the ASGI server.
    for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(uvicorn_logger).handlers = []
        logging.getLogger(uvicorn_logger).propagate = True

    logging.getLogger(__name__).info(
        "Logging configured at level %s", level
    )
