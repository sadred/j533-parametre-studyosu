#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""J533 Veri Seti & Parametre Stüdyosu — Continental VAG MQB J533 (3Q0 907 530).

64 KB `DataFlash.bin` üzerinde **çevrimdışı** parametre düzenleme:
ZDC pasaport · MKE sürüş uyarısı · Start-Stop göstergesi · FPA sürüş profilleri ·
BEM alternatör · CP banka durumu · 773 DTC kataloğu.

Araç/CAN bağlantısı YOKTUR: yalnız dosya okur, yeni dosya yazar.

Kaynak motor (gömülü, değiştirilmeden): ContiTool — PerkTheFox
  github.com/perkthefox/mqb_contitool · vwhacking.antonperk.com
Lisans: ücretsiz / ticari satış yasak. Denizli Garaj yalnız arayüzü ekler.
"""

from __future__ import annotations

import shutil
import struct
import sys
import tkinter as tk
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

HERE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))
MEIPASS = Path(getattr(sys, "_MEIPASS", HERE))
ASSET_DIR = MEIPASS / "assets"
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else HERE
MOTOR_DIR = MEIPASS / "motor"
if str(MOTOR_DIR) not in sys.path:
    sys.path.insert(0, str(MOTOR_DIR))

from contitool import i18n  # noqa: E402
from contitool.core import analyzer, dtc_j533, zdc  # noqa: E402

i18n.set_lang("en")  # motor uyarıları İngilizce gelsin

APP_TITLE = "J533 Veri Seti & Parametre Stüdyosu"
APP_SUBTITLE = "Continental 3Q0 907 530 · DataFlash 64 KB · ZDC / MKE / Start-Stop / FPA / BEM · DTC kataloğu"
APP_VERSION = "0.1.1"
CREDIT = ("Motor: ContiTool — PerkTheFox · github.com/perkthefox/mqb_contitool  ·  arayüz: Denizli Garaj")
DFLASH_SIZE = 65536

MKE_FIELDS = [
    ("min_drive_min", "Değerlendirme için asgari sürüş (dk)", 0, 255),
    ("primary_window_min", "Ana birikim penceresi (dk)", 0, 255),
    ("short_break_min", "Kısa mola sayacı (dk)", 0, 255),
    ("full_rest_min", "Tam dinlenme / sıfırlama (dk)", 0, 255),
    ("suppress_stage1_min", "Tekrar bastırma 1 (dk)", 0, 255),
    ("suppress_stage2_min", "Tekrar bastırma 2 (dk)", 0, 255),
    ("speed_on_kmh", "Devreye girme hızı (km/h)", 0, 255),
    ("speed_off_high_kmh", "Devreden çıkma üst hız (km/h)", 0, 255),
    ("speed_hyst_low_kmh", "Alt hız histerezisi (km/h)", 0, 255),
    ("speed_urban_reset_kmh", "Şehir içi sıfırlama eşiği (km/h)", 0, 255),
    ("stage1_threshold", "Uyarı eşiği 1", 0, 255),
    ("stage2_threshold", "Uyarı eşiği 2", 0, 255),
]
SSA_FIELDS = [
    ("bap_output_mode", "BAP 0x27 çıkış modu (0-3)", 0, 3),
    ("standstill_notice_delay_ms", "Durma bildirimi gecikmesi (ms)", 0, 65535),
    ("fault_autoclear_s", "Arıza otomatik silme (sn)", 0, 65535),
    ("summary_suppress_kmh", "Özet bastırma eşiği (km/h)", 0, 65535),
]


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None):
        if self.tip is not None:
            return
        self.tip = tk.Toplevel()
        self.tip.wm_overrideredirect(True)
        lbl = tk.Label(self.tip, text=self.text, background="#2b2b2b", foreground="#eaeaea",
                       relief="solid", borderwidth=1, font=("Segoe UI", 9), justify="left", padx=6, pady=4)
        lbl.pack()
        x, y = self._anchor()
        self.tip.wm_geometry(f"+{x}+{y}")

    def _anchor(self) -> tuple[int, int]:
        return (self._x, self._y)

    def _hide(self, _e=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def tip_for(widget: tk.Widget, text: str) -> None:
    t = Tooltip(widget, text)
    original = t._anchor

    def anchor():
        return (widget.winfo_rootx() + 12, widget.winfo_rooty() + widget.winfo_height() + 4)

    t._anchor = anchor  # type: ignore[method-assign]
    _ = original


class Studio(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=8)
        self.master: tk.Tk = master
        self.path: Path | None = None
        self.raw: bytes | None = None
        self.passport = None
        self.mke = None
        self.ssa = None
        self.bem = None
        self.ds_summary = None
        self.slots: list = []
        self.swap = None
        self.credit = CREDIT
        self._build()
        self._scan_desktop()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        head = ttk.Frame(self)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        head.columnconfigure(1, weight=1)
        try:
            self._logo = tk.PhotoImage(file=str(ASSET_DIR / "logo.png"))
            ttk.Label(head, image=self._logo).grid(row=0, column=0, rowspan=2, padx=(0, 10))
        except tk.TclError:
            self._logo = None
        ttk.Label(head, text=APP_TITLE, font=("Segoe UI", 14, "bold"), foreground="#2f4f6f").grid(row=0, column=1, sticky="w")
        ttk.Label(head, text=APP_SUBTITLE, foreground="#6b6b6b").grid(row=1, column=1, sticky="w")
        ttk.Label(head, text=f"v{APP_VERSION}", foreground="#8b949e").grid(row=0, column=2, rowspan=2, sticky="e")

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(3, weight=1)
        ttk.Button(bar, text="DataFlash aç…", command=self._pick).grid(row=0, column=0)
        ttk.Button(bar, text="Yeniden yükle", command=self._reload).grid(row=0, column=1, padx=6)
        self.btn_save = ttk.Button(bar, text="💾 Kaydet (yeni .bin)", command=self._save, state="disabled")
        self.btn_save.grid(row=0, column=2)
        self.lbl_file = ttk.Label(bar, text="Dosya yüklenmedi", foreground="#1f5f8f")
        self.lbl_file.grid(row=0, column=3, sticky="w", padx=(12, 0))
        self.lbl_state = ttk.Label(bar, text="", foreground="#1f8f3d")
        self.lbl_state.grid(row=0, column=4, sticky="e")

        self.nb = ttk.Notebook(self)
        self.nb.grid(row=2, column=0, sticky="nsew")
        self.tab_sum = ttk.Frame(self.nb, padding=8)
        self.tab_pass = ttk.Frame(self.nb, padding=8)
        self.tab_mke = ttk.Frame(self.nb, padding=8)
        self.tab_ssa = ttk.Frame(self.nb, padding=8)
        self.tab_fpa = ttk.Frame(self.nb, padding=8)
        self.tab_bem = ttk.Frame(self.nb, padding=8)
        self.tab_dtc = ttk.Frame(self.nb, padding=8)
        for name, frame in (("Özet", self.tab_sum), ("ZDC Pasaport", self.tab_pass), ("MKE · Sürüş Uyarısı", self.tab_mke),
                            ("Start-Stop", self.tab_ssa), ("FPA · Sürüş Profilleri", self.tab_fpa),
                            ("BEM · Alternatör", self.tab_bem), ("DTC Kataloğu", self.tab_dtc)):
            self.nb.add(frame, text=f"  {name}  ")

        self._build_summary()
        self._build_passport()
        self._build_mke()
        self._build_ssa()
        self._build_fpa()
        self._build_bem()
        self._build_dtc()

        foot = ttk.Frame(self)
        foot.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        foot.columnconfigure(0, weight=1)
        ttk.Label(foot, text=CREDIT, foreground="#8b949e", font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w")
        ttk.Label(foot, text="araç bağlantısı yok · yalnız dosya", foreground="#8b949e",
                  font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")

    def _tree(self, parent, cols, widths, height=8):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w", stretch=True)
        tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sb.set)
        return frame, tree

    def _build_summary(self) -> None:
        f = self.tab_sum
        f.columnconfigure(0, weight=1)
        self.txt_sum = tk.Text(f, height=13, wrap="none", font=("Consolas", 9),
                               background="#0f1419", foreground="#d6dde6")
        self.txt_sum.grid(row=0, column=0, sticky="nsew")
        f.rowconfigure(0, weight=1)
        box = ttk.LabelFrame(f, text=" 12 CP bankası ", padding=6)
        box.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        frame, self.tree_cp = self._tree(box, ("Banka", "ECU", "Modül", "Durum", "CRC"), (60, 60, 300, 90, 80), 6)
        frame.pack(fill="both", expand=True)

    def _build_passport(self) -> None:
        f = self.tab_pass
        f.columnconfigure(1, weight=1)
        self.v_pn = tk.StringVar()
        self.v_ver = tk.StringVar()
        self.v_eq = tk.StringVar()
        rows = [("Dataset numarası (F1A0)", self.v_pn, "1–11 karakter, ör. V03935256AA"),
                ("Dataset sürümü (F1A1)", self.v_ver, "4 hane, ör. 0001 (0000 olamaz)"),
                ("Donanım kodu (equip, 12 bit)", self.v_eq, "Harf/rakam karışık kod, ör. 0AB veya boş bırak")]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=4)
            e = ttk.Entry(f, textvariable=var, width=28)
            e.grid(row=i, column=1, sticky="w", padx=8)
            tip_for(e, hint)
        self.lbl_pass_info = ttk.Label(f, text="", foreground="#6b6b6b")
        self.lbl_pass_info.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(f, text="Pasaport değişikliklerini uygula", command=self._apply_passport).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(f, text="CRC-32 otomatik yeniden hesaplanır; pad alanları 0xFF'e çekilir.",
                  foreground="#8b949e").grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_mke(self) -> None:
        f = self.tab_mke
        f.columnconfigure(1, weight=1)
        self.mke_vars: dict[str, tk.StringVar] = {}
        for i, (key, label, lo, hi) in enumerate(MKE_FIELDS):
            r, c = divmod(i, 2)
            ttk.Label(f, text=label).grid(row=r, column=c * 2, sticky="w", padx=(0, 6), pady=3)
            var = tk.StringVar()
            self.mke_vars[key] = var
            e = ttk.Entry(f, textvariable=var, width=8, justify="right")
            e.grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 20))
            tip_for(e, f"{lo}…{hi} arası")
        self.lbl_mke_info = ttk.Label(f, text="", foreground="#6b6b6b")
        self.lbl_mke_info.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        row = ttk.Frame(f)
        row.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(row, text="MKE değişikliklerini uygula", command=self._apply_mke).pack(side="left")
        ttk.Button(row, text="Fabrika ön ayarı '86'", command=lambda: self._mke_preset("86")).pack(side="left", padx=6)
        ttk.Button(row, text="Fabrika ön ayarı '84'", command=lambda: self._mke_preset("84")).pack(side="left")
        ttk.Label(f, text="ZDC #1 (0x0100–0x01FF) · CRC-32 blok sonunda saklanır.",
                  foreground="#8b949e").grid(row=8, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def _build_ssa(self) -> None:
        f = self.tab_ssa
        f.columnconfigure(1, weight=1)
        self.ssa_vars: dict[str, tk.StringVar] = {}
        for i, (key, label, lo, hi) in enumerate(SSA_FIELDS):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            self.ssa_vars[key] = var
            e = ttk.Entry(f, textvariable=var, width=12, justify="right")
            e.grid(row=i, column=1, sticky="w", padx=8)
            tip_for(e, f"{lo}…{hi} arası")
        self.lbl_ssa_info = ttk.Label(f, text="", foreground="#6b6b6b")
        self.lbl_ssa_info.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row = ttk.Frame(f)
        row.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(row, text="Start-Stop değişikliklerini uygula", command=self._apply_ssa).pack(side="left")
        ttk.Button(row, text="Fabrika ön ayarı '4C'", command=self._ssa_preset).pack(side="left", padx=6)
        ttk.Label(f, text="ZDC #2 (0x0200–0x09FF) · BAP LSG 0x27 gösterge veri seti.",
                  foreground="#8b949e").grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_fpa(self) -> None:
        f = self.tab_fpa
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        frame, self.tree_fpa = self._tree(f, ("Profil", "Ad", "Seçilebilir"), (80, 260, 110), 8)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(f, text="ZDC #4 (0x1340–0x243F) · sürüş profilleri ve direksiyon tuşları "
                          "(okuma; düzenleme v0.2)", foreground="#8b949e").grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _build_bem(self) -> None:
        f = self.tab_bem
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self.txt_bem = tk.Text(f, height=14, wrap="none", font=("Consolas", 9),
                               background="#0f1419", foreground="#d6dde6")
        self.txt_bem.grid(row=0, column=0, sticky="nsew")
        ttk.Label(f, text="ZDC #6 (0x2440–0x303F) · 14V LIN alternatör yönetimi (okuma).",
                  foreground="#8b949e").grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _build_dtc(self) -> None:
        f = self.tab_dtc
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)
        self.v_dtc = tk.StringVar()
        ttk.Label(f, text="Ara").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(f, textvariable=self.v_dtc)
        entry.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 6))
        entry.bind("<KeyRelease>", lambda _e: self._filter_dtc())
        frame, self.tree_dtc = self._tree(f, ("DTC", "ODIS kodu", "Açıklama (EN)"), (90, 150, 520), 16)
        frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.lbl_dtc_count = ttk.Label(f, text="", foreground="#6b6b6b")
        self.lbl_dtc_count.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._fill_dtc(dtc_j533.J533_DTCS)

    # ------------------------------------------------------------- dosya
    def _scan_desktop(self) -> None:
        for folder in (Path.home() / "Desktop", Path.home() / "Downloads"):
            if not folder.is_dir():
                continue
            for f in folder.glob("*.bin"):
                try:
                    if f.stat().st_size == DFLASH_SIZE:
                        self.lbl_file.configure(text=f"{f.name} bulundu — 'DataFlash aç…' ile yükle")
                        return
                except OSError:
                    continue

    def _pick(self) -> None:
        path = filedialog.askopenfilename(title="DataFlash.bin seç (64 KB)",
                                          filetypes=[("DataFlash dump", "*.bin"), ("Tümü", "*.*")])
        if path:
            self._load(Path(path))

    def _reload(self) -> None:
        if self.path:
            self._load(self.path)

    def _load(self, path: Path) -> None:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Açılamadı", str(exc))
            return
        if len(raw) != DFLASH_SIZE:
            if not messagebox.askyesno("Boyut uyuşmuyor",
                                       f"Beklenen {DFLASH_SIZE:,} bayt, bulunan {len(raw):,}.\n"
                                       "Yine de açılsın mı? (CodeFlash 1,5 MB ise işlem yapılamaz)"):
                return
        try:
            analyzer.validate_dflash_bytes(raw)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Geçersiz DataFlash", str(exc))
            return
        self.path, self.raw = path, raw
        self.lbl_file.configure(text=f"{path.name} · {len(raw):,} bayt")
        self.lbl_state.configure(text="")
        self.btn_save.configure(state="normal")
        self._refresh_all()

    def _refresh_all(self) -> None:
        if self.raw is None:
            return
        raw = self.raw
        try:
            self.passport = zdc.parse_zdc_passport(raw)
        except Exception:  # noqa: BLE001
            self.passport = None
        try:
            self.mke = zdc.parse_mke_block(raw)
        except Exception:  # noqa: BLE001
            self.mke = None
        try:
            self.ssa = zdc.parse_ssa_block(raw)
        except Exception:  # noqa: BLE001
            self.ssa = None
        try:
            self.bem = zdc.parse_bem_block(raw)
        except Exception:  # noqa: BLE001
            self.bem = None
        try:
            self.ds_summary = analyzer.analyze_dflash_datasets(raw)
        except Exception:  # noqa: BLE001
            self.ds_summary = None
        try:
            self.slots = analyzer.analyze_dflash(raw)
        except Exception:  # noqa: BLE001
            self.slots = []
        try:
            self.swap = analyzer.analyze_dflash_swap(raw)
        except Exception:  # noqa: BLE001
            self.swap = None
        self._render_summary()
        self._render_passport()
        self._render_mke()
        self._render_ssa()
        self._render_fpa()
        self._render_bem()

    # ------------------------------------------------------------ render
    def _render_summary(self) -> None:
        raw = self.raw or b""
        p = self.passport
        lines = [f"Dosya           : {self.path.name if self.path else '—'}",
                 f"Boyut           : {len(raw):,} bayt (64 KB DataFlash)"]
        if p:
            lines += [f"Dataset (F1A0)  : {p.dataset_pn or '—'}",
                      f"Sürüm (F1A1)    : {p.dataset_ver or '—'}",
                      f"Equip           : {p.equip_hex or '—'}  ({p.equip_ascii or '—'})",
                      f"Pasaport CRC-32 : 0x{p.crc_stored:08X} "
                      f"{'DOĞRU' if p.crc_ok else 'HATALI (0x%08X beklenir)' % p.crc_calc}",
                      f"Pad alanları    : {'temiz (0xFF)' if p.pads_clean else 'kirli'}"]
        if self.ds_summary:
            d = self.ds_summary
            lines.append(f"Ana gateway etiketi: {getattr(d, 'maingw_tag', '') or '—'}")
            sup = getattr(d, "supported_fecs", None)
            if sup:
                lines.append(f"Desteklenen FeC : {', '.join(str(s) for s in sup)}")
        if self.swap:
            s = self.swap
            lines.append(f"SWaP modülü     : {s.swap_rsa_mod.hex()[:32] + '…' if s.swap_rsa_mod else '—'}"
                         f" · e=3 {'uyumlu' if s.swap_rsa_exp_ok else 'UYUMSUZ'}")
            lines.append(f"VCRN            : {s.vcrn.hex().upper() if s.vcrn else '—'}"
                         f" · VIN: {getattr(s, 'vin', '') or '—'}")
            lines.append(f"SWaP CRC-32     : {'DOĞRU' if s.crc_ok else 'HATALI'}"
                         f" · aktif FSC: {len(getattr(s, 'active_fscs', []) or [])}"
                         f" · boş slot: {getattr(s, 'free_slots', '—')}")
        if self.mke:
            m = self.mke
            if m.empty:
                lines.append("ZDC #1 MKE      : boş")
            else:
                crc = "OK" if m.crc_ok else "HATALI"
                lines.append("ZDC #1 MKE      : etiket " + m.version_tag + " · CRC " + crc +
                             f" · {m.min_drive_min} dk / {m.speed_on_kmh}-{m.speed_off_high_kmh} km/h")
        if self.ssa:
            s2 = self.ssa
            if s2.empty:
                lines.append("ZDC #2 Start-Stop: boş")
            else:
                crc2 = "OK" if s2.crc_ok else "HATALI"
                lines.append("ZDC #2 Start-Stop: etiket " + s2.version_tag + " · CRC " + crc2 +
                             f" · BAP mod {s2.bap_output_mode}")

        self.txt_sum.configure(state="normal")
        self.txt_sum.delete("1.0", "end")
        self.txt_sum.insert("1.0", "\n".join(lines))
        self.txt_sum.configure(state="disabled")

        for row in self.tree_cp.get_children():
            self.tree_cp.delete(row)
        for st in self.slots or []:
            spec = st.spec
            etiket = f"#{spec.slot}" if spec.slot <= 12 else "Mst"
            durum = "BOŞ" if st.empty else ("DOLU · CRC OK" if st.crc_ok else "DOLU · CRC HATA")
            self.tree_cp.insert("", "end", values=(etiket, spec.ecu_addr, spec.short_en, durum,
                                                   f"0x{st.crc_stored:08X}"))

    def _render_passport(self) -> None:
        p = self.passport
        if not p:
            self.lbl_pass_info.configure(text="Pasaport okunamadı.")
            return
        self.v_pn.set(p.dataset_pn or "")
        self.v_ver.set(p.dataset_ver or "")
        self.v_eq.set(p.equip_ascii or "")
        self.lbl_pass_info.configure(
            text=f"CRC-32 0x{p.crc_stored:08X} · {'DOĞRU' if p.crc_ok else 'HATALI'} · "
                 f"pad {'temiz' if p.pads_clean else 'kirli'} · {'' if not p.empty else 'BOŞ BLOK'}")

    def _render_mke(self) -> None:
        m = self.mke
        if not m:
            self.lbl_mke_info.configure(text="ZDC #1 okunamadı.")
            return
        if m.empty:
            self.lbl_mke_info.configure(text="Blok boş (0xFF) — fabrika ön ayarı uygulanabilir.")
        else:
            self.lbl_mke_info.configure(text=f"Etiket {m.version_tag} · CRC {'DOĞRU' if m.crc_ok else 'HATALI'}"
                                             f" · makul: {'evet' if m.plausible else 'hayır'}")
        for key, _label, _lo, _hi in MKE_FIELDS:
            self.mke_vars[key].set(str(getattr(m, key, 0)))

    def _render_ssa(self) -> None:
        s = self.ssa
        if not s:
            self.lbl_ssa_info.configure(text="ZDC #2 okunamadı.")
            return
        self.lbl_ssa_info.configure(
            text=("Blok boş (0xFF) — fabrika ön ayarı uygulanabilir." if s.empty else
                  f"Etiket {s.version_tag} · CRC {'DOĞRU' if s.crc_ok else 'HATALI'}"
                  f" · etkin sebep: {s.enabled_reasons_count}"))
        for key, _label, _lo, _hi in SSA_FIELDS:
            self.ssa_vars[key].set(str(getattr(s, key, 0)))

    def _render_fpa(self) -> None:
        for row in self.tree_fpa.get_children():
            self.tree_fpa.delete(row)
        d = self.ds_summary
        pmap = getattr(d, "fpa_profile_map", None) if d else None
        mask = getattr(d, "fpa_selectable_mask", 0) if d else 0
        if not pmap:
            self.tree_fpa.insert("", "end", values=("—", "FPA veri seti bulunamadı / boş", ""))
            return
        for idx, name in (pmap.items() if hasattr(pmap, "items") else enumerate(pmap)):
            self.tree_fpa.insert("", "end", values=(f"0x{idx:02X}" if isinstance(idx, int) else idx,
                                                    str(name), "evet" if (mask >> int(idx)) & 1 else "hayır"))

    def _render_bem(self) -> None:
        self.txt_bem.configure(state="normal")
        self.txt_bem.delete("1.0", "end")
        b = self.bem
        if not b:
            self.txt_bem.insert("1.0", "BEM (ZDC #6) okunamadı.")
        else:
            out = []
            for f in getattr(type(b), "__dataclass_fields__", {}):
                if f.startswith("_"):
                    continue
                val = getattr(b, f, "")
                if isinstance(val, bytes):
                    val = val.hex().upper()[:64] + ("…" if len(val) > 32 else "")
                out.append(f"{f:28s}: {val}")
            self.txt_bem.insert("1.0", "\n".join(out) or "alan yok")
        self.txt_bem.configure(state="disabled")

    # -------------------------------------------------------------- DTC
    def _fill_dtc(self, table: dict) -> None:
        for row in self.tree_dtc.get_children():
            self.tree_dtc.delete(row)
        shown = 0
        for key in sorted(table):
            odis, ru, en = table[key]
            self.tree_dtc.insert("", "end", values=(f"0x{key:04X}", odis, en or ru))
            shown += 1
        self.lbl_dtc_count.configure(text=f"{shown} kod")

    def _filter_dtc(self) -> None:
        q = self.v_dtc.get().strip().lower()
        if not q:
            self._fill_dtc(dtc_j533.J533_DTCS)
            return
        filtered = {}
        for key, (odis, ru, en) in dtc_j533.J533_DTCS.items():
            hay = f"0x{key:04x} {key} {odis} {en} {ru}".lower()
            if q in hay:
                filtered[key] = (odis, ru, en)
        self._fill_dtc(filtered)

    # ----------------------------------------------------------- düzenle
    def _apply_passport(self) -> None:
        if self.raw is None:
            return
        try:
            self.raw = zdc.apply_zdc_passport(self.raw, dataset_pn=self.v_pn.get().strip() or None,
                                              dataset_ver=self.v_ver.get().strip() or None,
                                              equip=self.v_eq.get().strip() or None)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Pasaport uygulanamadı", str(exc))
            return
        self._refresh_all()
        self.lbl_state.configure(text="pasaport güncellendi")

    def _apply_mke(self) -> None:
        if self.raw is None or not self.mke:
            return
        cfg = self.mke
        try:
            for key, _l, lo, hi in MKE_FIELDS:
                txt = self.mke_vars[key].get().strip()
                val = int(float(txt)) if txt else 0
                if not lo <= val <= hi:
                    raise ValueError(f"{key}: {val} aralık dışı ({lo}…{hi})")
                setattr(cfg, key, val)
            self.raw = zdc.apply_mke_config(self.raw, cfg)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("MKE uygulanamadı", str(exc))
            return
        self._refresh_all()
        self.lbl_state.configure(text="MKE güncellendi")

    def _mke_preset(self, variant: str) -> None:
        if self.raw is None:
            return
        try:
            self.raw = zdc.inject_mke_preset(self.raw, variant)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ön ayar yazılamadı", str(exc))
            return
        self._refresh_all()
        self.lbl_state.configure(text=f"MKE '{variant}' ön ayarı yazıldı")

    def _apply_ssa(self) -> None:
        if self.raw is None or not self.ssa:
            return
        cfg = self.ssa
        try:
            for key, _l, lo, hi in SSA_FIELDS:
                txt = self.ssa_vars[key].get().strip()
                val = int(float(txt)) if txt else 0
                if not lo <= val <= hi:
                    raise ValueError(f"{key}: {val} aralık dışı ({lo}…{hi})")
                setattr(cfg, key, val)
            self.raw = zdc.apply_ssa_config(self.raw, cfg)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Start-Stop uygulanamadı", str(exc))
            return
        self._refresh_all()
        self.lbl_state.configure(text="Start-Stop güncellendi")

    def _ssa_preset(self) -> None:
        if self.raw is None:
            return
        try:
            self.raw = zdc.inject_ssa_preset(self.raw)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ön ayar yazılamadı", str(exc))
            return
        self._refresh_all()
        self.lbl_state.configure(text="Start-Stop '4C' ön ayarı yazıldı")

    def _save(self) -> None:
        if self.raw is None or self.path is None:
            return
        original = self.path.read_bytes()
        diff = sum(1 for a, b in zip(original, self.raw) if a != b)
        if not diff:
            messagebox.showinfo("Kaydet", "Değişiklik yok.")
            return
        out = self.path.with_name(f"{self.path.stem}_duzenlenmis.bin")
        try:
            out.write_bytes(self.raw)
        except OSError as exc:
            messagebox.showerror("Yazılamadı", str(exc))
            return
        p = zdc.parse_zdc_passport(self.raw)
        self.lbl_state.configure(text=f"✔ {diff} bayt değişti → {out.name}")
        messagebox.showinfo("Kaydedildi",
                            f"{out}\n\nDeğişen bayt: {diff}\n"
                            f"Pasaport CRC-32: 0x{p.crc_stored:08X} ({'doğru' if p.crc_ok else 'HATALI'})\n\n"
                            "Bu dosyayı tezgâhta βprogramlayıcı ile gateway'in DataFlash'ına yazabilirsin.\n"
                            "Araçta OBD'den yazma bu programın kapsamı dışında.")



def selftest(out_dir: Path) -> int:
    """Frozen exe doğrulaması: sentetik 64 KB DataFlash üret, oku, düzenle, kaydet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines_list: list[str] = []
    rc = 0
    try:
        raw = bytes([0xFF]) * DFLASH_SIZE
        raw = zdc.apply_zdc_passport(raw, dataset_pn="V03935374FG", dataset_ver="0001", equip="0AB")
        raw = zdc.inject_mke_preset(raw, "86")
        raw = zdc.inject_ssa_preset(raw)
        src = out_dir / "selftest_DataFlash.bin"
        src.write_bytes(raw)
        p = zdc.parse_zdc_passport(raw)
        m = zdc.parse_mke_block(raw)
        s = zdc.parse_ssa_block(raw)
        lines_list.append(f"pasaport={p.dataset_pn}/{p.dataset_ver} crc_ok={p.crc_ok}")
        lines_list.append(f"mke_tag={m.version_tag} mke_crc={m.crc_ok} ssa_crc={s.crc_ok}")
        cfg = zdc.parse_mke_block(raw)
        cfg.min_drive_min = 9
        new = zdc.apply_mke_config(raw, cfg)
        (out_dir / "selftest_modified.bin").write_bytes(new)
        lines_list.append(f"mke_after={zdc.parse_mke_block(new).min_drive_min}")
        lines_list.append(f"dtc_sayisi={len(dtc_j533.J533_DTCS)}")
        slots = analyzer.analyze_dflash(new)
        lines_list.append(f"cp_slot={len(slots)}")
        if not (p.crc_ok and m.crc_ok and s.crc_ok and zdc.parse_mke_block(new).min_drive_min == 9):
            rc = 1
    except Exception as exc:  # noqa: BLE001
        lines_list.append(f"HATA={exc}")
        rc = 1
    lines_list.append(f"rc={rc}")
    (out_dir / "selftest.txt").write_text("\n".join(lines_list), encoding="utf-8")
    if sys.stdout is not None:
        print("\n".join(lines_list))
    return rc


def main() -> int:
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        target = Path(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else Path.cwd()
        return selftest(target)

    root = tk.Tk()
    root.title(f"{APP_TITLE}  v{APP_VERSION}")
    try:
        root.iconbitmap(str(ASSET_DIR / "logo.ico"))
    except tk.TclError:
        pass
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    Studio(root).pack(fill="both", expand=True)
    root.geometry("1120x780")
    root.minsize(980, 680)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
