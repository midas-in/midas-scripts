#!/usr/bin/env python3
"""
Anonymizer Pro – Optimized for Character Detection Only
══════════════════════════════════════════════════════════════════
KEY CHANGES vs original
────────────────────────────────────────────────────────────────
WHITE LABEL (paper sticker) DETECTOR — rejection filters:
  ① Circularity guard   → kills specular reflections (near-circle)
  ② Solidity guard      → kills teeth arcs (non-convex contours)
  ③ Edge-sharpness gate → paper has hard rectangular borders
  ④ Corner-bias gate    → labels live near image edges, not center
  ⑤ Internal variance   → blank-white reflection has near-zero σ

HANDWRITTEN TEXT — two-stage approach:
  Stage A: locate white-label ROI (improved detector above)
  Stage B: CLAHE + adaptive-threshold pre-process the ROI, then
           run docTR on the enhanced crop at full scale

OCR ZONE EXPANSION:
  Any confirmed white-label bounding box is passed to docTR as an
  explicit high-priority crop (full res, no PHI-zone gating).

TEETH / REFLECTION GUARD in PHI-zone OCR:
  Rejects word boxes whose pixel region looks like a specular
  highlight (expanded ROI sampling for stable std on small boxes).

RULER / SCALE-BAR GUARD:
  Sobel-X heuristic detects tick-mark columns in the bottom 20%
  of the image; pure-digit OCR hits inside that strip are dropped.

PHI KEYWORD LIST (NEW):
  Place PHI_KEYWORDS.txt inside INPUT_DIR.
  Syntax — one entry per line:
    Plain text  → case-insensitive "contains" match
    EXACT:word  → whole-token exact match (case-insensitive)
    REGEX:pat   → full Python regular expression (case-insensitive)
  Lines starting with # and blank lines are ignored.
  Keyword hits bypass the PHI-zone gate entirely, catching PHI
  anywhere in the image (centre labels, specimen stickers, etc.).

FIX — ACQUISITION PARAM STRIP (D3):
  Image-aware: only masks the strip when it actually contains
  text-like content. Set MASK_ACQ_PARAMS = False to disable.

FIX — detect_ocr() DUPLICATE LOOP:
  Previous version had two separate for-loops; the first returned
  early and the keyword / ruler logic never ran. Now unified into
  one loop with all guards applied in the correct order.

STARTUP DIALOG (NEW):
  On launch a folder-picker dialog appears so the user can choose
  the input and (optionally) output directories without editing
  the source code.  Falls back to the DEFAULT_INPUT_DIR /
  DEFAULT_OUTPUT_DIR constants below if the dialog is skipped.
══════════════════════════════════════════════════════════════════
"""

import os, sys, copy, re as _re, shutil, csv, cv2
import numpy as np
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime

from doctr.io import DocumentFile
from doctr.models import ocr_predictor

# ══════════════════════════════════════════════════════════════════
# CONFIG  (used as fallback defaults if the startup dialog is closed)
# ══════════════════════════════════════════════════════════════════

DEFAULT_INPUT_DIR  = r"C:\Users\Admin\Desktop\YASH Script\APPS\Model_case"
DEFAULT_OUTPUT_DIR = ""          # empty → save next to originals (input folder)

# These are set at runtime by the startup dialog:
INPUT_DIR  = DEFAULT_INPUT_DIR
OUTPUT_DIR = DEFAULT_OUTPUT_DIR   # may remain "" → means "same as INPUT_DIR"

# CSV paths are derived from INPUT_DIR after the dialog confirms:
DETECTION_CSV  = ""
ANONYMIZED_CSV = ""

# ── OCR ───────────────────────────────────────────────────────────
PADDING              = 3
DOCTR_MIN_W          = 12
DOCTR_MIN_H          = 8
DOCTR_CONF_THRESHOLD = 0.30   # lower → catch faint handwriting

# ── PHI zones (corners / edges where patient info lives) ──────────
PHI_TOP_FRAC  = 0.16
PHI_BOT_FRAC  = 0.09
PHI_SIDE_FRAC = 0.25

# ── White-label detector ──────────────────────────────────────────
LABEL_MIN_AREA        = 2_500
LABEL_MAX_AREA_F      = 0.25     # fraction of total image area
LABEL_WHITE_THRESH    = 195      # minimum mean brightness
LABEL_ASPECT_MAX      = 6.0      # w/h ratio cap

LABEL_CIRCULARITY_MAX = 0.72     # reflections ≈ 0.85–1.0 → reject
LABEL_SOLIDITY_MIN    = 0.80     # teeth arcs ~0.5–0.7 → reject
LABEL_EDGE_DENSITY_MIN= 0.02     # fraction of edge pixels inside ROI
LABEL_INTERNAL_STD_MIN= 5.0      # blank reflection std ~2–4 → reject
LABEL_BORDER_MARGIN_F = 0.22     # label must overlap this border fraction

# ── Acquisition params strip ──────────────────────────────────────
MASK_ACQ_PARAMS   = False        # disable for oral-cavity datasets
ACQ_COL_WIDTH_F   = 0.10
ACQ_ROW_START_F   = 0.12
ACQ_ROW_END_F     = 0.35
ACQ_EDGE_DENSITY_MIN = 0.06
ACQ_STD_MIN          = 15.0

