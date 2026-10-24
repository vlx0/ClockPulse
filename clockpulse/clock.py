"""CPU P-state MHz, hybrid P/E classes, power schemes. No pip."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import winreg
from dataclasses import dataclass

powrprof = ctypes.windll.powrprof
kernel32 = ctypes.windll.kernel32
pdh = ctypes.windll.pdh

PROCESSOR_INFORMATION = 11
ACCESS_SCHEME = 16
ERROR_NO_MORE_ITEMS = 259
PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000


class PROCESSOR_POWER_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Number", wt.ULONG),
        ("MaxMhz", wt.ULONG),
        ("CurrentMhz", wt.ULONG),
        ("MhzLimit", wt.ULONG),
        ("MaxIdleState", wt.ULONG),
        ("CurrentIdleState", wt.ULONG),
    ]


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", ctypes.c_double),
            ("largeValue", ctypes.c_int64),
        ]

    _anonymous_ = ("u",)
    _fields_ = [("CStatus", wt.DWORD), ("u", _U)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wt.DWORD),
        ("Data2", wt.WORD),
        ("Data3", wt.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


@dataclass
class Scheme:
    guid: str
    name: str


@dataclass
class ClockSnap:
    name: str
    cores: list[int]
    windows_max: int
    limit: int
    scheme: str
    scheme_guid: str
    hybrid: bool
    p_idx: tuple[int, ...]
    e_idx: tuple[int, ...]
    p_avg: float
    p_min: int
    p_max: int
    e_avg: float
    e_min: int
    e_max: int
    live: bool
    pstate_p: int
    pstate_e: int


def cpu_name() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return str(val).strip()
    except OSError:
        return ""


def guid_text(g: GUID) -> str:
    d4 = "".join(f"{b:02x}" for b in g.Data4)
    return f"{g.Data1:08x}-{g.Data2:04x}-{g.Data3:04x}-{d4[:4]}-{d4[4:]}"


def guid_from_text(s: str) -> GUID:
    a, b, c, d, e = s.strip("{}").lower().split("-")
    raw = bytes.fromhex(d + e)
    g = GUID()
    g.Data1 = int(a, 16)
    g.Data2 = int(b, 16)
    g.Data3 = int(c, 16)
    for i, x in enumerate(raw):
        g.Data4[i] = x
    return g


def _scheme_name(g: GUID) -> str:
    buf = ctypes.create_unicode_buffer(256)
    size = wt.DWORD(ctypes.sizeof(buf))
    if powrprof.PowerReadFriendlyName(None, ctypes.byref(g), None, None, buf, ctypes.byref(size)) == 0:
        return buf.value.strip()
    return ""


def active_scheme() -> tuple[str, str]:
    ptr = ctypes.POINTER(GUID)()
    rc = powrprof.PowerGetActiveScheme(None, ctypes.byref(ptr))
    if rc != 0 or not ptr:
        return "", ""
    try:
        gid = guid_text(ptr.contents)
        return _scheme_name(ptr.contents), gid.lower()
    finally:
        kernel32.LocalFree(ptr)


def list_schemes() -> list[Scheme]:
    out: list[Scheme] = []
    idx = 0
    while idx < 24:
        g = GUID()
        size = wt.DWORD(ctypes.sizeof(GUID))
        rc = powrprof.PowerEnumerate(
            None, None, None, ACCESS_SCHEME, idx, ctypes.byref(g), ctypes.byref(size)
        )
        if rc == ERROR_NO_MORE_ITEMS:
            break
        if rc != 0:
            break
        gid = guid_text(g)
        out.append(Scheme(gid.lower(), _scheme_name(g) or gid[:8]))
        idx += 1
    return out


def set_scheme(gid: str) -> str | None:
    try:
        g = guid_from_text(gid)
    except ValueError:
        return "непонятный GUID схемы"
    rc = powrprof.PowerSetActiveScheme(None, ctypes.byref(g))
    if rc != 0:
        return f"не вышло сменить схему (код {rc})"
    return None


def read_cores(nproc: int) -> list[PROCESSOR_POWER_INFORMATION] | None:
    if nproc < 1:
        return None
    arr = (PROCESSOR_POWER_INFORMATION * nproc)()
    fn = powrprof.CallNtPowerInformation
    fn.restype = ctypes.c_long
    rc = fn(PROCESSOR_INFORMATION, None, 0, ctypes.byref(arr), ctypes.sizeof(arr))
    if rc != 0:
        return None
    return list(arr)


def logical_efficiency(nproc: int) -> list[int]:
    eff = [0] * nproc
    need = wt.ULONG(0)
    kernel32.GetSystemCpuSetInformation(None, 0, ctypes.byref(need), None, 0)
    if need.value < 16:
        return eff
    buf = (ctypes.c_ubyte * need.value)()
    got = wt.ULONG(0)
    if not kernel32.GetSystemCpuSetInformation(buf, need.value, ctypes.byref(got), None, 0):
        return eff
    off = 0
    while off + 19 <= got.value:
        size = ctypes.c_uint.from_buffer(buf, off).value
        if size < 20:
            break
        lp = buf[off + 14]
        klass = buf[off + 18]
        if lp < nproc:
            eff[lp] = int(klass)
        off += size
    return eff


def split_hybrid(eff: list[int]) -> tuple[bool, tuple[int, ...], tuple[int, ...]]:
    if not eff:
        return False, (), ()
    lo, hi = min(eff), max(eff)
    if lo == hi:
        idx = tuple(range(len(eff)))
        return False, idx, ()
    p = tuple(i for i, e in enumerate(eff) if e == hi)
    e = tuple(i for i, x in enumerate(eff) if x == lo)
    return True, p, e


def _span(cores: list[int], idx: tuple[int, ...]) -> tuple[float, int, int]:
    if not idx:
        return 0.0, 0, 0
    vals = [cores[i] for i in idx if 0 <= i < len(cores)]
    if not vals:
        return 0.0, 0, 0
    return sum(vals) / len(vals), min(vals), max(vals)


class _PdhPerf:
    def __init__(self, nproc: int) -> None:
        self._query = wt.HANDLE()
        self._ok = False
        self._primed = False
        self._hs: list[wt.HANDLE] = []
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
            return
        for i in range(nproc):
            h = wt.HANDLE()
            path = rf"\Processor Information(0,{i})\% Processor Performance"
            if pdh.PdhAddEnglishCounterW(self._query, path, 0, ctypes.byref(h)) != 0:
                pdh.PdhCloseQuery(self._query)
                return
            self._hs.append(h)
        pdh.PdhCollectQueryData(self._query)
        self._ok = True

    def read(self) -> list[float] | None:
        if not self._ok:
            return None
        if pdh.PdhCollectQueryData(self._query) != 0:
            return None
        if not self._primed:
            self._primed = True
            return None
        out: list[float] = []
        for h in self._hs:
            val = PDH_FMT_COUNTERVALUE()
            rc = pdh.PdhGetFormattedCounterValue(
                h, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100, None, ctypes.byref(val)
            )
            if rc != 0 or val.CStatus != 0:
                return None
            out.append(float(val.doubleValue))
        return out

    def close(self) -> None:
        if self._ok:
            pdh.PdhCloseQuery(self._query)
            self._ok = False


class ClockSampler:
    def __init__(self) -> None:
        self.name = cpu_name()
        self.nproc = os.cpu_count() or 1
        self.eff = logical_efficiency(self.nproc)
        self.hybrid, self.p_idx, self.e_idx = split_hybrid(self.eff)
        self._pdh = _PdhPerf(self.nproc)

    def sample(self) -> ClockSnap | None:
        rows = read_cores(self.nproc)
        if not rows:
            return None
        pstate = [int(p.CurrentMhz) for p in rows]
        if not pstate or max(pstate) <= 0:
            return None
        base = max(int(p.MaxMhz) for p in rows) or max(pstate)
        perfs = self._pdh.read()
        live = perfs is not None and len(perfs) == len(pstate)
        if live and perfs is not None:
            cores = [max(0, round(base * p / 100.0)) for p in perfs]
        else:
            cores = pstate
        p_avg, p_min, p_max = _span(cores, self.p_idx)
        e_avg, e_min, e_max = _span(cores, self.e_idx)
        psp, _, _ = _span(pstate, self.p_idx)
        pse, _, _ = _span(pstate, self.e_idx)
        scheme, gid = active_scheme()
        return ClockSnap(
            name=self.name,
            cores=cores,
            windows_max=base,
            limit=max(int(p.MhzLimit) for p in rows) or base,
            scheme=scheme,
            scheme_guid=gid,
            hybrid=self.hybrid,
            p_idx=self.p_idx,
            e_idx=self.e_idx,
            p_avg=p_avg,
            p_min=p_min,
            p_max=p_max,
            e_avg=e_avg,
            e_min=e_min,
            e_max=e_max,
            live=live,
            pstate_p=round(psp),
            pstate_e=round(pse) if self.hybrid else round(psp),
        )

    def close(self) -> None:
        self._pdh.close()
