# -*- coding: utf-8 -*-
"""
Pupillab – Beta v0.6.1
Pupil-to-Iris Ratio (PIR) – Unified Application
- Caricamento bilaterale con split automatico
- Drag linee, PIR 5 classi
- Statistiche (parametriche e non parametriche)
- Grafici pubblicabili
- Report PDF con tabelle e grafici
- Salvataggio immagini annotate
- Traduzione IT/EN completa
"""

import os
import csv
import math
import datetime
import traceback
from pathlib import Path
from threading import Thread
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np
import pandas as pd
import cv2
from PIL import Image, ImageTk
from scipy import stats
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ReportLab per PDF (opzionale)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ------------------------------------------------------------
# SOGLIE UFFICIALI (dal paper, Tabella 1)
# ------------------------------------------------------------
PIR_THRESHOLDS = {
    "extreme_miosis": 0.200,
    "miosis_upper": 0.275,
    "neutral_upper": 0.459,
    "mydriasis_upper": 0.599,
}

def classify_pir(pir):
    if pir <= PIR_THRESHOLDS["extreme_miosis"]:
        return "ESTREMA MIOSI"
    elif pir <= PIR_THRESHOLDS["miosis_upper"]:
        return "MIOSI"
    elif pir <= PIR_THRESHOLDS["neutral_upper"]:
        return "NEUTRO"
    elif pir <= PIR_THRESHOLDS["mydriasis_upper"]:
        return "MIDRIASI"
    else:
        return "ESTREMA MIDRIASI"

# ------------------------------------------------------------
# Percorsi
# ------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "pir_data.csv"
IMAGE_DIR = BASE_DIR / "images"
ANNOTATED_DIR = IMAGE_DIR / "annotated"
OUTPUT_DIR = BASE_DIR / "output"
for d in [IMAGE_DIR, ANNOTATED_DIR, OUTPUT_DIR]:
    d.mkdir(exist_ok=True)

def init_database():
    if not DATA_FILE.exists():
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'case_id', 'sex', 'age', 'pmi', 'eye',
                'pupil', 'iris', 'pir', 'timestamp',
                'medications', 'substances', 'image_path', 'annotated_path'
            ])

def load_data():
    init_database()
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except:
        return []

def save_measurement(row):
    data = load_data()
    with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['case_id','sex','age','pmi','eye','pupil','iris','pir',
                      'timestamp','medications','substances','image_path','annotated_path']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in data:
            writer.writerow(r)
        writer.writerow(row)
    return True

# ------------------------------------------------------------
# Imaging helpers
# ------------------------------------------------------------
def bgr_to_photo(bgr, target_w, target_h):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    scale = min(target_w/w, target_h/h, 1.0)
    new = cv2.resize(rgb, (int(w*scale), int(h*scale)))
    return ImageTk.PhotoImage(Image.fromarray(new)), scale