# ── Specular-pixel guard ──────────────────────────────────────────
SPECULAR_MEAN_MIN = 230          # bright AND uniform → reflection
SPECULAR_STD_MAX  = 20
SPECULAR_MIN_AREA = 25 * 25      # large boxes are always real text

# ── Misc ──────────────────────────────────────────────────────────
NMS_IOU       = 0.3
MAX_DISPLAY_W = 1280
MAX_DISPLAY_H = 800

# ══════════════════════════════════════════════════════════════════
# STARTUP DIALOG — choose input / output folders before scanning
# ══════════════════════════════════════════════════════════════════

class StartupDialog:
    """
    Modal dialog shown at launch so the user can pick folders without
    editing the script.  Sets the global INPUT_DIR / OUTPUT_DIR and
    derives the CSV paths.  Closes itself on confirm or cancel.

    Returns True if the user confirmed, False if cancelled/closed.
    """

    def __init__(self):
        self.confirmed = False

        self.root = tk.Tk()
        self.root.title("Anonymizer Pro — Setup")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(False, False)

        # Centre on screen
        w, h = 620, 280
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.root.mainloop()

    # ── UI ────────────────────────────────────────────────────────

    def _build(self):
        PAD = dict(padx=16, pady=6)

        # Title
        tk.Label(self.root,
                 text="Anonymizer Pro",
                 bg="#1a1a2e", fg="#e0e0e0",
                 font=("Courier New", 14, "bold")).pack(anchor="w", padx=16, pady=(18, 0))
        tk.Label(self.root,
                 text="Select folders before scanning",
                 bg="#1a1a2e", fg="#7ec8e3",
                 font=("Courier New", 10)).pack(anchor="w", padx=16, pady=(0, 12))

        # ── Input folder ──────────────────────────────────────────
        frm_in = tk.Frame(self.root, bg="#1a1a2e")
        frm_in.pack(fill="x", **PAD)
        tk.Label(frm_in, text="Input folder  (images to anonymize) *",
                 bg="#1a1a2e", fg="#aaa",
                 font=("Courier New", 9)).pack(anchor="w")
        row_in = tk.Frame(frm_in, bg="#1a1a2e")
        row_in.pack(fill="x", pady=(2, 0))
        self.var_in = tk.StringVar(value=DEFAULT_INPUT_DIR)
        tk.Entry(row_in, textvariable=self.var_in,
                 font=("Courier New", 9), width=62,
                 bg="#0d0d1a", fg="#e0e0e0",
                 insertbackground="white",
                 relief="flat", bd=4).pack(side="left", fill="x", expand=True)
        tk.Button(row_in, text="Browse…",
                  command=self._browse_in,
                  bg="#0f3460", fg="white",
                  font=("Courier New", 9), relief="flat",
                  padx=10, pady=4, cursor="hand2").pack(side="left", padx=(6, 0))

        # ── Output folder ─────────────────────────────────────────
        frm_out = tk.Frame(self.root, bg="#1a1a2e")
        frm_out.pack(fill="x", **PAD)
        tk.Label(frm_out, text="Output folder  (optional — leave blank to save next to originals)",
                 bg="#1a1a2e", fg="#aaa",
                 font=("Courier New", 9)).pack(anchor="w")
        row_out = tk.Frame(frm_out, bg="#1a1a2e")
        row_out.pack(fill="x", pady=(2, 0))
        self.var_out = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        tk.Entry(row_out, textvariable=self.var_out,
                 font=("Courier New", 9), width=62,
                 bg="#0d0d1a", fg="#e0e0e0",
                 insertbackground="white",
                 relief="flat", bd=4).pack(side="left", fill="x", expand=True)
        tk.Button(row_out, text="Browse…",
                  command=self._browse_out,
                  bg="#0f3460", fg="white",
                  font=("Courier New", 9), relief="flat",
                  padx=10, pady=4, cursor="hand2").pack(side="left", padx=(6, 0))

        # ── Buttons ───────────────────────────────────────────────
        btn_row = tk.Frame(self.root, bg="#1a1a2e")
        btn_row.pack(fill="x", padx=16, pady=(10, 16))
        tk.Button(btn_row, text="Cancel",
                  command=self._cancel,
                  bg="#2c2c54", fg="#aaa",
                  font=("Courier New", 10), relief="flat",
                  padx=14, pady=7, cursor="hand2").pack(side="right", padx=(6, 0))
        tk.Button(btn_row, text="▶  Start Scanning",
                  command=self._confirm,
                  bg="#27ae60", fg="white",
                  font=("Courier New", 10, "bold"), relief="flat",
                  padx=18, pady=7, cursor="hand2").pack(side="right")

    # ── Actions ───────────────────────────────────────────────────

    def _browse_in(self):
        d = filedialog.askdirectory(
            title="Select input folder",
            initialdir=self.var_in.get() or os.path.expanduser("~"))
        if d:
            self.var_in.set(d)

    def _browse_out(self):
        d = filedialog.askdirectory(
            title="Select output folder (or cancel to use input folder)",
            initialdir=self.var_out.get() or self.var_in.get() or os.path.expanduser("~"))
        if d:
            self.var_out.set(d)

    def _confirm(self):
        in_dir  = self.var_in.get().strip()
        out_dir = self.var_out.get().strip()

        if not in_dir:
            messagebox.showerror("Missing input",
                                 "Please select an input folder.", parent=self.root)
            return
        if not os.path.isdir(in_dir):
            messagebox.showerror("Not found",
                                 f"Input folder does not exist:\n{in_dir}", parent=self.root)
            return
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Cannot create",
                                     f"Output folder could not be created:\n{e}", parent=self.root)
                return

        # Commit to globals
        global INPUT_DIR, OUTPUT_DIR, DETECTION_CSV, ANONYMIZED_CSV, PHI_KEYWORDS_FILE
        INPUT_DIR       = in_dir
        OUTPUT_DIR      = out_dir      # "" means same as input
        DETECTION_CSV   = os.path.join(INPUT_DIR, "detection_log.csv")
        ANONYMIZED_CSV  = os.path.join(INPUT_DIR, "anonymized_log.csv")
        PHI_KEYWORDS_FILE = os.path.join(INPUT_DIR, "phi_keywords.txt")

        self.confirmed = True
        self.root.destroy()

    def _cancel(self):
        self.confirmed = False
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════
# MODEL  (loaded after dialog so the window appears immediately)
# ══════════════════════════════════════════════════════════════════

