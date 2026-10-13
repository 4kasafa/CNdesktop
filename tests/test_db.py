import os
import tempfile

from src.db import (clear_transactions, delete_cashier, init_db, insert_tx,
                   list_cashiers, list_since, save_cashier)


def _tmp():
    return os.path.join(tempfile.mkdtemp(), "t.db")


def test_insert_valid():
    p = init_db(_tmp())
    assert insert_tx(p, "TRX1", 150000) == 1


def test_duplicate_no_double():
    p = init_db(_tmp())
    assert insert_tx(p, "TRX1", 150000) == 1
    assert insert_tx(p, "TRX1", 150000) is None
    assert len(list_since(p)) == 1


def test_bad_kategori_rejected():
    p = init_db(_tmp())
    assert insert_tx(p, "TRX9", 100, kategori="Kredit") is None


def test_list_since_asc():
    p = init_db(_tmp())
    for i in range(1, 4):
        insert_tx(p, f"TRX{i}", i * 1000, kategori="Tunai")
    rows = list_since(p, since=1, limit=50)
    assert [r["id"] for r in rows] == [2, 3]
    assert rows[0]["no_transaksi"] == "TRX2"


def test_migrate_old_schema_adds_no_urut():
    import sqlite3
    p = _tmp()
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "no_transaksi TEXT UNIQUE NOT NULL, total INTEGER NOT NULL,"
                  "tunai INTEGER NOT NULL DEFAULT 0, nontunai INTEGER NOT NULL DEFAULT 0,"
                  "bank TEXT DEFAULT '', kategori TEXT NOT NULL,"
                  "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT INTO transactions(no_transaksi,total,kategori) VALUES('9001',1000,'Tunai')")
    init_db(p)
    assert list_since(p)[0]["no_urut"] == "9001"


def test_insert_no_urut():
    p = init_db(_tmp())
    assert insert_tx(p, "001519/KSR/SURJO/1026", 28600, no_urut="001519") == 1
    r = list_since(p)[0]
    assert r["no_transaksi"] == "001519/KSR/SURJO/1026" and r["no_urut"] == "001519"


def test_cashier_crud():
    p = init_db(_tmp())
    assert list_cashiers(p) == []
    r1 = save_cashier(p, "Surjo", "K01", "Cabang A", "Pagi")
    assert r1 == 1
    rows = list_cashiers(p)
    assert len(rows) == 1 and rows[0]["name"] == "Surjo"
    assert rows[0]["branch"] == "Cabang A" and rows[0]["shift"] == "Pagi"
    save_cashier(p, "Surjo Baru", "K01", "Cabang B", "Malam", rowid=r1)
    assert list_cashiers(p)[0]["branch"] == "Cabang B"
    delete_cashier(p, r1)
    assert list_cashiers(p) == []


def test_cashier_id_duplikat_diperbolehkan():
    p = init_db(_tmp())
    r1 = save_cashier(p, "A", "SAMA")
    r2 = save_cashier(p, "B", "SAMA")
    assert (r1, r2) == (1, 2)
    assert len(list_cashiers(p)) == 2


def test_cashier_nama_kosong_ditolak():
    p = init_db(_tmp())
    assert save_cashier(p, "   ") is None
    assert list_cashiers(p) == []


def test_cashier_delete_tepat_rowid():
    p = init_db(_tmp())
    r1 = save_cashier(p, "A", "X")
    r2 = save_cashier(p, "B", "X")
    delete_cashier(p, r1)
    rows = list_cashiers(p)
    assert [r["rowid"] for r in rows] == [r2]
    assert rows[0]["name"] == "B"


def test_cashiers_table_dibuat_di_db_lama():
    import sqlite3
    p = _tmp()
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "no_transaksi TEXT UNIQUE NOT NULL, total INTEGER NOT NULL,"
                  "tunai INTEGER NOT NULL DEFAULT 0, nontunai INTEGER NOT NULL DEFAULT 0,"
                  "bank TEXT DEFAULT '', kategori TEXT NOT NULL,"
                  "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    init_db(p)
    assert save_cashier(p, "Lama", "L1") == 1


def test_insert_berzona_lokal():
    from datetime import datetime
    p = init_db(_tmp())
    insert_tx(p, "LOKAL1", 5000)
    ts = list_since(p)[0]["created_at"]
    got = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    assert abs((datetime.now() - got).total_seconds()) < 120


