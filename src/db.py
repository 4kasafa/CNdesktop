"""SQLite transaksi (PRD §5). Idempoten via UNIQUE(no_transaksi)."""
import os
import sqlite3

from src.config import DB_FILE, app_dir

SCHEMA = """CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_transaksi TEXT UNIQUE NOT NULL,
  total INTEGER NOT NULL,
  tunai INTEGER NOT NULL DEFAULT 0,
  nontunai INTEGER NOT NULL DEFAULT 0,
  bank TEXT DEFAULT '',
  kategori TEXT NOT NULL CHECK(kategori IN ('Tunai','Nontunai','Split')),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)"""


def default_path() -> str:
    return os.path.join(app_dir(), DB_FILE)


def init_db(path: str | None = None) -> str:
    """Buat skema jika belum ada. Return path dipakai."""
    path = path or default_path()
    with sqlite3.connect(path) as c:
        c.execute(SCHEMA)
    return path


def insert_tx(path: str, no_transaksi: str, total: int, tunai: int = 0,
              nontunai: int = 0, bank: str = "", kategori: str = "Tunai") -> int | None:
    """INSERT idempoten: duplikat no_transaksi → None (bukan error)."""
    try:
        with sqlite3.connect(path) as c:
            cur = c.execute(
                "INSERT INTO transactions(no_transaksi,total,tunai,nontunai,bank,kategori)"
                " VALUES(?,?,?,?,?,?)", (no_transaksi, total, tunai, nontunai, bank, kategori))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # ponytail: duplikat/CHECK gagal = None, caller yang log needs_review


def list_since(path: str, since: int = 0, limit: int = 50) -> list[dict]:
    """Transaksi baru untuk HP polling, ORDER BY id ASC."""
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT * FROM transactions WHERE id > ? ORDER BY id ASC LIMIT ?",
            (since, limit))]
