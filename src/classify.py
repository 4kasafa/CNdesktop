"""Klasifikasi metode bayar (PRD §4, verbatim, toleransi 0)."""


def classify(total: int | None, tunai: int | None, debit: int | None, bank: str) -> str:
    """Tunai/Nontunai/Split else `needs_review` (jangan save). Tunai murni: kembalian diabaikan."""
    if not total:
        return "needs_review"
    debit = debit or 0
    if not bank and debit == 0:
        return "Tunai"
    if debit == total:
        return "Nontunai"
    if debit + (tunai or 0) == total:
        return "Split"
    return "needs_review"
