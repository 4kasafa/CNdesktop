"""Parse nominal Ketoko (PRD §3). Port `_clean_amount_text` docs/pos.md."""
import re


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