# Deferred — see main()
model = None

# ══════════════════════════════════════════════════════════════════
# PHI KEYWORD LOADER
# ══════════════════════════════════════════════════════════════════

PHI_KEYWORDS_FILE = os.path.join(DEFAULT_INPUT_DIR, "phi_keywords.txt")
PHI_MATCHERS      = []    # populated after dialog confirms INPUT_DIR


def load_phi_keywords(path: str):
    """
    Load PHI_KEYWORDS.txt and return a list of (kind, label, matcher_fn) tuples.
    Returns an empty list if the file does not exist — the tool works
    normally without it (PHI-zone detection still runs).

    Supported syntax:
      Plain text   → case-insensitive "contains" match
      EXACT:token  → whole-token boundary match (case-insensitive)
      REGEX:pat    → full Python regular expression (case-insensitive)
    """
    if not os.path.exists(path):
        print(f"[INFO] No PHI_KEYWORDS.txt found at {path} — keyword matching disabled.")
        return []

    matchers = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.upper().startswith("REGEX:"):
                pattern = line[6:].strip()
                try:
                    compiled = _re.compile(pattern, _re.IGNORECASE)
                    matchers.append(
                        ("regex", pattern,
                         lambda w, c=compiled: bool(c.search(w))))
                except _re.error as e:
                    print(f"  [WARN] Bad regex in keywords file: {pattern!r} → {e}")

            elif line.upper().startswith("EXACT:"):
                token = line[6:].strip()
                compiled = _re.compile(
                    r"(?<![A-Za-z0-9])" + _re.escape(token) + r"(?![A-Za-z0-9])",
                    _re.IGNORECASE)
                matchers.append(
                    ("exact", token,
                     lambda w, c=compiled: bool(c.search(w))))

            else:
                needle = line.lower()
                matchers.append(
                    ("contains", needle,
                     lambda w, n=needle: n in w.lower()))

    print(f"[INFO] Loaded {len(matchers)} PHI keyword matcher(s) from {path}")
    return matchers


def word_matches_keyword(word_str: str) -> bool:
    """
    Return True if word_str matches ANY entry in PHI_KEYWORDS.txt.
    Matching is case-insensitive; whitespace is stripped first.
    Keyword hits bypass the PHI-zone gate in detect_ocr().
    """
    w = word_str.strip()
    if not w or not PHI_MATCHERS:
        return False
    for (_kind, _label, fn) in PHI_MATCHERS:
        if fn(w):
            return True
    return False

# ══════════════════════════════════════════════════════════════════
# GEOMETRY HELPERS
# ══════════════════════════════════════════════════════════════════

def clamp_box(x, y, w, h, shape):
    H, W = shape[:2]
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return (x, y, w, h)

def pad_box(x, y, w, h, shape):
    return clamp_box(x - PADDING, y - PADDING,
                     w + 2 * PADDING, h + 2 * PADDING, shape)

def box_in_phi_zone(x, y, w, h, img_shape):
    H, W = img_shape[:2]
    cx, cy = x + w / 2, y + h / 2
    return (
        cy < H * PHI_TOP_FRAC or
        cy > H * (1 - PHI_BOT_FRAC) or
        (cy > H * 0.72 and cx < W * PHI_SIDE_FRAC) or
        (cy > H * 0.72 and cx > W * (1 - PHI_SIDE_FRAC))
    )

def merge_boxes(boxes):
    if not boxes:
        return []
    scores = [1.0] * len(boxes)
    idx = cv2.dnn.NMSBoxes(boxes, scores, 0.0, NMS_IOU)
    if len(idx) == 0:
        return []
    return [boxes[i] for i in idx.flatten()]

def boxes_to_str(boxes):
    return "|".join(f"{x},{y},{w},{h}" for x, y, w, h in boxes)