def dist(a,b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

# ------------------------------------------------------------
# Stili (Pupillab palette)
# ------------------------------------------------------------
STYLES = {
    "bg": "#0a1628",
    "card": "#0f2040",
    "ink": "#e8edf5",
    "muted": "#8899bb",
    "accent": "#2a6b9e",
    "accent2": "#4d8fc9",
    "ok": "#2ecc71",
    "warn": "#f39c12",
    "bad": "#e74c3c",
    "title": ("Segoe UI", 20, "bold"),
    "h2": ("Segoe UI", 13, "bold"),
    "base": ("Segoe UI", 10),
    "bold": ("Segoe UI", 10, "bold"),
}

# ------------------------------------------------------------
# Testi (IT/EN completi)
# ------------------------------------------------------------
T_IT = {
    "app_name": "Pupillab – PIR Unified",
    "tab_measure": "Misura",
    "tab_stats": "Statistiche",
    "tab_charts": "Grafici",
    "tab_export": "Esporta",
    "run_stats": "▶ Esegui statistiche",
    "run_charts": "▶ Genera grafici",
    "open_output": "📂 Apri cartella output",
    "export_pdf": "📄 Esporta report PDF",
    "case_id": "Case ID:", "sex": "Sesso:", "age": "Età:", "pmi": "PMI (ore):",
    "meds": "Farmaci:", "subs": "Sostanze:",
    "load_img": "📷 Carica immagine", "load_bi": "📷 Carica bilaterale", "invert": "🔄 Inverti L/R",
    "save_one": "💾 Salva", "discard": "🗑 Scarta",
    "line_pupil": "✏️ Pupilla (drag)", "line_iris": "✏️ Iride (drag)",
    "line_calc": "🧮 Calcola PIR", "line_reset": "↺ Reset linee",
    "pupil_px": "Pupilla (px):", "iris_px": "Iride (px):", "pir": "PIR:",
    "no_image": "(nessuna immagine)", "eye_panel": "Occhio {eye}",
    "err_case": "Inserire Case ID", "info_none": "Nessuna misura da salvare",
    "ok_saved": "✅ Salvato {eye}", "err_img": "Impossibile caricare immagine",
    "classification": "Classificazione",
    "stats_title": "📊 ANALISI STATISTICA",
    "stats_saved": "I risultati vengono salvati in 'output/statistics_output.xlsx'",
    "charts_saved": "I grafici vengono salvati in 'output/charts_output/'",
    "export_header": "📦 Esporta tutti i dati e i report",
    "export_csv": "📄 Esporta CSV",
    "export_excel": "📊 Esporta Excel completo",
}

T_EN = {
    "app_name": "Pupillab – PIR Unified",
    "tab_measure": "Measure",
    "tab_stats": "Statistics",
    "tab_charts": "Charts",
    "tab_export": "Export",
    "run_stats": "▶ Run statistics",
    "run_charts": "▶ Generate charts",
    "open_output": "📂 Open output folder",
    "export_pdf": "📄 Export PDF report",
    "case_id": "Case ID:", "sex": "Sex:", "age": "Age:", "pmi": "PMI (h):",
    "meds": "Medications:", "subs": "Substances:",
    "load_img": "📷 Load image", "load_bi": "📷 Load bilateral", "invert": "🔄 Swap L/R",
    "save_one": "💾 Save", "discard": "🗑 Discard",
    "line_pupil": "✏️ Pupil (drag)", "line_iris": "✏️ Iris (drag)",
    "line_calc": "🧮 Compute PIR", "line_reset": "↺ Reset lines",
    "pupil_px": "Pupil (px):", "iris_px": "Iris (px):", "pir": "PIR:",
    "no_image": "(no image)", "eye_panel": "{eye} eye",
    "err_case": "Enter Case ID", "info_none": "No measurement to save",
    "ok_saved": "✅ Saved {eye}", "err_img": "Cannot load image",
    "classification": "Classification",
    "stats_title": "📊 STATISTICAL ANALYSIS",
    "stats_saved": "Results are saved to 'output/statistics_output.xlsx'",
    "charts_saved": "Charts are saved to 'output/charts_output/'",
    "export_header": "📦 Export all data and reports",
    "export_csv": "📄 Export CSV",
    "export_excel": "📊 Export full Excel",
}

# ------------------------------------------------------------
# Stato manuale (linee)
# ------------------------------------------------------------
class ManualState:
    def __init__(self):
        self.lines = {"iris": None, "pupil": None}
        self.active = None
        self.drawing = False
        self.drag_start = None
        self.drag_current = None

# ------------------------------------------------------------
# Splash Screen (copertina)
# ------------------------------------------------------------
def show_splash_and_language():
    splash = tk.Tk()
    splash.title("Pupillab – Loading")
    splash.configure(bg="#0a1628")
    splash.geometry("640x470+200+100")
    splash.resizable(False, False)

    cover_path = BASE_DIR / "cover.png"
    try:
        img = Image.open(cover_path)
        img = img.resize((520, 280), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(splash, image=photo, bg="#0a1628")
        label.image = photo
        label.pack(pady=(20, 5))
    except:
        tk.Label(splash, text="Pupillab", font=("Segoe UI", 36, "bold"),
                 fg="#e8edf5", bg="#0a1628").pack(pady=(50, 5))
        tk.Label(splash, text="Pupil-to-Iris Ratio – Unified App",
                 font=("Segoe UI", 14), fg="#8899bb", bg="#0a1628").pack()

    tk.Label(splash, text="by M. Nioi – Beta v0.6.1",
             font=("Segoe UI", 11), fg="#8899bb", bg="#0a1628").pack(pady=5)

    lang_frame = tk.Frame(splash, bg="#0a1628")
    lang_frame.pack(pady=18)
    selected_lang = {"lang": "IT"}

    def set_lang(lang):
        selected_lang["lang"] = lang
        splash.destroy()

    for lang, label, color in [("IT", "🇮🇹 Italiano", "#2a6b9e"),
                               ("EN", "🇬🇧 English", "#4d8fc9")]:
        btn = tk.Button(lang_frame, text=label, font=("Segoe UI", 11, "bold"),
                        fg="white", bg=color, width=14, height=1,
                        relief="flat", command=lambda l=lang: set_lang(l))
        btn.pack(side="left", padx=12)

    splash.mainloop()
    return selected_lang["lang"]

# ------------------------------------------------------------
# App principale
# ------------------------------------------------------------
class PupillabApp:
    def __init__(self, root, T):
        self.T = T
        self.root = root
        self.root.title(T["app_name"])
        self.root.configure(bg=STYLES["bg"])
        w = min(1360, root.winfo_screenwidth()-80)
        h = min(780, root.winfo_screenheight()-120)
        self.root.geometry(f"{w}x{h}+20+20")

        self.photo_refs = {"OD": None, "OS": None}
        self.images = {"OD":None, "OS":None}
        self.overlays = {"OD":None, "OS":None}
        self.results = {"OD":None, "OS":None}
        self.tk_scale = {"OD":1.0, "OS":1.0}
        self.manual = {"OD":ManualState(), "OS":ManualState()}
        self.active_eye = "OD"
        self.current_mode = None
        self.invert_lr = tk.BooleanVar(value=False)

        self._setup_styles()
        self._build_ui()
        self.root.bind("<Key>", self._on_key_press)
        self.root.focus_set()

    def _setup_styles(self):
        st = ttk.Style()
        try: st.theme_use('clam')
        except: pass
        st.configure('TFrame', background=STYLES["bg"])
        st.configure('TLabel', background=STYLES["bg"], foreground=STYLES["ink"])
        st.configure('Title.TLabel', background=STYLES["bg"], foreground=STYLES["ink"], font=STYLES["title"])
        st.configure('Accent.TButton', background=STYLES["accent"], foreground='white')
        st.configure('Alt.TButton', background=STYLES["ink"], foreground=STYLES["bg"])

    def _build_ui(self):
        # Header con pulsanti aggiuntivi
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=5)
        ttk.Label(header, text="Pupillab", style="Title.TLabel").pack(side="left")
        btn_frame = ttk.Frame(header); btn_frame.pack(side="right")
        ttk.Button(btn_frame, text=self.T["load_bi"], command=self.load_bilateral, style="Accent.TButton").pack(side="left", padx=2)
        ttk.Checkbutton(btn_frame, text=self.T["invert"], variable=self.invert_lr).pack(side="left", padx=4)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=5)
        self.tab_measure = ttk.Frame(self.nb)
        self.tab_stats = ttk.Frame(self.nb)
        self.tab_charts = ttk.Frame(self.nb)
        self.tab_advanced = ttk.Frame(self.nb)
        self.tab_export = ttk.Frame(self.nb)
        self.nb.add(self.tab_measure, text=self.T["tab_measure"])
        self.nb.add(self.tab_stats, text=self.T["tab_stats"])
        self.nb.add(self.tab_charts, text=self.T["tab_charts"])
        self.nb.add(self.tab_advanced, text="Analisi avanzata")
        self.nb.add(self.tab_export, text=self.T["tab_export"])
        self._build_measure_tab()
        self._build_stats_tab()
        self._build_charts_tab()
        self._build_advanced_tab()
        self._build_export_tab()

    # ---------- Analisi avanzata (modelli della revisione) ----------
    def _build_advanced_tab(self):
        frame = self.tab_advanced
        self.advanced_input = tk.StringVar()
        self.advanced_output = tk.StringVar()
        self.advanced_running = False

        box = ttk.LabelFrame(frame, text="Dataset e cartella dei risultati", padding=10)
        box.pack(fill="x", padx=12, pady=12)
        ttk.Label(box, text="File Excel (.xlsx/.xls)").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.advanced_input, width=75).grid(
            row=1, column=0, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(box, text="Sfoglia…", command=self._pick_advanced_input).grid(row=1, column=1)
        ttk.Label(box, text="Cartella output").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(box, textvariable=self.advanced_output, width=75).grid(
            row=3, column=0, sticky="ew", padx=(0, 8), pady=5
        )
        ttk.Button(box, text="Sfoglia…", command=self._pick_advanced_output).grid(row=3, column=1)
        box.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text=(
                "Esegue QC, descrittive, GEE, MixedLM con fallback OLS cluster-robust, "
                "asimmetria interoculare, cause di morte, sostanze e interazioni, ROC "
                "e regressione quantilica. Soglie: miosi ≤0,275; midriasi ≥0,460."
            ),
            wraplength=1050,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self.advanced_run_btn = ttk.Button(
            frame, text="Esegui analisi avanzata", command=self._run_advanced_analysis,
            style="Accent.TButton"
        )
        self.advanced_run_btn.pack(anchor="w", padx=16, pady=5)
        self.advanced_progress = ttk.Progressbar(frame, mode="indeterminate")
        self.advanced_progress.pack(fill="x", padx=16, pady=5)
        self.advanced_log = scrolledtext.ScrolledText(frame, wrap="word", height=20)
        self.advanced_log.pack(fill="both", expand=True, padx=16, pady=(5, 12))
        self._advanced_log_add("Pronto. Seleziona il dataset Excel e la cartella output.")

    def _pick_advanced_input(self):
        path = filedialog.askopenfilename(
            title="Seleziona dataset PIR",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Tutti i file", "*.*")],
        )
        if path:
            self.advanced_input.set(path)
            if not self.advanced_output.get():
                p = Path(path)
                self.advanced_output.set(str(p.parent / f"{p.stem}_OUTPUT"))

    def _pick_advanced_output(self):
        path = filedialog.askdirectory(title="Seleziona cartella output")
        if path:
            self.advanced_output.set(path)

    def _advanced_log_add(self, text):
        def write():
            self.advanced_log.insert("end", str(text) + ("" if str(text).endswith("\n") else "\n"))
            self.advanced_log.see("end")
        self.root.after(0, write)

    def _run_advanced_analysis(self):
        if self.advanced_running:
            return
        input_file = self.advanced_input.get().strip()
        output_dir = self.advanced_output.get().strip()
        if not input_file or not Path(input_file).is_file():
            messagebox.showerror("Pupillab", "Seleziona un file Excel valido.")
            return
        if not output_dir:
            messagebox.showerror("Pupillab", "Seleziona la cartella output.")
            return

        try:
            from editorpalloso import PIRAnalysis
        except Exception as exc:
            messagebox.showerror(
                "Pupillab",
                "Impossibile caricare il motore di analisi. Verifica che "
                "'editorpalloso.py' sia nella stessa cartella di PupilLab.py e installa "
                "le dipendenze con: pip install -r requirements.txt"
                f"\n\nDettaglio: {exc}",
            )
            return

        self.advanced_running = True
        self.advanced_run_btn.config(state="disabled")
        self.advanced_progress.start(10)
        self._advanced_log_add("Avvio analisi avanzata…")

        def finish(ok, detail):
            self.advanced_running = False
            self.advanced_progress.stop()
            self.advanced_run_btn.config(state="normal")
            if ok:
                messagebox.showinfo("Pupillab", f"Analisi completata.\nOutput: {detail}")
            else:
                messagebox.showerror("Pupillab", "Analisi non completata. Consulta il log.")

        def worker():
            try:
                PIRAnalysis(input_file, output_dir, logger=self._advanced_log_add).run_all()
                resolved = str(Path(output_dir).resolve())
                self._advanced_log_add(f"Output salvato in: {resolved}")
                self.root.after(0, lambda: finish(True, resolved))
            except Exception:
                self._advanced_log_add("ERRORE:\n" + traceback.format_exc())
                self.root.after(0, lambda: finish(False, ""))

        Thread(target=worker, daemon=True).start()

    # ---------- Tab Misura ----------
    def _build_measure_tab(self):
        left = ttk.Frame(self.tab_measure, width=320)
        left.pack(side="left", fill="y", padx=10, pady=10)
        left.pack_propagate(False)

        lf = ttk.LabelFrame(left, text="📋 " + self.T["case_id"][:-1], padding=8)
        lf.pack(fill="x", pady=4)
        self.case_id = self._entry_row(lf, self.T["case_id"])
        self.sex = ttk.Combobox(lf, values=["M","F"], state="readonly", width=5)
        self.sex.set("M"); self._label_row(lf, self.T["sex"], self.sex)
        self.age = self._entry_row(lf, self.T["age"])
        self.pmi = self._entry_row(lf, self.T["pmi"])
        self.medications = self._entry_row(lf, self.T["meds"])
        self.substances = self._entry_row(lf, self.T["subs"])

        eye_frm = ttk.Frame(lf); eye_frm.pack(fill="x", pady=4)
        ttk.Label(eye_frm, text="👁 " + self.T["eye_panel"].format(eye="")).pack(side="left")
        self.current_eye = tk.StringVar(value="OD")
        cb = ttk.Combobox(eye_frm, textvariable=self.current_eye, values=["OD","OS"], state="readonly")
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_fields())

        btn_frm = ttk.LabelFrame(left, text="✏️ " + self.T["line_pupil"][:10], padding=8)
        btn_frm.pack(fill="x", pady=6)
        ttk.Button(btn_frm, text="🔴 " + self.T["line_pupil"][4:], command=lambda: self.start_draw("pupil")).pack(fill="x", pady=2)
        ttk.Button(btn_frm, text="🟢 " + self.T["line_iris"][4:], command=lambda: self.start_draw("iris")).pack(fill="x", pady=2)
        ttk.Button(btn_frm, text=self.T["line_calc"], command=self.compute_pir, style="Accent.TButton").pack(fill="x", pady=2)
        ttk.Button(btn_frm, text=self.T["line_reset"], command=self.reset_lines).pack(fill="x", pady=2)

        res_frm = ttk.LabelFrame(left, text="📊 " + self.T["pupil_px"][:5], padding=8)
        res_frm.pack(fill="x", pady=6)
        self.pupil_var = tk.StringVar(); self._readonly_row(res_frm, self.T["pupil_px"], self.pupil_var)
        self.iris_var = tk.StringVar(); self._readonly_row(res_frm, self.T["iris_px"], self.iris_var)
        self.pir_var = tk.StringVar(); self._readonly_row(res_frm, self.T["pir"], self.pir_var)
        self.class_var = tk.StringVar(); self._readonly_row(res_frm, self.T["classification"], self.class_var)

        act = ttk.Frame(left); act.pack(fill="x", pady=4)
        ttk.Button(act, text=self.T["load_img"], command=self.load_image).pack(side="left", padx=2)
        ttk.Button(act, text=self.T["save_one"], command=self.save_measurement, style="Accent.TButton").pack(side="left", padx=2)
        ttk.Button(act, text=self.T["discard"], command=self.discard_image).pack(side="left", padx=2)

        log_frm = ttk.LabelFrame(left, text="📝 Log", padding=8)
        log_frm.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(log_frm, height=6, bg=STYLES["card"], fg=STYLES["ink"])
        self.log.pack(fill="both", expand=True)

        right = ttk.Frame(self.tab_measure)
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.canvas = tk.Canvas(right, bg="black", cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._select_line)
        self.info_lbl = ttk.Label(right, text="Scegli 'Pupilla (drag)' o 'Iride (drag)', poi clicca e trascina sul canvas.")
        self.info_lbl.pack(anchor="w", pady=4)

    def _entry_row(self, parent, label):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        e = ttk.Entry(row); e.pack(side="right", fill="x", expand=True)
        return e

    def _label_row(self, parent, label, widget):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        widget.pack(side="right")

    def _readonly_row(self, parent, label, var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=var, state="readonly").pack(side="right", fill="x", expand=True)

    def log_add(self, msg):
        self.log.insert("end", msg+"\n"); self.log.see("end")

    # ---------- Caricamento immagini ----------
    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tif")])
        if not path: return
        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("Errore", self.T["err_img"]); return
        eye = self.current_eye.get()
        self.images[eye] = img
        self.overlays[eye] = None
        self.manual[eye] = ManualState()
        self.root.update_idletasks()
        self._draw_image(eye)
        self.log_add(f"Immagine caricata per {eye}")

    def load_bilateral(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tif")])
        if not path: return
        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("Errore", self.T["err_img"]); return
        h, w = img.shape[:2]
        mid = w // 2
        left = img[:, :mid].copy()
        right = img[:, mid:].copy()
        if self.invert_lr.get():
            self.images["OD"], self.images["OS"] = right, left
        else:
            self.images["OD"], self.images["OS"] = left, right
        for e in ("OD","OS"):
            self.overlays[e] = None
            self.manual[e] = ManualState()
            self.root.update_idletasks()
            self._draw_image(e)
        self.log_add("Caricata immagine bilaterale (split automatico)")

    def discard_image(self):
        eye = self.current_eye.get()
        self.images[eye] = None
        self.overlays[eye] = None
        self.results[eye] = None
        self.manual[eye] = ManualState()
        self.photo_refs[eye] = None
        self.pupil_var.set(""); self.iris_var.set(""); self.pir_var.set(""); self.class_var.set("")
        self.canvas.delete("all")
        self.log_add(f"Immagine scartata per {eye}")

    def _draw_image(self, eye):
        img = self.overlays[eye] if self.overlays[eye] is not None else self.images[eye]
        if img is None:
            self.canvas.delete("all")
            self.photo_refs[eye] = None
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            cw, ch = 800, 600
        ph, sc = bgr_to_photo(img, cw, ch)
        self.photo_refs[eye] = ph
        self.tk_scale[eye] = sc
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, ph.width(), ph.height()))
        self.canvas.create_image(0, 0, image=ph, anchor="nw")
        self._redraw_lines(eye)

    def _redraw_lines(self, eye):
        st = self.manual[eye]
        for name, seg in st.lines.items():
            if seg is None: continue
            x1,y1,x2,y2 = seg
            col = "#ff4444" if name=="pupil" else "#44ff88"
            if st.active == name:
                col = "#ffdd44"
            self.canvas.create_line(x1, y1, x2, y2, fill=col, width=2, tags=(name,))
            for pt in [(x1,y1),(x2,y2)]:
                self.canvas.create_oval(pt[0]-3, pt[1]-3, pt[0]+3, pt[1]+3, fill=col, tags=(name,))

    # ---------- Drag linee ----------
    def start_draw(self, mode):
        eye = self.current_eye.get()
        if self.images[eye] is None:
            messagebox.showinfo("Info", "Carica prima un'immagine"); return
        self.current_mode = mode
        self.manual[eye].drawing = False
        self.manual[eye].drag_start = None
        self.info_lbl.config(text=f"Disegna la linea di {mode}. Clicca e trascina sul canvas.")

    def _on_canvas_press(self, event):
        eye = self.current_eye.get()
        if self.images[eye] is None: return
        if self.current_mode is None:
            self._select_line(event); return
        sc = self.tk_scale[eye]
        x, y = int(event.x/sc), int(event.y/sc)
        st = self.manual[eye]
        st.drawing = True
        st.drag_start = (x, y)
        st.drag_current = (x, y)
        self.canvas.delete("temp_line")
        self.canvas.create_line(x, y, x, y, fill="white", width=1, tags="temp_line")

    def _on_canvas_drag(self, event):
        eye = self.current_eye.get()
        if self.images[eye] is None: return
        st = self.manual[eye]
        if not st.drawing or self.current_mode is None: return
        sc = self.tk_scale[eye]
        x, y = int(event.x/sc), int(event.y/sc)
        st.drag_current = (x, y)
        self.canvas.delete("temp_line")
        x1,y1 = st.drag_start
        self.canvas.create_line(x1, y1, x, y, fill="white", width=2, tags="temp_line")

    def _on_canvas_release(self, event):
        eye = self.current_eye.get()
        if self.images[eye] is None: return
        st = self.manual[eye]
        if not st.drawing or self.current_mode is None: return
        st.drawing = False
        self.canvas.delete("temp_line")
        x1,y1 = st.drag_start
        sc = self.tk_scale[eye]
        x2, y2 = int(event.x/sc), int(event.y/sc)
        if dist((x1,y1),(x2,y2)) < 5:
            self.info_lbl.config(text="Linea troppo corta. Riprova.")
            return
        mode = self.current_mode
        st.lines[mode] = (x1,y1,x2,y2)
        st.active = mode
        lp = dist((x1,y1),(x2,y2)) / sc
        if mode == "pupil":
            self.pupil_var.set(f"{lp:.2f}")
        else:
            self.iris_var.set(f"{lp:.2f}")
        self.overlays[eye] = self.images[eye].copy()
        self._draw_image(eye)
        self.info_lbl.config(text=f"Linea di {mode} disegnata. Lunghezza: {lp:.2f} px. Usa le frecce per spostarla.")
        self.current_mode = None
        self.compute_pir(update_only=True)

    def _select_line(self, event):
        eye = self.current_eye.get()
        sc = self.tk_scale[eye]
        cx, cy = int(event.x/sc), int(event.y/sc)
        st = self.manual[eye]
        best = None; best_dist = 20
        for name, seg in st.lines.items():
            if seg is None: continue
            x1,y1,x2,y2 = seg
            d = self._point_segment_dist(cx, cy, x1, y1, x2, y2)
            if d < best_dist:
                best_dist = d; best = name
        if best is not None:
            st.active = best
            self._draw_image(eye)
            self.info_lbl.config(text=f"Linea '{best}' selezionata. Usa le frecce per spostare.")

    def _point_segment_dist(self, px, py, x1, y1, x2, y2):
        dx, dy = x2-x1, y2-y1
        if dx==0 and dy==0:
            return dist((px,py),(x1,y1))
        t = ((px-x1)*dx + (py-y1)*dy) / (dx*dx + dy*dy)
        t = max(0, min(1, t))
        proj_x = x1 + t*dx
        proj_y = y1 + t*dy
        return dist((px,py),(proj_x,proj_y))

    # ---------- Spostamento con frecce ----------
    def _on_key_press(self, event):
        eye = self.current_eye.get()
        st = self.manual[eye]
        if st.active is None: return
        seg = st.lines[st.active]
        if seg is None: return
        x1,y1,x2,y2 = seg
        step = 5 if event.state & 0x1 else 1
        dx = dy = 0
        if event.keysym == "Up": dy = -step
        elif event.keysym == "Down": dy = step
        elif event.keysym == "Left": dx = -step
        elif event.keysym == "Right": dx = step
        else: return
        st.lines[st.active] = (x1+dx, y1+dy, x2+dx, y2+dy)
        self.overlays[eye] = self.images[eye].copy()
        self._draw_image(eye)
        sc = self.tk_scale[eye]
        lp = dist((x1+dx,y1+dy),(x2+dx,y2+dy)) / sc
        if st.active == "pupil":
            self.pupil_var.set(f"{lp:.2f}")
        else:
            self.iris_var.set(f"{lp:.2f}")
        self.info_lbl.config(text="Linea spostata.")

    # ---------- Calcolo PIR ----------
    def compute_pir(self, update_only=False):
        eye = self.current_eye.get()
        st = self.manual[eye]
        def get_len(seg):
            if seg is None: return None
            x1,y1,x2,y2 = seg
            return dist((x1,y1),(x2,y2)) / self.tk_scale[eye]
        lp = get_len(st.lines["pupil"])
        li = get_len(st.lines["iris"])
        if lp is None or li is None or li==0:
            if not update_only:
                messagebox.showinfo("Info", "Disegna entrambe le linee (pupilla e iride).")
            return
        pir = round(lp/li, 4)
        cat = classify_pir(pir)
        self.pir_var.set(f"{pir:.4f}")
        self.class_var.set(cat)
        self.results[eye] = {"pupil":lp, "iris":li, "pir":pir, "classification":cat}
        self.log_add(f"{eye}: PIR = {pir:.4f} ({cat})")

    def reset_lines(self):
        eye = self.current_eye.get()
        self.manual[eye].lines = {"iris":None, "pupil":None}
        self.manual[eye].active = None
        self.pupil_var.set(""); self.iris_var.set(""); self.pir_var.set(""); self.class_var.set("")
        self.results[eye] = None
        self._draw_image(eye)
        self.log_add(f"Linee cancellate per {eye}")

    def _refresh_fields(self):
        eye = self.current_eye.get()
        res = self.results.get(eye)
        if res:
            self.pupil_var.set(f"{res['pupil']:.2f}")
            self.iris_var.set(f"{res['iris']:.2f}")
            self.pir_var.set(f"{res['pir']:.4f}")
            self.class_var.set(res['classification'])
        else:
            self.pupil_var.set(""); self.iris_var.set(""); self.pir_var.set(""); self.class_var.set("")
        self._draw_image(eye)

    # ---------- Salvataggio (con immagine annotata) ----------
    def save_measurement(self):
        eye = self.current_eye.get()
        if not self.case_id.get().strip():
            messagebox.showerror("Errore", self.T["err_case"]); return
        res = self.results.get(eye)
        if not res:
            messagebox.showinfo("Info", self.T["info_none"]); return

        # Salva immagine originale
        img_path = ""
        if self.images[eye] is not None:
            fn = f"{self.case_id.get()}_{eye}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            full = IMAGE_DIR / fn
            cv2.imwrite(str(full), self.images[eye])
            img_path = str(full)

        # Salva immagine annotata (con linee)
        annotated_path = ""
        if self.overlays[eye] is not None:
            fn_ann = f"{self.case_id.get()}_{eye}_annotated_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            full_ann = ANNOTATED_DIR / fn_ann
            cv2.imwrite(str(full_ann), self.overlays[eye])
            annotated_path = str(full_ann)

        row = {
            "case_id": self.case_id.get().strip(),
            "sex": self.sex.get(),
            "age": self.age.get().strip(),
            "pmi": self.pmi.get().strip(),
            "eye": eye,
            "pupil": f"{res['pupil']:.2f}",
            "iris": f"{res['iris']:.2f}",
            "pir": f"{res['pir']:.4f}",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "medications": self.medications.get().strip(),
            "substances": self.substances.get().strip(),
            "image_path": img_path,
            "annotated_path": annotated_path
        }
        save_measurement(row)
        messagebox.showinfo("OK", self.T["ok_saved"].format(eye=eye))
        self.log_add(f"Salvato: {row['case_id']} - {eye} - PIR={row['pir']}")

    # ---------- Statistiche (parametriche e non) ----------
    def _build_stats_tab(self):
        frame = self.tab_stats
        ttk.Button(frame, text=self.T["run_stats"], command=self.run_statistics, style="Accent.TButton").pack(pady=10)
        self.stats_text = scrolledtext.ScrolledText(frame, wrap="word", height=20)
        self.stats_text.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(frame, text=self.T["stats_saved"]).pack()

    def run_statistics(self):
        data = load_data()
        if not data:
            messagebox.showinfo("Info", "Nessun dato nel CSV.")
            return
        df = pd.DataFrame(data)
        df['pir'] = pd.to_numeric(df['pir'], errors='coerce')
        df['age'] = pd.to_numeric(df['age'], errors='coerce')
        df['pmi'] = pd.to_numeric(df['pmi'], errors='coerce')
        df = df.dropna(subset=['pir', 'age'])
        if len(df) < 2:
            self.stats_text.insert("end", "Dati insufficienti per l'analisi.\n")
            return
        self.stats_text.delete(1.0, "end")
        self.stats_text.insert("end", f"{self.T['stats_title']}\n")
        self.stats_text.insert("end", "="*50 + "\n\n")
        self.stats_text.insert("end", f"Numero di misure: {len(df)}\n")
        self.stats_text.insert("end", f"PIR medio: {df['pir'].mean():.4f}\n")
        self.stats_text.insert("end", f"PIR dev. std: {df['pir'].std():.4f}\n")
        self.stats_text.insert("end", f"Età media: {df['age'].mean():.1f}\n")
        self.stats_text.insert("end", f"PMI medio: {df['pmi'].mean():.1f} ore\n\n")

        # Test parametrici e non parametrici per OD/OS
        if 'eye' in df.columns:
            od = df[df['eye']=='OD']['pir']
            os = df[df['eye']=='OS']['pir']
            if len(od)>1 and len(os)>1:
                # T-test (parametrico)
                t, p_par = stats.ttest_ind(od, os, equal_var=False)
                # Wilcoxon signed-rank (non parametrico per dati appaiati)
                paired = df.pivot(index='case_id', columns='eye', values='pir').dropna()
                if 'OD' in paired and 'OS' in paired and len(paired)>1:
                    w_stat, p_non = stats.wilcoxon(paired['OD'], paired['OS'])
                    self.stats_text.insert("end", f"🔹 OD vs OS (t-test): t={t:.3f}, p={p_par:.4f}\n")
                    self.stats_text.insert("end", f"🔹 OD vs OS (Wilcoxon): W={w_stat:.1f}, p={p_non:.4f}\n")
                else:
                    self.stats_text.insert("end", f"🔹 OD vs OS (t-test): t={t:.3f}, p={p_par:.4f}\n")
                self.stats_text.insert("end", f"   OD media: {od.mean():.4f}, OS media: {os.mean():.4f}\n\n")

        # Test per sostanze (Mann-Whitney)
        if 'substances' in df.columns:
            has = df[df['substances'].notna() & (df['substances']!='')]['pir']
            none = df[df['substances'].isna() | (df['substances']=='')]['pir']
            if len(has)>1 and len(none)>1:
                t, p_par = stats.ttest_ind(has, none, equal_var=False)
                u, p_non = stats.mannwhitneyu(has, none, alternative='two-sided')
                self.stats_text.insert("end", f"🔹 Con sostanze vs senza (t-test): t={t:.3f}, p={p_par:.4f}\n")
                self.stats_text.insert("end", f"🔹 Con sostanze vs senza (Mann-Whitney): U={u:.1f}, p={p_non:.4f}\n")
                self.stats_text.insert("end", f"   Con sostanze media: {has.mean():.4f}, Senza: {none.mean():.4f}\n")

        out_file = OUTPUT_DIR / "statistics_output.xlsx"
        with pd.ExcelWriter(out_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="Dati", index=False)
            pd.DataFrame({
                "Metrica": ["N", "Media PIR", "Std PIR", "Età media", "PMI medio"],
                "Valore": [len(df), df['pir'].mean(), df['pir'].std(), df['age'].mean(), df['pmi'].mean()]
            }).to_excel(writer, sheet_name="Sintesi", index=False)
        self.stats_text.insert("end", f"\n✅ Sintesi salvata in {out_file}\n")

    # ---------- Grafici ----------
    def _build_charts_tab(self):
        frame = self.tab_charts
        ttk.Button(frame, text=self.T["run_charts"], command=self.generate_charts, style="Accent.TButton").pack(pady=10)
        self.charts_frame = ttk.Frame(frame)
        self.charts_frame.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(frame, text=self.T["charts_saved"]).pack()

    def generate_charts(self):
        data = load_data()
        if not data:
            messagebox.showinfo("Info", "Nessun dato.")
            return
        df = pd.DataFrame(data)
        df['pir'] = pd.to_numeric(df['pir'], errors='coerce')
        df['age'] = pd.to_numeric(df['age'], errors='coerce')
        df['pmi'] = pd.to_numeric(df['pmi'], errors='coerce')
        df = df.dropna(subset=['pir', 'age'])
        if len(df) < 3:
            messagebox.showinfo("Info", "Dati insufficienti per i grafici.")
            return

        fig = Figure(figsize=(12, 10), facecolor='white')
        ax1 = fig.add_subplot(221)
        ax2 = fig.add_subplot(222)
        ax3 = fig.add_subplot(223)
        ax4 = fig.add_subplot(224)

        ax1.axvspan(0, 0.200, alpha=0.25, color='darkred')
        ax1.axvspan(0.200, 0.275, alpha=0.25, color='red')
        ax1.axvspan(0.275, 0.459, alpha=0.25, color='orange')
        ax1.axvspan(0.459, 0.599, alpha=0.25, color='green')
        ax1.axvspan(0.599, 1, alpha=0.25, color='darkgreen')
        ax1.hist(df['pir'], bins=20, edgecolor='black', alpha=0.7)
        ax1.set_xlabel('PIR'); ax1.set_ylabel('Frequenza'); ax1.set_title('Distribuzione PIR')

        ax2.scatter(df['age'], df['pir'], alpha=0.6, s=30)
        z = np.polyfit(df['age'], df['pir'], 1)
        p = np.poly1d(z)
        ax2.plot(df['age'].sort_values(), p(df['age'].sort_values()), 'r--', linewidth=2)
        ax2.set_xlabel('Età'); ax2.set_ylabel('PIR'); ax2.set_title('PIR vs Età')

        if 'substances' in df.columns:
            grp = df.groupby('substances')['pir'].apply(list).to_dict()
            if len(grp)>1:
                ax3.boxplot(grp.values(), labels=grp.keys())
                ax3.set_xticklabels(ax3.get_xticklabels(), rotation=45)
                ax3.set_ylabel('PIR'); ax3.set_title('PIR per sostanza')

        if 'eye' in df.columns:
            od = df[df['eye']=='OD']['pir']; os = df[df['eye']=='OS']['pir']
            ax4.boxplot([od, os], labels=['OD','OS'])
            ax4.set_ylabel('PIR'); ax4.set_title('OD vs OS')

        fig.tight_layout()
        for widget in self.charts_frame.winfo_children():
            widget.destroy()
        canvas = FigureCanvasTkAgg(fig, master=self.charts_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        out_dir = OUTPUT_DIR / "charts_output"
        out_dir.mkdir(exist_ok=True)
        fig.savefig(out_dir / "combined_charts.png", dpi=300, bbox_inches='tight')
        fig.savefig(out_dir / "combined_charts.pdf", bbox_inches='tight')
        self.log_add(f"✅ Grafici salvati in {out_dir}")
        return fig, out_dir

    # ---------- Esporta ----------
    def _build_export_tab(self):
        frame = self.tab_export
        ttk.Label(frame, text=self.T["export_header"], font=STYLES["h2"]).pack(pady=10)
        ttk.Button(frame, text=self.T["export_csv"], command=self.export_csv, style="Accent.TButton").pack(pady=5)
        ttk.Button(frame, text=self.T["export_excel"], command=self.export_excel, style="Accent.TButton").pack(pady=5)
        ttk.Button(frame, text=self.T["export_pdf"], command=self.export_pdf, style="Accent.TButton").pack(pady=5)
        ttk.Button(frame, text=self.T["open_output"], command=self.open_output, style="Accent.TButton").pack(pady=5)

    def export_csv(self):
        data = load_data()
        if not data: return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], initialdir=OUTPUT_DIR)
        if not path: return
        pd.DataFrame(data).to_csv(path, index=False)
        messagebox.showinfo("OK", f"CSV salvato in {path}")

    def export_excel(self):
        data = load_data()
        if not data: return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")], initialdir=OUTPUT_DIR)
        if not path: return
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            pd.DataFrame(data).to_excel(writer, sheet_name="Dati", index=False)
        messagebox.showinfo("OK", f"Excel salvato in {path}")

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Errore", "ReportLab non installato. Installa con: pip install reportlab")
            return
        data = load_data()
        if not data:
            messagebox.showinfo("Info", "Nessun dato da esportare.")
            return
        fig, chart_dir = self.generate_charts()
        if fig is None:
            return
        pdf_path = OUTPUT_DIR / f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=16)
        heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12)

        story = []
        story.append(Paragraph("Pupillab – Report", title_style))
        story.append(Spacer(1, 0.5*cm))

        df = pd.DataFrame(data)
        df['pir'] = pd.to_numeric(df['pir'], errors='coerce')
        df = df.dropna(subset=['pir'])
        summary_data = [
            ["Metric", "Value"] if self.T is T_EN else ["Metrica", "Valore"],
            ["Number of measurements", str(len(df))],
            ["Mean PIR", f"{df['pir'].mean():.4f}"],
            ["PIR std dev", f"{df['pir'].std():.4f}"],
        ]
        table = Table(summary_data, colWidths=[5*cm, 4*cm])
        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.5*cm))

        chart_png = chart_dir / "combined_charts.png"
        if chart_png.exists():
            img = RLImage(str(chart_png), width=15*cm, height=12*cm)
            story.append(img)
        else:
            story.append(Paragraph("Charts not available", styles['Normal']))

        doc.build(story)
        messagebox.showinfo("OK", f"Report PDF salvato in {pdf_path}")
        self.log_add(f"PDF report salvato: {pdf_path}")

    def open_output(self):
        try:
            os.startfile(OUTPUT_DIR)
        except:
            messagebox.showinfo("Info", f"Cartella: {OUTPUT_DIR}")

# ------------------------------------------------------------
# Avvio
# ------------------------------------------------------------
def main():
    init_database()
    lang = show_splash_and_language()
    T = T_IT if lang == "IT" else T_EN
    root = tk.Tk()
    app = PupillabApp(root, T)
    root.mainloop()

if __name__ == "__main__":
    main()
