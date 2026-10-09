"""Parse nominal Ketoko (PRD §3). Port `_clean_amount_text` docs/pos.md."""
import re


def parse_no_transaksi(raw: str | None) -> tuple[str | None, str | None]:
    """Nomor dokumen kasir -> (doc_id, counter).

    Full string = ID unik (`001519/KSR/SURJO/1026`); digit terdepan = nomor
    urut untuk deteksi missing di HP. Tolak kosong/`Auto`/non-digit-di-depan.
    """
    s = (raw or "").strip()
    if not s or s.lower() == "auto":
        return None, None
    m = re.match(r"\d+", s)
    if not m:
        return None, None
    return s, m.group(0)


def parse_nominal(raw: str | None) -> int | None:
    """`Rp 150.000,00` → `150000`. Tolak tanggal/jam, nol, kosong → `None`."""
    if not raw:
        return None
    if "/" in raw or ":" in raw:
        return None  # ponytail: tolak tanggal/jam (e.g. DateEdit 10/3/2026 5:11 PM)
    digits = "".join(ch for ch in re.sub(r"[,.]\d{1,2}$", "", raw.strip()) if ch.isdigit())
    if digits and int(digits) > 0:
        return int(digits)
    return None