# ══════════════════════════════════════════════════════════════════
# SPECULAR / TEETH GUARD
# ══════════════════════════════════════════════════════════════════

def is_specular(gray_img, x, y, w, h):
    if w * h > SPECULAR_MIN_AREA:
        return False
    PAD = 6
    H_img, W_img = gray_img.shape[:2]
    sx = max(0,     x - PAD);  sy = max(0,     y - PAD)
    ex = min(W_img, x + w + PAD); ey = min(H_img, y + h + PAD)
    roi = gray_img[sy:ey, sx:ex]
    if roi.size == 0:
        return False
    m = float(np.mean(roi))
    s = float(np.std(roi))
    return m > SPECULAR_MEAN_MIN and s < SPECULAR_STD_MAX

# ══════════════════════════════════════════════════════════════════
# RULER / SCALE-BAR GUARD
# ══════════════════════════════════════════════════════════════════

def detect_ruler_strip(img_bgr):
    H, W = img_bgr.shape[:2]
    search_y = int(H * 0.80)
    strip    = img_bgr[search_y:, :]
    gray     = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sobelx   = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    col_mean = np.mean(np.abs(sobelx), axis=0)
    threshold  = np.percentile(col_mean, 70) * 1.5
    ruler_cols = col_mean > threshold
    runs, in_run, start = [], False, 0
    for i, v in enumerate(ruler_cols):
        if v and not in_run:
            start, in_run = i, True
        elif not v and in_run:
            runs.append((start, i - start))
            in_run = False
    if in_run:
        runs.append((start, len(ruler_cols) - start))
    long_runs = [r for r in runs if r[1] > 80]
    if not long_runs:
        return None
    x0 = min(r[0] for r in long_runs)
    x1 = max(r[0] + r[1] for r in long_runs)
    return (x0, search_y, x1 - x0, H - search_y)

# ══════════════════════════════════════════════════════════════════
# DETECTOR 1 — docTR OCR  (unified single-pass loop)
# ══════════════════════════════════════════════════════════════════

def _run_doctr_on_image(img_path):
    try:
        doc    = DocumentFile.from_images([img_path])
        result = model(doc)
    except Exception as e:
        print(f"  [docTR ERROR] {e}")
        return []
    page   = result.pages[0]
    h_dim, w_dim = page.dimensions
    words  = []
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                words.append((word, h_dim, w_dim))
    return words

def _run_doctr_on_crop(gray_crop, offset_x, offset_y, full_shape):
    rgb_crop = cv2.cvtColor(gray_crop, cv2.COLOR_GRAY2RGB)
    tmp_path = "/tmp/_label_crop_doctr.png"
    cv2.imwrite(tmp_path, rgb_crop)
    try:
        doc    = DocumentFile.from_images([tmp_path])
        result = model(doc)
    except Exception as e:
        print(f"  [docTR-crop ERROR] {e}")
        return []
    page   = result.pages[0]
    h_dim, w_dim = page.dimensions
    boxes  = []
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                if word.confidence < DOCTR_CONF_THRESHOLD:
                    continue
                (x1, y1), (x2, y2) = word.geometry
                x  = int(x1 * w_dim) + offset_x
                y  = int(y1 * h_dim) + offset_y
                bw = int((x2 - x1) * w_dim)
                bh = int((y2 - y1) * h_dim)
                if bw < DOCTR_MIN_W or bh < DOCTR_MIN_H:
                    continue
                boxes.append(clamp_box(x, y, bw, bh, full_shape))
    return boxes

def preprocess_for_handwriting(gray_roi):
    clahe    = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_roi)
    binary   = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10)
    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)
    return binary


def detect_ocr(img_path, img_bgr):
    gray        = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    words       = _run_doctr_on_image(img_path)
    ruler_bbox  = detect_ruler_strip(img_bgr)
    boxes       = []
    kw_hits     = 0

    for (word, h_dim, w_dim) in words:
        if word.confidence < DOCTR_CONF_THRESHOLD:
            continue
        (x1, y1), (x2, y2) = word.geometry
        x  = int(x1 * w_dim);  y  = int(y1 * h_dim)
        bw = int((x2 - x1) * w_dim)
        bh = int((y2 - y1) * h_dim)
        if bw < DOCTR_MIN_W or bh < DOCTR_MIN_H:
            continue
        if is_specular(gray, x, y, bw, bh):
            continue
        if ruler_bbox is not None:
            rx, ry, rw, rh = ruler_bbox
            cx, cy = x + bw / 2, y + bh / 2
            if (rx <= cx <= rx + rw and ry <= cy <= ry + rh
                    and word.value.strip().replace(".", "").isdigit()):
                continue
        in_zone  = box_in_phi_zone(x, y, bw, bh, img_bgr.shape)
        kw_match = word_matches_keyword(word.value)
        if not in_zone and not kw_match:
            continue
        if kw_match:
            kw_hits += 1
            print(f"    [KW HIT] '{word.value.strip()}'  "
                  f"conf={word.confidence:.2f}  "
                  f"zone={'YES' if in_zone else 'NO (centre hit)'}  "
                  f"box=({x},{y},{bw},{bh})")
        boxes.append((x, y, bw, bh))

    return boxes, kw_hits

