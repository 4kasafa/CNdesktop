"""SQLite transaksi (PRD §5). Idempoten via UNIQUE(no_transaksi)."""
import os
import shutil
import sqlite3

from src.config import DB_FILE, app_dir

SCHEMA = """CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_transaksi TEXT UNIQUE NOT NULL,
  no_urut TEXT DEFAULT '',
  total INTEGER NOT NULL,
  tunai INTEGER NOT NULL DEFAULT 0,
  nontunai INTEGER NOT NULL DEFAULT 0,
  bank TEXT DEFAULT '',
  kategori TEXT NOT NULL CHECK(kategori IN ('Tunai','Nontunai','Split')),
  created_at DATETIME DEFAULT (datetime('now','localtime'))
)"""
# ponytail: localtime agar jam tampil = jam toko (dulu CURRENT_TIMESTAMP = UTC)

META_SCHEMA = """CREATE TABLE IF NOT EXISTS app_meta(
  key TEXT PRIMARY KEY, value TEXT DEFAULT ''
)"""


CASHIERS_SCHEMA = """CREATE TABLE IF NOT EXISTS cashiers(
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  kasir_id TEXT DEFAULT '',
  name TEXT NOT NULL,
  branch TEXT DEFAULT '',
  shift TEXT DEFAULT ''
)"""
# ponytail: kasir_id bebas duplikat (bukan data penting) -> alamat baris via rowid


def _migrate(conn):
    """Tambah no_urut ke DB skema lama + backfill. Idempoten."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)")]
    if "no_urut" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN no_urut TEXT DEFAULT ''")
    from src.parse import parse_no_transaksi
    for tid, no in conn.execute(
            "SELECT id, no_transaksi FROM transactions WHERE no_urut IS NULL OR no_urut = ''"):
        _, counter = parse_no_transaksi(no or "")
        conn.execute("UPDATE transactions SET no_urut = ? WHERE id = ?", (counter or "", tid))


def _migrate_tz(conn):
    """Geser baris era-UTC ke WIB (+7 jam), sekali saja (flag tz_fix_v1)."""
    conn.execute(META_SCHEMA)
    row = conn.execute("SELECT value FROM app_meta WHERE key='tz_fix_v1'").fetchone()
    if row:
        return
    conn.execute("UPDATE transactions SET created_at = datetime(created_at, '+7 hours')")
    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('tz_fix_v1','1')")


def default_path() -> str:
    return os.path.join(app_dir(), DB_FILE)


def init_db(path: str | None = None) -> str:
    """Buat/migrasi skema jika perlu. Return path dipakai."""
    path = path or default_path()
    with sqlite3.connect(path) as c:
        c.execute(SCHEMA)
        c.execute(CASHIERS_SCHEMA)
        _migrate(c)
        _migrate_tz(c)
    return path


def insert_tx(path: str, no_transaksi: str, total: int, tunai: int = 0,
              nontunai: int = 0, bank: str = "", kategori: str = "Tunai",
              no_urut: str = "") -> int | None:
    """INSERT idempoten: duplikat no_transaksi → None (bukan error)."""
    try:
        with sqlite3.connect(path) as c:
            cur = c.execute(
                "INSERT INTO transactions(no_transaksi,no_urut,total,tunai,nontunai,bank,kategori)"
                " VALUES(?,?,?,?,?,?,?)",
                (no_transaksi, no_urut, total, tunai, nontunai, bank, kategori))
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


def list_cashiers(path: str) -> list[dict]:
    """Semua kasir ORDER BY rowid ASC. Tiap dict: rowid/kasir_id/name/branch/shift."""
    with sqlite3.connect(path) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT rowid, kasir_id, name, branch, shift FROM cashiers ORDER BY rowid ASC")]


def save_cashier(path: str, name: str, kasir_id: str = "", branch: str = "",
                 shift: str = "", rowid: int | None = None) -> int | None:
    """Tambah (rowid None) atau edit (rowid ada). Return rowid, None jika nama kosong."""
    name = (name or "").strip()
    if not name:
        return None
    with sqlite3.connect(path) as c:
        if rowid is None:
            cur = c.execute(
                "INSERT INTO cashiers(kasir_id,name,branch,shift) VALUES(?,?,?,?)",
                (kasir_id or "", name, branch or "", shift or ""))
            return cur.lastrowid
        c.execute("UPDATE cashiers SET kasir_id=?,name=?,branch=?,shift=? WHERE rowid=?",
                  (kasir_id or "", name, branch or "", shift or "", rowid))
        return rowid


def delete_cashier(path: str, rowid: int) -> None:
    with sqlite3.connect(path) as c:
        c.execute("DELETE FROM cashiers WHERE rowid=?", (rowid,))


def clear_transactions(path: str, backup: bool = True) -> tuple:
    """Hapus SEMUA transaksi. Backup file dulu bila diminta.

    Return (n_hapus, backup_path|None)."""
    backup_path = None
    if backup:
        from datetime import datetime as _dt
        stamp = _dt.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(
            app_dir(), f"{os.path.basename(path)}.bak-{stamp}")
        shutil.copy(path, backup_path)
    with sqlite3.connect(path) as c:
        cur = c.execute("DELETE FROM transactions")
        return cur.rowcount, backup_path
