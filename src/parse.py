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


def parse_tanggal_pos(raw: str | None) -> str | None:
    """Tanggal-jam POS → `YYYY-MM-DD HH:MM:SS`, `None` bila tak kalender.

    Terima `d/m/yyyy h:mm AM/PM` (12AM→00, 12PM→12), `dd/mm/yyyy`,
    varian jam 24-jam. Tanggal-only → jam `00:00:00` (caller yang
    memutuskan, bukan tebak jam-save di sini).
    """
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?)?", s)
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    if y < 2020 or y > 2100:
        return None
    # ponytail: POS Indonesia dd/mm; bila a>12 pasti hari, bila b>12 tukar
    d, mo = (a, b) if b <= 12 else (b, a)
    if not 1 <= mo <= 12:
        return None
    hh, mi, ss = 0, 0, 0
    if m.group(4) is not None:
        hh, mi = int(m.group(4)), int(m.group(5))
        ss = int(m.group(6) or 0)
        ap = (m.group(7) or "").upper()
        if ap == "AM":
            hh = 0 if hh == 12 else hh
        elif ap == "PM":
            hh = 12 if hh == 12 else hh + 12
        if not (hh <= 23 and mi <= 59 and ss <= 59):
            return None
    try:
        from datetime import datetime
        return datetime(y, mo, d, hh, mi, ss).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
