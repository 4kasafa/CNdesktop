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


DEFAULT_WIPE_PIN = "363636"


def validate_pin(pin: str) -> str | None:
    """Return pesan error, atau None jika PIN 6-digit valid. Lapisan bersama GUI+API."""
    pin = (pin or "").strip()
    if not (pin.isdigit() and len(pin) == 6):
        return "PIN harus 6 digit angka."
    return None


def get_wipe_pin(path: str | None = None) -> str:
    """PIN hapus/watcher, default 363636. Disimpan di app_meta."""
    path = path or default_path()
    with sqlite3.connect(path) as c:
        c.execute(META_SCHEMA)
        row = c.execute("SELECT value FROM app_meta WHERE key='wipe_pin'").fetchone()
        return row[0] if row and row[0] else DEFAULT_WIPE_PIN


def set_wipe_pin(path: str, pin: str) -> None:
    """Simpan PIN 6-digit. Raise ValueError jika format salah."""
    pin = (pin or "").strip()
    if not (pin.isdigit() and len(pin) == 6):
        raise ValueError("PIN harus 6 digit angka.")
    with sqlite3.connect(path) as c:
        c.execute(META_SCHEMA)
        c.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('wipe_pin',?)", (pin,))


def get_watcher_enabled(path: str | None = None) -> bool:
    """Status watcher persist, default aktif (hilang/rusak = True)."""
    path = path or default_path()
    try:
        with sqlite3.connect(path) as c:
            c.execute(META_SCHEMA)
            row = c.execute("SELECT value FROM app_meta WHERE key='watcher_enabled'").fetchone()
            if not row:
                return True
            return (row[0] or "1") != "0"
    except Exception:
        return True


def set_watcher_enabled(path: str, enabled: bool) -> None:
    with sqlite3.connect(path) as c:
        c.execute(META_SCHEMA)
        c.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('watcher_enabled',?)",
                  ("1" if enabled else "0",))


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
              no_urut: str = "", created_at: str | None = None) -> int | None:
    """INSERT idempoten: duplikat no_transaksi → None (bukan error).

    created_at eksplisit (e.g. tanggal POS) disimpan verbatim;
    None → default skema seperti sebelumnya. Skema tak diubah.
    """
    try:
        with sqlite3.connect(path) as c:
            if created_at is None:
                cur = c.execute(
                    "INSERT INTO transactions(no_transaksi,no_urut,total,tunai,nontunai,bank,kategori)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (no_transaksi, no_urut, total, tunai, nontunai, bank, kategori))
            else:
                cur = c.execute(
                    "INSERT INTO transactions(no_transaksi,no_urut,total,tunai,nontunai,bank,kategori,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (no_transaksi, no_urut, total, tunai, nontunai, bank, kategori, created_at))
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


def wipe_transactions(path: str) -> int:
    """Hapus SEMUA transactions tanpa backup, reset ID dari 1. Cashiers utuh.

    Return jumlah baris terhapus."""
    with sqlite3.connect(path) as c:
        cur = c.execute("DELETE FROM transactions")
        n = cur.rowcount
        c.execute("DELETE FROM sqlite_sequence WHERE name='transactions'")
        c.commit()
        c.execute("VACUUM")
        return n