def test_migrasi_utc_ke_wib_sekali():
    import sqlite3
    p = _tmp()
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "no_transaksi TEXT UNIQUE NOT NULL, total INTEGER NOT NULL,"
                  "tunai INTEGER NOT NULL DEFAULT 0, nontunai INTEGER NOT NULL DEFAULT 0,"
                  "bank TEXT DEFAULT '', kategori TEXT NOT NULL,"
                  "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT INTO transactions(no_transaksi,total,kategori,created_at)"
                  " VALUES('UTC1',1000,'Tunai','2026-10-11 07:00:00')")
    init_db(p)
    assert list_since(p)[0]["created_at"] == "2026-10-11 14:00:00"
    init_db(p)  # kedua kali tak geser ganda
    assert list_since(p)[0]["created_at"] == "2026-10-11 14:00:00"


def test_clear_dengan_backup(monkeypatch, tmp_path):
    import sqlite3
    p = init_db(_tmp())
    insert_tx(p, "C1", 1000)
    insert_tx(p, "C2", 2000)
    monkeypatch.setattr("src.db.app_dir", lambda: str(tmp_path))
    n, bak = clear_transactions(p, backup=True)
    assert n == 2 and bak and os.path.exists(bak)
    with sqlite3.connect(bak) as c:
        assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    assert list_since(p) == []


def test_clear_tanpa_backup():
    p = init_db(_tmp())
    insert_tx(p, "C1", 1000)
    n, bak = clear_transactions(p, backup=False)
    assert (n, bak) == (1, None)
    assert list_since(p) == []


def test_insert_created_at_eksplisit_verbatim():
    p = init_db(_tmp())
    insert_tx(p, "STAMP1", 9000, created_at="2026-10-03 17:11:00")
    assert list_since(p)[0]["created_at"] == "2026-10-03 17:11:00"
    insert_tx(p, "STAMP2", 9000)  # None -> default skema, bukan verbatim di atas
    assert list_since(p)[1]["created_at"] != "2026-10-03 17:11:00"


def test_wipe_delete_tanpa_backup():
    import glob
    from src.db import wipe_transactions
    p = init_db(_tmp())
    insert_tx(p, "W1", 1000)
    insert_tx(p, "W2", 2000)
    d = os.path.dirname(p)
    before = set(glob.glob(os.path.join(d, "*.bak-*")))
    assert wipe_transactions(p) == 2
    assert list_since(p) == []
    assert set(glob.glob(os.path.join(d, "*.bak-*"))) == before


def test_wipe_sequence_reset_dari_1():
    from src.db import insert_tx, wipe_transactions
    p = init_db(_tmp())
    insert_tx(p, "S1", 1000)
    insert_tx(p, "S2", 2000)
    wipe_transactions(p)
    assert insert_tx(p, "S3", 3000) == 1


def test_wipe_keep_cashiers_utuh():
    from src.db import list_cashiers, save_cashier, wipe_transactions
    p = init_db(_tmp())
    save_cashier(p, "Surjo", "K01")
    insert_tx(p, "K1", 1000)
    n_before = len(list_cashiers(p))
    wipe_transactions(p)
    assert len(list_cashiers(p)) == n_before == 1


def test_pin_default_363636():
    from src.db import DEFAULT_WIPE_PIN, get_wipe_pin, set_wipe_pin
    assert DEFAULT_WIPE_PIN == "363636"
    p = init_db(_tmp())
    assert get_wipe_pin(p) == "363636"
    set_wipe_pin(p, "112233")
    assert get_wipe_pin(p) == "112233"
    try:
        set_wipe_pin(p, "abc")
    except ValueError:
        pass
    else:
        raise AssertionError("PIN invalid harus raise")


def test_watcher_persist_ingat_terakhir():
    from src.db import get_watcher_enabled, set_watcher_enabled
    p = init_db(_tmp())
    assert get_watcher_enabled(p) is True  # hilang = default aktif
    set_watcher_enabled(p, False)
    assert get_watcher_enabled(p) is False
    set_watcher_enabled(p, True)
    assert get_watcher_enabled(p) is True


def test_dashboard_button_butuh_pin():
    from src.dashboard import check_watcher_pin, validate_new_pin
    p = init_db(_tmp())
    assert check_watcher_pin(p, "363636") is True  # tiap klik wajib PIN benar
    assert check_watcher_pin(p, "000000") is False
    assert validate_new_pin("363636") is None
    assert validate_new_pin("12") is not None
