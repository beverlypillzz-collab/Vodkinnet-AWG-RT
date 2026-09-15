import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    # httpx (used to call node-agents) is noisy at DEBUG.
    logging.getLogger("httpx").setLevel(
        "DEBUG" if level == "DEBUG" else "WARNING"
    )
    logging.getLogger("sqlalchemy.engine").setLevel(
        "INFO" if level == "DEBUG" else "WARNING"
    )

    logging.getLogger(__name__).info("Logging configured at level %s", level)
