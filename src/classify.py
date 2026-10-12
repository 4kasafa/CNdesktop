"""Klasifikasi metode bayar (PRD §4, verbatim, toleransi 0)."""


def classify(total: int | None, tunai: int | None, debit: int | None, bank: str) -> str:
    """Tunai/Nontunai/Split; `needs_review` hanya bila total kosong.

    Total dari kasir (dialog hanya tipe): ambigu (bank↔debit tak lengkap),
    kembalian, atau tunai gagal -> default Tunai. Split longgar tahan
    kembalian: debit>0, debit<total, tunai>=sisa.
    """
    if not total:
        return "needs_review"
    debit = debit or 0
    tunai = tunai or 0
    if debit == total:
        return "Nontunai"
    if not bank and debit == 0:
        return "Tunai"  # kembalian (tunai>=total) / tunai gagal diabaikan
    if 0 < debit < total and tunai >= total - debit:
        return "Split"  # ponytail: tunai dinormalisasi = total-debit oleh caller
    if not bank:
        return "Tunai"  # ponytail: debit gagal/0 tanpa bank -> jangan tebak Split
    if debit == 0:
        return "Tunai"  # ponytail: bank ada tapi debit gagal -> default Tunai
    return "Tunai"  # ponytail: mismatch angka (lag) -> simpan Tunai, jangan hangus
