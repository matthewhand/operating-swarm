import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEBUG = os.environ.get("SWARM_DEBUG", "").lower() in ("1", "true", "yes")

# Fallback for when Django settings are not configured
DEFAULT_LOGS_DIR = Path.cwd() / "logs"
DEFAULT_LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a logger with the specified name.

    Args:
        name (str): Name of the logger.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    log_level = logging.DEBUG if DEBUG else logging.INFO
    logger.setLevel(log_level)

    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(log_level)

    # Determine log file path
    try:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        try:
            log_dir = getattr(settings, "LOGS_DIR", DEFAULT_LOGS_DIR)
        except ImproperlyConfigured:
            log_dir = DEFAULT_LOGS_DIR
    except ImportError:
        log_dir = DEFAULT_LOGS_DIR

    log_file = log_dir / f"{name}.log"

    # Create file handler with rotation
    fh = RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
    )
    fh.setLevel(log_level)

    # Create formatter and add it to the handlers
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    # Avoid adding multiple handlers if they already exist
    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger
