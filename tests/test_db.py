import os
import tempfile

from src.db import init_db, insert_tx, list_since


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
