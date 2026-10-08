"""Logging CNdesktop: file geser di %APPDATA%/CNdesktop/logs/. Silent.

UIA gagal = log level rendah, tidak pernah raise ke kasir.
Tanpa console/stream handler (tray-only, tanpa console).
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from src.config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUPS, LOG_SUBDIR, app_dir


def setup_logging(level=logging.INFO):
    """Idempoten. Return logger 'cndesktop'."""
    log_dir = os.path.join(app_dir(), LOG_SUBDIR)
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("cndesktop")
    if logger.handlers:
        return logger  # ponytail: panggil 2x (test + main) = 1 handler
    h = RotatingFileHandler(os.path.join(log_dir, LOG_FILE),
                            maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
                            encoding="utf-8")
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(h)
    logger.setLevel(level)
    logger.propagate = False
    return logger
