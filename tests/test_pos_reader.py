"""Cache UIA pos_reader: hit cepat + rescan saat handle basi, tanpa raise."""
from types import SimpleNamespace

from src import pos_reader as P


class _Stub:
    """Elemen UIA palsu: Exists terkendali + ValuePattern."""

    def __init__(self, alive=True, value="001699/KSR/SURJO/1026"):
        self._alive = alive
        self._value = value

    def Exists(self, _a, _b):
        return self._alive

    def GetValuePattern(self):
        return SimpleNamespace(Value=self._value)

    @property
    def Name(self):
        return ""

    def GetLegacyIAccessiblePattern(self):
        raise RuntimeError("no legacy")


def test_no_cache_hit():
    """Handle cache hidup -> nilai langsung, tanpa UIA scan, cache dipertahankan."""
    P._EL_NO[777] = _Stub(alive=True)
    try:
        assert P.read_no_transaksi(777) == "001699/KSR/SURJO/1026"
        assert 777 in P._EL_NO
    finally:
        P._EL_NO.pop(777, None)


def test_stale_cache_rescan():
    """Handle basi -> dibuang + fallback tanpa raise ('' bila window hilang)."""
    P._EL_NO[778] = _Stub(alive=False)
    try:
        assert P.read_no_transaksi(778) == ""
        assert 778 not in P._EL_NO
    finally:
        P._EL_NO.pop(778, None)


def test_drop_caches_safe():
    """Drop hwnd tak dikenal = no-op."""
    P.drop_dialog_cache(123456)
    P.drop_no_cache(123456)


class _Counting:
    """Elemen UIA hitung pola baca: sukses harus tepat 1 COM call (Value)."""

    def __init__(self):
        self.calls = []

    def Exists(self, _a, _b):
        return True

    def GetValuePattern(self):
        from types import SimpleNamespace
        self.calls.append("value")
        return SimpleNamespace(Value="Auto")

    @property
    def Name(self):
        self.calls.append("name")
        return ""

    def GetLegacyIAccessiblePattern(self):
        self.calls.append("legacy")
        raise RuntimeError("no legacy")


def test_no_value_only():
    """Cache-hit baca Value saja: tepat 1 COM call, tanpa Name/Legacy."""
    el = _Counting()
    P._EL_NO[779] = el
    try:
        assert P.read_no_transaksi(779) == "Auto"
        assert el.calls == ["value"]
    finally:
        P._EL_NO.pop(779, None)