# ══════════════════════════════════════════════════════════════════
# DETECTOR 2 — White paper label finder
# ══════════════════════════════════════════════════════════════════

def _contour_circularity(cnt):
    area = cv2.contourArea(cnt)
    peri = cv2.arcLength(cnt, True)
    if peri < 1:
        return 0.0
    return 4 * np.pi * area / (peri ** 2)

def _contour_solidity(cnt):
    area      = cv2.contourArea(cnt)
    hull_area = cv2.contourArea(cv2.convexHull(cnt))
    if hull_area < 1:
        return 0.0
    return area / hull_area

def _near_border(x, y, w, h, img_shape):
    H, W = img_shape[:2]
    mx, my = int(W * LABEL_BORDER_MARGIN_F), int(H * LABEL_BORDER_MARGIN_F)
    return (x < mx or y < my or
            (x + w) > (W - mx) or
            (y + h) > (H - my))

def _edge_density(gray_roi):
    edges = cv2.Canny(gray_roi, 50, 150)
    return float(np.count_nonzero(edges)) / max(edges.size, 1)

def detect_white_labels(img_bgr):
    H, W = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, LABEL_WHITE_THRESH, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 9))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    max_area = H * W * LABEL_MAX_AREA_F
    label_boxes, label_rois = [], []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        roi = gray[y:y + h, x:x + w]
        if np.mean(roi) < LABEL_WHITE_THRESH * 0.85:
            continue
        if w * h < LABEL_MIN_AREA or w * h > max_area:
            continue
        if w / (h + 1e-6) > LABEL_ASPECT_MAX:
            continue
        if _contour_circularity(c) > LABEL_CIRCULARITY_MAX:
            continue
        if _contour_solidity(c) < LABEL_SOLIDITY_MIN:
            continue
        if np.std(roi) < LABEL_INTERNAL_STD_MIN:
            if _edge_density(roi) < LABEL_EDGE_DENSITY_MIN * 2:
                continue
        if _edge_density(roi) < LABEL_EDGE_DENSITY_MIN:
            continue
        if not _near_border(x, y, w, h, img_bgr.shape):
            continue
        label_boxes.append((x, y, w, h))
        label_rois.append((roi.copy(), x, y))
    return label_boxes, label_rois

# ══════════════════════════════════════════════════════════════════
# DETECTOR 3 — Acquisition parameter strip  (image-aware)
# ══════════════════════════════════════════════════════════════════

def detect_acq_params(img_shape, img_bgr=None):
    if not MASK_ACQ_PARAMS:
        return []
    H, W = img_shape[:2]
    x = 0
    y = int(H * ACQ_ROW_START_F)
    w = int(W * ACQ_COL_WIDTH_F)
    h = int(H * (ACQ_ROW_END_F - ACQ_ROW_START_F))
    if img_bgr is not None:
        strip = img_bgr[y:y + h, x:x + w]
        if strip.size == 0:
            return []
        gray_strip = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
        if (_edge_density(gray_strip) < ACQ_EDGE_DENSITY_MIN or
                float(np.std(gray_strip)) < ACQ_STD_MIN):
            return []
    return [(x, y, w, h)]

# ══════════════════════════════════════════════════════════════════
# AUTO-DETECT ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════

def auto_detect(img_path):
    img = cv2.imread(img_path)
    if img is None:
        return [], None, 0
    d1, kw_hits = detect_ocr(img_path, img)
    label_boxes, label_rois = detect_white_labels(img)
    d2 = label_boxes
    d2b = []
    for (roi_gray, ox, oy) in label_rois:
        processed  = preprocess_for_handwriting(roi_gray)
        word_boxes = _run_doctr_on_crop(processed, ox, oy, img.shape)
        d2b.extend(word_boxes)
    d3 = detect_acq_params(img.shape, img)
    all_boxes = d1 + d2 + d2b + d3
    merged    = merge_boxes(all_boxes)
    padded    = [pad_box(x, y, w, h, img.shape) for x, y, w, h in merged]
    return padded, img, kw_hits

# ══════════════════════════════════════════════════════════════════
# PHASE 1 — BATCH AUTO-DETECT + CSV LOG
# ══════════════════════════════════════════════════════════════════

def phase1_detect(image_paths):
    print(f"\n{'═' * 60}")
    print(f"  PHASE 1 — Auto-detection on {len(image_paths)} image(s)")
    print(f"{'═' * 60}")

    detected = []
    with open(DETECTION_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "original_path", "filename",
            "num_auto_boxes", "auto_boxes_coords",
            "keyword_hits",
            "detected_at",
        ])
        for path in image_paths:
            name = os.path.basename(path)
            print(f"  Scanning  {name} …", end=" ", flush=True)
            boxes, img, kw_hits = auto_detect(path)
            if not boxes:
                print("no detections")
                continue
            kw_tag = f"  [{kw_hits} keyword hit(s)]" if kw_hits else ""
            print(f"{len(boxes)} box(es) detected{kw_tag}")
            row = {
                "original_path": path,
                "filename"     : name,
                "img"          : img,
                "auto_boxes"   : boxes,
                "kw_hits"      : kw_hits,
            }
            detected.append(row)
            writer.writerow([
                path, name, len(boxes), boxes_to_str(boxes),
                kw_hits,
                datetime.now().isoformat(timespec="seconds"),
            ])

    print(f"\n  → {len(detected)} image(s) with detections")
    print(f"  → detection_log.csv written to {DETECTION_CSV}\n")
    return detected

