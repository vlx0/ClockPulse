"""ClockPulse GUI."""

from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import ttk

from . import __version__
from .clock import ClockSampler, ClockSnap, Scheme, list_schemes, set_scheme
from .instance import WINDOW_TITLE
from .settings import INTERVALS, load_interval, save_interval

BG = "#111111"
FG = "#ffffff"
MUTED = "#999999"
CARD = "#1a1a1a"
BAR = "#333333"
BTN = "#333333"
ACCENT = "#93c5fd"
OK = "#86efac"
HOT = "#fde68a"
PCOL = "#93c5fd"
ECOL = "#86efac"


def _mhz_color(pct: float) -> str:
    if pct >= 90:
        return OK
    if pct >= 50:
        return ACCENT
    return HOT


class ClockPulseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("560x560")
        self.minsize(480, 480)
        self.configure(bg=BG)
        self._samp = ClockSampler()
        self._sec = load_interval()
        self._hist: list[list[int]] = []
        self._job: str | None = None
        self._schemes: list[Scheme] = list_schemes()
        self._scheme_btns: dict[str, tk.Button] = {}
        self._p_lo: int | None = None
        self._p_hi: int | None = None
        self._e_lo: int | None = None
        self._e_hi: int | None = None
        self._busy_scheme = False

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=CARD, background=BTN, foreground=FG, arrowcolor=FG,
            darkcolor=CARD, lightcolor=CARD, bordercolor=BTN,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", CARD)],
            foreground=[("readonly", FG)],
            background=[("readonly", BTN)],
        )

        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=22, pady=16)

        foot = tk.Frame(pad, bg=BG)
        foot.pack(fill="x", side="bottom", pady=(8, 0))
        tk.Label(foot, text="неделя 9 · день 62", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(foot, text=f"v{__version__} · darkshade", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right")
        labels = [lab for _, lab in INTERVALS]
        self._iv_var = tk.StringVar(value=next((lab for sec, lab in INTERVALS if sec == self._sec), "1 с"))
        self._iv = ttk.Combobox(
            foot, textvariable=self._iv_var, values=labels, state="readonly",
            width=6, style="Dark.TCombobox", font=("Segoe UI", 8),
        )
        self._iv.pack(side="right", padx=(0, 10))
        self._iv.bind("<<ComboboxSelected>>", lambda _e: self._on_interval())
        tk.Label(foot, text="обновление", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        self._note = tk.Label(
            pad,
            text="Живые МГц как в Диспетчере. P-state Windows не двигается.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8),
            wraplength=500, justify="left",
        )
        self._note.pack(fill="x", side="bottom", pady=(6, 0))

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="ClockPulse", bg=BG, fg=FG, font=("Segoe UI Semibold", 20)).pack(side="left")

        self._cpu = tk.Label(
            pad, text=self._samp.name, bg=BG, fg=MUTED, font=("Segoe UI", 9),
            wraplength=500, justify="left",
        )
        self._cpu.pack(anchor="w", pady=(4, 8))

        pair = tk.Frame(pad, bg=BG)
        pair.pack(fill="x")
        self._p_box, self._p_title, self._p_mhz, self._p_sub = self._card(pair, "P-ядра", PCOL)
        self._e_box, self._e_title, self._e_mhz, self._e_sub = self._card(pair, "E-ядра", ECOL)
        if not self._samp.hybrid:
            self._e_box.pack_forget()
            self._p_box.pack(side="left", fill="x", expand=True)
            self._p_title.configure(text="ядра")

        self._mood = tk.Label(
            pad, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10),
            wraplength=500, justify="left",
        )
        self._mood.pack(anchor="w", pady=(10, 4))

        tk.Label(pad, text="такт по логическим ядрам во времени", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        self._heat = tk.Canvas(pad, height=148, bg=CARD, highlightthickness=0)
        self._heat.pack(fill="x", pady=(2, 8))

        tk.Label(pad, text="схема питания", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        schemes = tk.Frame(pad, bg=BG)
        schemes.pack(fill="x", pady=(4, 0))
        if not self._schemes:
            tk.Label(schemes, text="Windows не отдал список схем", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        for sch in self._schemes:
            btn = tk.Button(
                schemes, text=sch.name, command=lambda g=sch.guid: self._pick_scheme(g),
                bg=CARD, fg=FG, relief="flat", bd=0, cursor="hand2",
                font=("Segoe UI", 9), activebackground=BTN, activeforeground=FG,
                padx=10, pady=6,
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self._scheme_btns[sch.guid] = btn

        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._place)
        self._job = self.after(150, self._tick)

    def _card(self, parent: tk.Frame, title: str, col: str) -> tuple[tk.Frame, tk.Label, tk.Label, tk.Label]:
        box = tk.Frame(parent, bg=CARD)
        box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="x", padx=12, pady=10)
        cap = tk.Label(inner, text=title, bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        cap.pack(anchor="w")
        mhz = tk.Label(inner, text="— МГц", bg=CARD, fg=col, font=("Segoe UI Semibold", 26))
        mhz.pack(anchor="w")
        sub = tk.Label(inner, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        sub.pack(anchor="w")
        return box, cap, mhz, sub

    def _on_interval(self) -> None:
        lab = self._iv_var.get()
        for sec, name in INTERVALS:
            if name == lab:
                self._sec = sec
                save_interval(sec)
                self._schedule(0)
                return

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        w = max(320, event.width - 48)
        self._cpu.configure(wraplength=w)
        self._mood.configure(wraplength=w)
        self._note.configure(wraplength=w)
        self._draw_heat()

    def _place(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width() or 560, self.winfo_height() or 560
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 6}")

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _close(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self._samp.close()
        self.destroy()

    def _schedule(self, delay_ms: int | None = None) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        ms = int(self._sec * 1000) if delay_ms is None else delay_ms
        self._job = self.after(max(0, ms), self._tick)

    def _pick_scheme(self, gid: str) -> None:
        if self._busy_scheme:
            return
        self._busy_scheme = True
        err = set_scheme(gid)
        self._busy_scheme = False
        if err:
            self._mood.configure(text=err, fg=HOT)
            return
        self._schedule(0)

    def _tick(self) -> None:
        if not self._alive():
            return
        try:
            snap = self._samp.sample()
        except Exception:
            snap = None
        if snap is None:
            self._mood.configure(text="Windows не отдал частоту процессора.", fg=HOT)
        else:
            self._apply(snap)
        self._schedule()

    def _apply(self, snap: ClockSnap) -> None:
        if not snap.live:
            self._mood.configure(text="жду счётчик частоты…", fg=MUTED)
            return
        cap = snap.windows_max or snap.limit or 1
        if snap.hybrid:
            self._p_lo = snap.p_min if self._p_lo is None else min(self._p_lo, snap.p_min)
            self._p_hi = snap.p_max if self._p_hi is None else max(self._p_hi, snap.p_max)
            self._e_lo = snap.e_min if self._e_lo is None else min(self._e_lo, snap.e_min)
            self._e_hi = snap.e_max if self._e_hi is None else max(self._e_hi, snap.e_max)
            self._p_mhz.configure(text=f"{snap.p_avg:.0f} МГц", fg=PCOL)
            self._e_mhz.configure(text=f"{snap.e_avg:.0f} МГц", fg=ECOL)
            self._p_sub.configure(
                text=f"{len(snap.p_idx)} пот. · сессия {self._p_lo}–{self._p_hi}"
            )
            self._e_sub.configure(
                text=f"{len(snap.e_idx)} пот. · сессия {self._e_lo}–{self._e_hi}"
            )
            split = f"P {snap.p_min}–{snap.p_max}  ·  E {snap.e_min}–{snap.e_max}"
        else:
            self._p_lo = snap.p_min if self._p_lo is None else min(self._p_lo, snap.p_min)
            self._p_hi = snap.p_max if self._p_hi is None else max(self._p_hi, snap.p_max)
            self._p_mhz.configure(text=f"{snap.p_avg:.0f} МГц", fg=PCOL)
            self._p_sub.configure(text=f"сессия {self._p_lo}–{self._p_hi}  ·  потолок {cap}")
            split = f"{snap.p_min}–{snap.p_max} МГц"
        if snap.live:
            mood = f"{split}. База {cap} МГц × % производительности."
        else:
            mood = f"{split}. Жду счётчик частоты…"
        if snap.scheme:
            mood = f"{snap.scheme}. " + mood
        self._mood.configure(text=mood, fg=FG)
        for gid, btn in self._scheme_btns.items():
            on = gid == snap.scheme_guid
            btn.configure(bg=ACCENT if on else CARD, fg=BG if on else FG)
        self._hist.append(snap.cores)
        self._hist = self._hist[-90:]
        self._draw_heat()

    def _draw_heat(self) -> None:
        c = self._heat
        c.delete("all")
        frames = self._hist
        if not frames:
            return
        ncore = len(frames[0])
        if ncore < 1:
            return
        hybrid = self._samp.hybrid
        p_idx = set(self._samp.p_idx)
        order = list(self._samp.p_idx) + list(self._samp.e_idx) if hybrid else list(range(ncore))
        left = 22 if hybrid else 4
        w = max(40, c.winfo_width())
        h = int(c.cget("height"))
        gap = 4 if hybrid else 0
        rows = len(order)
        row_h = max(3, (h - 6 - gap) / rows)
        col_w = max(1.0, (w - left - 4) / max(1, len(frames)))
        cap = max(max(fr) for fr in frames) or 1
        y = 4
        for i, lp in enumerate(order):
            if hybrid and i == len(self._samp.p_idx):
                y += gap
            if hybrid and i == 0:
                c.create_text(10, y + row_h * len(self._samp.p_idx) / 2, text="P", fill=PCOL, font=("Segoe UI", 8))
            if hybrid and i == len(self._samp.p_idx):
                c.create_text(10, y + row_h * len(self._samp.e_idx) / 2, text="E", fill=ECOL, font=("Segoe UI", 8))
            for t, fr in enumerate(frames):
                mhz = fr[lp] if lp < len(fr) else 0
                pct = 100.0 * mhz / cap
                x0 = left + t * col_w
                c.create_rectangle(
                    x0, y, x0 + col_w + 0.5, y + row_h - 1,
                    fill=_mhz_color(pct), outline="",
                )
            y += row_h


def run() -> None:
    ClockPulseApp().mainloop()
