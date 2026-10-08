from src.classify import classify


def test_tunai_ignores_change():
    assert classify(150000, 200000, 0, "") == "Tunai"


def test_nontunai():
    assert classify(150000, 0, 150000, "BCA") == "Nontunai"


def test_split_live_values():
    assert classify(284700, 47200, 237500, "BCA") == "Split"


def test_off_by_one_is_review():
    assert classify(150000, 75000, 74999, "BCA") == "needs_review"


def test_bank_set_debit_zero_is_review():
    assert classify(150000, 50000, 0, "BCA") == "needs_review"


def test_total_none_is_review():
    assert classify(None, 0, 0, "") == "needs_review"
