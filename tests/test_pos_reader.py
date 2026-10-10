"""Cache UIA pos_reader: hit cepat + rescan saat handle basi, tanpa raise."""
from types import SimpleNamespace

from src import pos_reader as P


class _Stub:
    """Elemen UIA palsu: ValuePattern (mati = semua raise, tanpa Exists)."""

    def __init__(self, alive=True, value="001699/KSR/SURJO/1026"):
        self._alive = alive
        self._value = value

    def Exists(self, _a, _b):
        raise AssertionError("fast path tak boleh tree-walk")

    def GetValuePattern(self):
        if not self._alive:
            raise RuntimeError("element dead")
        return SimpleNamespace(Value=self._value)

    @property
    def Name(self):
        if not self._alive:
            raise RuntimeError("element dead")
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


def test_lifetime_init_smoke():
    """lifetime_init dapat di-hold via with (context seumur thread pekerja)."""
    with P.lifetime_init():
        pass


class _Counting:
    """Elemen UIA hitung pola baca: sukses harus tepat 1 COM call (Value)."""

    def __init__(self):
        self.calls = []

    def Exists(self, _a, _b):
        raise AssertionError("fast path tak boleh tree-walk")

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


class _LegacyOnly:
    """Value raise + Name kosong: pemenang = legacy."""

    def __init__(self, value):
        self.calls = []
        self._value = value

    def Exists(self, _a, _b):
        raise AssertionError("fast path tak boleh tree-walk")

    def GetValuePattern(self):
        self.calls.append("value")
        raise RuntimeError("no value pattern")

    @property
    def Name(self):
        self.calls.append("name")
        return ""

    def GetLegacyIAccessiblePattern(self):
        from types import SimpleNamespace
        self.calls.append("legacy")
        return SimpleNamespace(Value=self._value)


def test_no_winner_source():
    """Sumber-pemenang tercatat: sampel berikut tepat 1 call sumber itu."""
    el = _LegacyOnly("001700/KSR/SURJO/1026")
    P._EL_NO[780] = el
    P._EL_SRC[780] = "legacy"
    try:
        assert P.read_no_transaksi(780) == "001700/KSR/SURJO/1026"
        assert el.calls == ["legacy"]
    finally:
        P._EL_NO.pop(780, None)
        P._EL_SRC.pop(780, None)


def test_dialog_fast_no_exists():
    """Fast dialog tanpa tree-walk: total+tunai dari cache, Exists tak tersentuh."""
    P._EL_TOTAL[781] = _Stub(alive=True, value="24.000,00")
    P._EL_SRC[(781, "total")] = "value"
    P._EL_TUNAI[781] = _Stub(alive=True, value="50.000,00")
    P._EL_SRC[(781, "tunai")] = "value"
    try:
        out = P.read_dialog_fast(781)
        assert out["total_raw"] == "24.000,00" and out["tunai_raw"] == "50.000,00"
    finally:
        P.drop_dialog_cache(781)