# ══════════════════════════════════════════════════════════════════
# SAVE HELPERS
# ══════════════════════════════════════════════════════════════════

def _output_path(original_path: str, filename: str) -> str:
    """
    Compute the destination path for an anonymized file.
    Uses OUTPUT_DIR when set; otherwise places it next to the original.
    """
    dest_dir = OUTPUT_DIR if OUTPUT_DIR else os.path.dirname(original_path)
    os.makedirs(dest_dir, exist_ok=True)
    return os.path.join(dest_dir, f"anonymized_{filename}")


def save_anonymized(img, boxes, original_path, filename):
    out_path = _output_path(original_path, filename)
    out = img.copy()
    for x, y, w, h in boxes:
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 0), -1)
    cv2.imwrite(out_path, out)
    return out_path

def append_anonymized_csv(row: dict):
    write_header = not os.path.exists(ANONYMIZED_CSV)
    with open(ANONYMIZED_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "original_path", "anonymized_path",
                "num_auto_boxes_kept", "num_manual_boxes",
                "total_boxes_applied", "reviewed_at",
            ])
        writer.writerow([
            row["original_path"], row["anonymized_path"],
            row["num_auto_kept"], row["num_manual"], row["total"],
            datetime.now().isoformat(timespec="seconds"),
        ])

# ══════════════════════════════════════════════════════════════════
# PHASE 2 — REVIEW GUI
# ══════════════════════════════════════════════════════════════════

