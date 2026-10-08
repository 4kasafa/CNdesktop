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
