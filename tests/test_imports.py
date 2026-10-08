"""Semua modul src wajib importable (jebak SyntaxError, mis. dashboard v1.0.2)."""
import importlib


def test_all_importable():
    for m in ("src.api", "src.classify", "src.config", "src.dashboard",
              "src.db", "src.log", "src.parse", "src.pos_reader",
              "src.tray", "src.watcher"):
        importlib.import_module(m)