class ReviewGUI:
    def __init__(self, root, detected_records):
        self.root    = root
        self.records = detected_records
        self.idx     = 0
        self.history = []

        self.img_cv      = None
        self.auto_boxes  = []
        self.active_auto = []
        self.user_boxes  = []
        self.draw_start  = None
        self.draw_rect   = None
        self.scale       = 1.0

        self._build_ui()
        self.root.after(150, lambda: self._load(0))

    def _build_ui(self):
        self.root.title("Anonymizer Pro — Human Review")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(True, True)

        top = tk.Frame(self.root, bg="#16213e", pady=6)
        top.pack(fill="x")
        self.lbl_file = tk.Label(
            top, text="", bg="#16213e", fg="#e0e0e0",
            font=("Courier New", 11, "bold"), anchor="w")
        self.lbl_file.pack(side="left", padx=12, fill="x", expand=True)
        self.lbl_stat = tk.Label(
            top, text="", bg="#16213e", fg="#7ec8e3",
            font=("Courier New", 10))
        self.lbl_stat.pack(side="right", padx=12)

        self.canvas = tk.Canvas(
            self.root, bg="#0d0d1a", cursor="crosshair",
            highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>",        self._right_click)

        bot = tk.Frame(self.root, bg="#16213e", pady=8)
        bot.pack(fill="x")
        B = dict(font=("Courier New", 10, "bold"), relief="flat",
                 padx=12, pady=6, cursor="hand2", bd=0)

        tk.Button(bot, text="◀ PREV",         bg="#0f3460", fg="white",
                  command=self._prev,          **B).pack(side="left", padx=4)
        tk.Button(bot, text="NEXT ▶",         bg="#0f3460", fg="white",
                  command=self._next,          **B).pack(side="left", padx=4)
        tk.Button(bot, text="↩ UNDO",         bg="#0f3460", fg="white",
                  command=self._undo,          **B).pack(side="left", padx=4)
        tk.Button(bot, text="✕ CLEAR MANUAL", bg="#4a1040", fg="#f0a0d0",
                  command=self._clear_manual,  **B).pack(side="left", padx=4)
        tk.Button(bot, text="☰ ALL AUTO ON",  bg="#1a3a1a", fg="#90ee90",
                  command=self._all_auto_on,   **B).pack(side="left", padx=4)
        tk.Button(bot, text="☷ ALL AUTO OFF", bg="#3a1a1a", fg="#ee9090",
                  command=self._all_auto_off,  **B).pack(side="left", padx=4)

        tk.Button(bot, text="⏭ SKIP (copy original)",
                  bg="#2c2c54", fg="#aaa",
                  font=("Courier New", 10), relief="flat",
                  padx=12, pady=6, cursor="hand2",
                  command=self._skip).pack(side="right", padx=4)
        tk.Button(bot, text="✔ SAVE & NEXT",
                  bg="#27ae60", fg="white",
                  font=("Courier New", 11, "bold"), relief="flat",
                  padx=18, pady=6, cursor="hand2",
                  command=self._save_next).pack(side="right", padx=6)

        leg = tk.Frame(bot, bg="#16213e")
        leg.pack(side="right", padx=14)
        for r, (sym, col, txt) in enumerate([
            ("■", "#f39c12", " Auto box  (click=toggle)"),
            ("■", "#e74c3c", " Manual box (right-click=remove)"),
            ("■", "#555555", " Auto OFF"),
        ]):
            tk.Label(leg, text=sym, fg=col, bg="#16213e",
                     font=("Arial", 13)).grid(row=r, column=0, sticky="w")
            tk.Label(leg, text=txt, fg="#aaa", bg="#16213e",
                     font=("Courier New", 8)).grid(row=r, column=1, sticky="w")

        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Left>",      lambda e: self._prev())
        self.root.bind("<Right>",     lambda e: self._next())
        self.root.after(500, lambda: self.root.bind(
            "<Return>", lambda e: self._save_next()))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if messagebox.askyesno("Quit?",
                "Exit without finishing?\nImages already saved will be kept."):
            self.root.destroy()

    def _load(self, idx):
        self.idx         = idx
        self.history     = []
        rec              = self.records[idx]
        self.img_cv      = rec["img"]
        self.auto_boxes  = list(rec["auto_boxes"])
        self.active_auto = [True] * len(self.auto_boxes)
        self.user_boxes  = []
        self._refresh_labels()
        self._render()

    def _refresh_labels(self):
        rec   = self.records[self.idx]
        n_on  = sum(self.active_auto)
        n_man = len(self.user_boxes)
        kw    = rec.get("kw_hits", 0)
        kw_tag = f"  │  KW hits: {kw}" if kw else ""
        self.lbl_file.config(text=f"  {rec['filename']}")
        self.lbl_stat.config(
            text=(f"Image {self.idx + 1}/{len(self.records)}  │  "
                  f"Auto active: {n_on}/{len(self.auto_boxes)}  │  "
                  f"Manual: {n_man}  │  "
                  f"Total to apply: {n_on + n_man}{kw_tag}  "))

    def _c(self, x, y, w, h):
        s = self.scale
        return int(x * s), int(y * s), int(w * s), int(h * s)

    def _img_pt(self, cx, cy):
        return cx / self.scale, cy / self.scale

    def _render(self):
        img  = self.img_cv
        H, W = img.shape[:2]
        self.root.update_idletasks()
        cw = self.canvas.winfo_width();  cw = cw if cw > 10 else MAX_DISPLAY_W
        ch = self.canvas.winfo_height(); ch = ch if ch > 10 else MAX_DISPLAY_H
        self.scale = min(cw / W, ch / H, 1.0)
        dw = max(1, int(W * self.scale))
        dh = max(1, int(H * self.scale))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(pil)
        self.canvas.delete("all")
        self.canvas.config(width=dw, height=dh)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        for i, (x, y, w, h) in enumerate(self.auto_boxes):
            cx, cy, cw2, ch2 = self._c(x, y, w, h)
            on = self.active_auto[i]
            self.canvas.create_rectangle(
                cx, cy, cx + cw2, cy + ch2,
                outline="#f39c12" if on else "#555555",
                width=2 if on else 1, dash=(8, 3), tags=f"auto_{i}")
        for i, (x, y, w, h) in enumerate(self.user_boxes):
            cx, cy, cw2, ch2 = self._c(x, y, w, h)
            self.canvas.create_rectangle(
                cx, cy, cx + cw2, cy + ch2,
                outline="#e74c3c", width=2, tags=f"usr_{i}")
        self._refresh_labels()

    def _press(self, event):
        ix, iy = self._img_pt(event.x, event.y)
        for i, (x, y, w, h) in enumerate(self.auto_boxes):
            if x <= ix <= x + w and y <= iy <= y + h:
                self._push_history()
                self.active_auto[i] = not self.active_auto[i]
                self._render()
                return
        self.draw_start = (event.x, event.y)

    def _drag(self, event):
        if not self.draw_start:
            return
        if self.draw_rect:
            self.canvas.delete(self.draw_rect)
        x0, y0 = self.draw_start
        self.draw_rect = self.canvas.create_rectangle(
            x0, y0, event.x, event.y,
            outline="#e74c3c", width=2, dash=(4, 2))

    def _release(self, event):
        if not self.draw_start:
            return
        x0, y0 = self.draw_start
        x1, y1 = event.x, event.y
        self.draw_start = None
        if self.draw_rect:
            self.canvas.delete(self.draw_rect)
            self.draw_rect = None
        if abs(x1 - x0) < 5 or abs(y1 - y0) < 5:
            return
        H, W = self.img_cv.shape[:2]
        ix0 = max(0, int(min(x0, x1) / self.scale))
        iy0 = max(0, int(min(y0, y1) / self.scale))
        ix1 = min(W, int(max(x0, x1) / self.scale))
        iy1 = min(H, int(max(y0, y1) / self.scale))
        self._push_history()
        self.user_boxes.append((ix0, iy0, ix1 - ix0, iy1 - iy0))
        self._render()

    def _right_click(self, event):
        ix, iy = self._img_pt(event.x, event.y)
        for i, (x, y, w, h) in enumerate(self.user_boxes):
            if x <= ix <= x + w and y <= iy <= y + h:
                self._push_history()
                self.user_boxes.pop(i)
                self._render()
                return

    def _push_history(self):
        self.history.append({
            "active_auto": copy.copy(self.active_auto),
            "user_boxes" : copy.copy(self.user_boxes),
        })

    def _undo(self):
        if not self.history:
            return
        state            = self.history.pop()
        self.active_auto = state["active_auto"]
        self.user_boxes  = state["user_boxes"]
        self._render()

    def _all_auto_on(self):
        self._push_history()
        self.active_auto = [True] * len(self.auto_boxes)
        self._render()

    def _all_auto_off(self):
        self._push_history()
        self.active_auto = [False] * len(self.auto_boxes)
        self._render()

    def _clear_manual(self):
        self._push_history()
        self.user_boxes = []
        self._render()

    def _save_next(self):
        final_boxes = (
            [b for i, b in enumerate(self.auto_boxes) if self.active_auto[i]]
            + self.user_boxes)
        rec      = self.records[self.idx]
        out_path = save_anonymized(
            self.img_cv, final_boxes,
            rec["original_path"], rec["filename"])
        n_auto   = sum(self.active_auto)
        n_man    = len(self.user_boxes)
        append_anonymized_csv({
            "original_path"  : rec["original_path"],
            "anonymized_path": out_path,
            "num_auto_kept"  : n_auto,
            "num_manual"     : n_man,
            "total"          : n_auto + n_man,
        })
        print(f"  [SAVED] {os.path.basename(out_path)}  "
              f"(auto:{n_auto}  manual:{n_man})")
        self._advance()

    def _skip(self):
        rec = self.records[self.idx]
        dst = _output_path(rec["original_path"], rec["filename"])
        shutil.copy2(rec["original_path"], dst)
        append_anonymized_csv({
            "original_path"  : rec["original_path"],
            "anonymized_path": dst,
            "num_auto_kept"  : 0,
            "num_manual"     : 0,
            "total"          : 0,
        })
        print(f"  [SKIP]  {rec['filename']} → copied unchanged")
        self._advance()

    def _advance(self):
        if self.idx < len(self.records) - 1:
            self._load(self.idx + 1)
        else:
            messagebox.showinfo(
                "Done",
                f"All {len(self.records)} image(s) reviewed.\n"
                f"anonymized_log.csv → {ANONYMIZED_CSV}")
            self.root.quit()

    def _prev(self):
        if self.idx > 0:
            self._load(self.idx - 1)

    def _next(self):
        if self.idx < len(self.records) - 1:
            self._load(self.idx + 1)

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    global model, PHI_MATCHERS, PHI_KEYWORDS_FILE

    # ── Step 1: Show startup dialog ───────────────────────────────
    dialog = StartupDialog()
    if not dialog.confirmed:
        print("[INFO] Setup cancelled — exiting.")
        sys.exit(0)

    print(f"[INFO] Input  → {INPUT_DIR}")
    print(f"[INFO] Output → {OUTPUT_DIR or '(same as input)'}")

    # ── Step 2: Load model (after dialog so window appears fast) ──
    print("[INFO] Loading docTR model …")
    model = ocr_predictor(pretrained=True)

    # ── Step 3: Load keyword matchers (INPUT_DIR now confirmed) ───
    PHI_MATCHERS = load_phi_keywords(PHI_KEYWORDS_FILE)

    # ── Step 4: Gather images ─────────────────────────────────────
    exts = (".jpg", ".jpeg", ".png", ".tiff", ".bmp")
    all_images = sorted([
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(exts)
           and not os.path.basename(f).startswith("anonymized_")
    ])

    if not all_images:
        messagebox.showwarning(
            "No images",
            f"No supported images found in:\n{INPUT_DIR}\n\n"
            "Supported: jpg, jpeg, png, tiff, bmp")
        sys.exit(0)

    print(f"[INFO] Found {len(all_images)} source image(s)")
    if PHI_MATCHERS:
        print(f"[INFO] PHI keyword matchers active: {len(PHI_MATCHERS)}")
    else:
        print("[INFO] No PHI keyword file — PHI-zone detection only.")
    print()

    # ── Step 5: Detect ────────────────────────────────────────────
    detected = phase1_detect(all_images)
    if not detected:
        messagebox.showinfo(
            "No detections",
            "No text / PHI detected in any image.\nNothing to review.")
        sys.exit(0)

    # ── Step 6: Review GUI ────────────────────────────────────────
    print(f"{'═' * 60}")
    print(f"  PHASE 2 — Human Review  ({len(detected)} image(s))")
    print(f"{'═' * 60}\n")
    print("  Controls:")
    print("    Left-click auto box    → toggle on/off")
    print("    Left-drag anywhere     → draw manual redaction box")
    print("    Right-click manual box → remove it")
    print("    Ctrl+Z / ↩ UNDO       → undo last action")
    print("    Enter / SAVE & NEXT    → save and advance\n")

    root = tk.Tk()
    root.geometry(f"{MAX_DISPLAY_W}x{MAX_DISPLAY_H + 140}")
    ReviewGUI(root, detected)
    root.mainloop()

    print(f"\n[DONE]")
    print(f"  Detection log  → {DETECTION_CSV}")
    print(f"  Anonymized log → {ANONYMIZED_CSV}")


if __name__ == "__main__":
    main()