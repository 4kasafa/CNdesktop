"""Logging CNdesktop: file geser di %APPDATA%/CNdesktop/logs/. Silent.

UIA gagal = log level rendah, tidak pernah raise ke kasir.
Tanpa console/stream handler (tray-only, tanpa console).
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from src.config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUPS, LOG_SUBDIR, app_dir


def setup_logging(level=logging.INFO, log_dir=None):
    """Idempoten. Return logger 'cndesktop'."""
    log_dir = log_dir or os.path.join(app_dir(), LOG_SUBDIR)
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


def _log_dir(resolved=None) -> str:
    return resolved or os.path.join(app_dir(), LOG_SUBDIR)


def clear_logs(log_dir=None) -> int:
    """Hapus log aktif + rotasi .1-.5, buat kosong baru. Return jumlah file dihapus.

    Menutup handler dulu agar file tidak terkunci, lalu pasang handler baru
    agar logger tetap tulis ke file kosong."""
    d = _log_dir(log_dir)
    os.makedirs(d, exist_ok=True)
    logger = logging.getLogger("cndesktop")
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)
    targets = [os.path.join(d, LOG_FILE)] + \
        [os.path.join(d, f"{LOG_FILE}.{i}") for i in range(1, LOG_BACKUPS + 1)]
    n = 0
    for p in targets:
        try:
            if os.path.exists(p):
                os.remove(p)
                n += 1
        except Exception:
            pass
    open(os.path.join(d, LOG_FILE), "a", encoding="utf-8").close()
    if log_dir:
        setup_logging(log_dir=log_dir)
    else:
        setup_logging()
    return n
