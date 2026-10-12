from src.parse import parse_no_transaksi, parse_nominal, parse_tanggal_pos


def test_id_format():
    assert parse_nominal("Rp 150.000,00") == 150000


def test_us_format_live():
    assert parse_nominal("47,200.00") == 47200
    assert parse_nominal("284,700.00") == 284700


def test_plain_and_zero():
    assert parse_nominal("47200") == 47200
    assert parse_nominal("0") is None
    assert parse_nominal("0.00") is None


def test_empty_and_none():
    assert parse_nominal("") is None
    assert parse_nominal(None) is None


def test_datetime_rejected():
    assert parse_nominal("10/3/2026 5:11 PM") is None


def test_no_dokumen_full_dan_counter():
    assert parse_no_transaksi("001519/KSR/SURJO/1026") == ("001519/KSR/SURJO/1026", "001519")
    assert parse_no_transaksi("9001") == ("9001", "9001")
    assert parse_no_transaksi("  Auto  ") == (None, None)
    assert parse_no_transaksi("") == (None, None)
    assert parse_no_transaksi(None) == (None, None)
    assert parse_no_transaksi("KSR/1026") == (None, None)


def test_tanggal_pos_ampm():
    assert parse_tanggal_pos("10/3/2026 5:11 PM") == "2026-03-10 17:11:00"
    assert parse_tanggal_pos("10/3/2026 12:00 AM") == "2026-03-10 00:00:00"
    assert parse_tanggal_pos("10/3/2026 12:00 PM") == "2026-03-10 12:00:00"


def test_tanggal_pos_date_only_dan_24jam():
    assert parse_tanggal_pos("03/10/2026") == "2026-10-03 00:00:00"
    assert parse_tanggal_pos("03/10/2026 21:05") == "2026-10-03 21:05:00"


def test_tanggal_pos_sampah_none():
    assert parse_tanggal_pos("") is None
    assert parse_tanggal_pos(None) is None
    assert parse_tanggal_pos("Auto") is None
    assert parse_tanggal_pos("32/13/2026") is None
    assert parse_tanggal_pos("10/3/2019 5:11 PM") is None
    assert parse_tanggal_pos("30/02/2026") is None
