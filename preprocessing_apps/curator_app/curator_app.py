#!/usr/bin/env python3
"""
MIDAS Image Curation System  v2.0
Clinical Image Archival Application for Hospital Curators

Requirements:
    pip install PyQt6

Usage:
    python midas_curation.py
"""

import sys
import os
import shutil
import csv
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Dict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDateEdit, QComboBox,
    QGroupBox, QScrollArea, QFrame, QFileDialog, QMessageBox,
    QSplitter, QCheckBox, QButtonGroup, QRadioButton,
    QProgressBar, QSizePolicy, QListWidget, QListWidgetItem,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QCloseEvent
import sys
import io

# Force UTF-8 encoding for Windows console/output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

APP_TITLE   = "MIDAS Curation System"
APP_VERSION = "v2.0"
ANATOMICAL_SITE = "MOUTH"

CATEGORIES: List[Tuple[str, str]] = [
    ("XC", "Clinical Photography"),
    ("RG", "Radiograph / OPG / CT"),
    ("GM", "General Microscopy"),
    ("SM", "Slide Microscopy"),
    ("OT", "Other"),
]

BODY_SITES: List[Tuple[str, str]] = [
    ("MANDI",  "Mandible"),
    ("MAXIL",  "Maxilla"),
    ("PALAT",  "Palate"),
    ("BUCCA",  "Buccal"),
    ("LING",   "Lingual"),
    ("LIP",    "Lip"),
    ("TONG",   "Tongue"),
    ("LN",     "Lymph Node"),
    ("OTHERS", "Others"),
]

MAGNIFICATIONS: List[str] = ["4x", "10x", "20x", "40x", "100x"]
CYTOLOGY_MAGS:  List[str] = ["10x", "40x"]

GM_SUBCATEGORIES: List[str] = ["HISTOPATH", "CYTOLOGY", "IHC", "SPECIAL_STAINS"]
SM_SUBCATEGORIES: List[str] = ["HISTOPATH", "IHC", "SPECIAL_STAINS", "CYTOLOGY"]
OT_SUBCATEGORIES: List[str] = ["GROSS", "GENOMIC"]

CSV_HEADERS: List[str] = [
    "UHID", "MIDAS_CODE", "VisitDate", "BodySite",
    "XC", "RG", "Gross", "Special_Stains", "IHC",
    "Cytology", "Genomic",
    "Histopath_4x", "Histopath_10x", "Histopath_20x",
    "Histopath_40x", "Histopath_100x",
    "WSI", "Curator",
]

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}

# ═══════════════════════════════════════════════════════════════════════════════
# STYLESHEET
# ═══════════════════════════════════════════════════════════════════════════════

QSS = """
* { font-family: 'Segoe UI','SF Pro Display','Helvetica Neue',Arial,sans-serif;
    font-size: 13px; color: #E6EDF3; }
QMainWindow { background: #0A0E17; }
QWidget#central { background: #0A0E17; }
QWidget { background: transparent; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background:#161B22; width:6px; margin:0; border-radius:3px; }
QScrollBar::handle:vertical { background:#30363D; border-radius:3px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#0ABDC6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#161B22; height:6px; border-radius:3px; }
QScrollBar::handle:horizontal { background:#30363D; border-radius:3px; }
QScrollBar::handle:horizontal:hover { background:#0ABDC6; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }

QGroupBox { background:#161B22; border:1px solid #21262D; border-radius:8px;
    margin-top:14px; padding-top:14px; padding-left:10px;
    padding-right:10px; padding-bottom:10px; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px;
    color:#0ABDC6; font-weight:700; font-size:10px; letter-spacing:1.5px; }

QLabel { background:transparent; color:#8B949E; font-size:12px; }
QLabel#subheading { color:#0ABDC6; font-size:10px; letter-spacing:2px; font-weight:700; }
QLabel#filename_preview { color:#0ABDC6;
    font-family:'Consolas','Courier New',monospace; font-size:11px;
    background:#0D1117; border:1px solid #21262D; border-radius:4px; padding:6px 10px; }
QLabel#counter_badge { color:#FFFFFF; font-size:12px; font-weight:800;
    background:#0ABDC6; border-radius:10px; padding:2px 10px; min-width:40px; }
QLabel#unsaved_badge { color:#FFFFFF; font-size:11px; font-weight:700;
    background:#E3A000; border-radius:8px; padding:2px 8px; }

QLineEdit { background:#0D1117; border:1px solid #30363D; border-radius:6px;
    padding:7px 10px; color:#E6EDF3; font-size:13px;
    selection-background-color:#1F6FEB; }
QLineEdit:focus { border-color:#0ABDC6; background:#0F1923; }
QLineEdit:hover { border-color:#484F58; }
QLineEdit[readOnly="true"] { color:#8B949E; }

QDateEdit { background:#0D1117; border:1px solid #30363D; border-radius:6px;
    padding:7px 10px; color:#E6EDF3; font-size:13px; }
QDateEdit:focus { border-color:#0ABDC6; }
QDateEdit::drop-down { border:none; width:22px; }
QCalendarWidget { background:#1C2128; color:#E6EDF3; }

QComboBox { background:#0D1117; border:1px solid #30363D; border-radius:6px;
    padding:7px 10px; color:#E6EDF3; font-size:13px; }
QComboBox:focus, QComboBox:on { border-color:#0ABDC6; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox::down-arrow { border:4px solid transparent; border-top:5px solid #8B949E;
    width:0; height:0; margin-right:8px; }
QComboBox QAbstractItemView { background:#1C2128; border:1px solid #30363D;
    border-radius:6px; selection-background-color:#1F3A5C;
    outline:none; padding:4px; color:#E6EDF3; }

QListWidget { background:#0D1117; border:1px solid #30363D; border-radius:6px;
    color:#E6EDF3; font-size:12px; outline:none; }
QListWidget::item { padding:4px 8px; border-radius:4px; }
QListWidget::item:selected { background:#1F3A5C; color:#0ABDC6; }
QListWidget::item:hover { background:#21262D; }

QRadioButton { color:#C9D1D9; spacing:8px; font-size:13px; }
QRadioButton::indicator { width:16px; height:16px; border-radius:8px;
    border:2px solid #30363D; background:#0D1117; }
QRadioButton::indicator:checked { background:#0ABDC6; border-color:#0ABDC6; }
QRadioButton::indicator:hover { border-color:#0ABDC6; }
QRadioButton:checked { color:#0ABDC6; font-weight:600; }

QCheckBox { color:#C9D1D9; spacing:6px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:3px;
    border:2px solid #30363D; background:#0D1117; }
QCheckBox::indicator:checked { background:#0ABDC6; border-color:#0ABDC6; }

QPushButton { background:#21262D; color:#C9D1D9; border:1px solid #30363D;
    border-radius:6px; padding:8px 16px; font-size:13px; font-weight:500; }
QPushButton:hover { background:#2D333B; border-color:#484F58; color:#E6EDF3; }
QPushButton:pressed { background:#1C2128; }

QPushButton#btn_primary {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0ABDC6,stop:1 #0891B2);
    color:#FFFFFF; border:none; font-size:14px; font-weight:700;
    padding:12px 24px; border-radius:8px; }
QPushButton#btn_primary:hover {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #22D3EE,stop:1 #0ABDC6);
    border:none; color:#FFFFFF; }
QPushButton#btn_primary:pressed { background:#0891B2; }
QPushButton#btn_primary:disabled { background:#21262D; color:#484F58; border:1px solid #30363D; }

QPushButton#btn_secondary { background:transparent; color:#0ABDC6;
    border:1px solid #0ABDC6; border-radius:6px; padding:7px 14px; }
QPushButton#btn_secondary:hover { background:rgba(10,189,198,0.12); }
QPushButton#btn_secondary:disabled { color:#30363D; border-color:#30363D; }

QPushButton#btn_warning { background:transparent; color:#E3A000;
    border:1px solid #E3A000; border-radius:6px; padding:7px 14px; font-weight:600; }
QPushButton#btn_warning:hover { background:rgba(227,160,0,0.12); }
QPushButton#btn_warning:disabled { color:#30363D; border-color:#30363D; }

QPushButton#btn_danger { background:transparent; color:#F85149;
    border:1px solid #F85149; border-radius:6px; padding:6px 12px; font-size:12px; }
QPushButton#btn_danger:hover { background:rgba(248,81,73,0.1); }

QProgressBar { background:#161B22; border:1px solid #21262D; border-radius:4px;
    height:6px; text-align:center; color:transparent; }
QProgressBar::chunk {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0ABDC6,stop:1 #00C896);
    border-radius:4px; }

QStatusBar { background:#161B22; border-top:1px solid #21262D;
    color:#8B949E; font-size:11px; }
QSplitter::handle { background:#21262D; width:1px; }
"""

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND — FOLDER BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class FolderBuilder:
    @staticmethod
    def get_path(root, midas_code, visit_date, category,
                 subcategory=None, body_site=None, magnification=None) -> Path:
        base = Path(root) / midas_code / f"VISIT_{visit_date}" / ANATOMICAL_SITE
        if category == "XC":
            return base / "XC" / "CLINICAL"
        elif category == "RG":
            return base / "RG" / "RADIOGRAPH"
        elif category in ("GM", "SM"):
            path = base / category
            if subcategory == "HISTOPATH":
                p = path / "HISTOPATH"
                if body_site:   p = p / body_site
                if magnification: p = p / magnification
                return p
            elif subcategory == "CYTOLOGY":
                p = path / "CYTOLOGY"
                if magnification: p = p / magnification
                return p
            elif subcategory in ("IHC", "SPECIAL_STAINS"):
                return path / subcategory
            return path
        elif category == "OT":
            path = base / "OT"
            if subcategory in ("GROSS", "GENOMIC"):
                return path / subcategory
            return path
        return base

    @staticmethod
    def ensure(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND — FILE NAMER
# ═══════════════════════════════════════════════════════════════════════════════

class FileNamer:
    @staticmethod
    def build(midas_code, visit_date, category,
              body_site=None, magnification=None, count=1, ext=".jpg") -> str:
        parts = [midas_code, f"VISIT_{visit_date}", category]
        if body_site:     parts.append(body_site)
        if magnification: parts.append(magnification)
        parts.append(f"{count:03d}")
        return "_".join(parts) + ext


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND — COUNTER MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class CounterManager:
    @staticmethod
    def next_count(folder: Path) -> int:
        if not folder.exists():
            return 1
        imgs = [f for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXT]
        return len(imgs) + 1


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND — CSV WRITER  (one CSV per MIDAS code; upsert by MIDAS_CODE+VisitDate)
# ═══════════════════════════════════════════════════════════════════════════════

class CSVWriter:
    """
    One persistent CSV per MIDAS code stored as  MIDAS_CODE/MIDAS_CODE_metadata.csv.

    upsert(row):
      Key = (MIDAS_CODE, VisitDate).
      • If a matching row already exists  -> numeric columns are SUMMED,
        text fields (UHID, BodySite, Curator) kept from existing unless blank.
      • If no matching row             -> new row appended.

    This guarantees ONE row per visit regardless of how many organise passes
    were made within a session or across sessions.
    """

    NUMERIC_COLS = {
        "XC", "RG", "Gross", "Special_Stains", "IHC", "Cytology", "Genomic",
        "Histopath_4x", "Histopath_10x", "Histopath_20x",
        "Histopath_40x", "Histopath_100x", "WSI",
    }

    def __init__(self, midas_folder: Path, midas_code: str):
        midas_folder.mkdir(parents=True, exist_ok=True)
        self.csv_path = midas_folder / f"{midas_code}_metadata.csv"
        if not self.csv_path.exists():
            with open(self.csv_path, 'w', newline='') as f:
                csv.writer(f).writerow(CSV_HEADERS)

    # ── public ───────────────────────────────────────────────────────────────

    def upsert(self, new_row: dict):
        """Merge new_row into the CSV (sum numerics on key match)."""
        rows = self._read_all()
        key  = (str(new_row.get("MIDAS_CODE", "")),
                str(new_row.get("VisitDate",   "")))
        matched = False
        for row in rows:
            if (str(row.get("MIDAS_CODE", "")) == key[0]
                    and str(row.get("VisitDate", "")) == key[1]):
                for col in CSV_HEADERS:
                    if col in self.NUMERIC_COLS:
                        try:
                            row[col] = int(row.get(col) or 0) + int(new_row.get(col) or 0)
                        except (ValueError, TypeError):
                            pass
                    else:
                        # Keep existing text; fill blanks from new row
                        if not row.get(col):
                            row[col] = new_row.get(col, "")
                matched = True
                break
        if not matched:
            rows.append({h: new_row.get(h, "") for h in CSV_HEADERS})
        self._write_all(rows)

    # ── private ──────────────────────────────────────────────────────────────

    def _read_all(self) -> List[dict]:
        if not self.csv_path.exists():
            return []
        with open(self.csv_path, 'r', newline='') as f:
            return list(csv.DictReader(f))

    def _write_all(self, rows: List[dict]):
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND — SESSION LOGGER  (Req 5: per-session, timestamped log file)
# ═══════════════════════════════════════════════════════════════════════════════

class SessionLogger:
    """New timestamped log file per application session, stored in root/logs/."""

    def __init__(self, root: Path):
        logs_dir = root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = logs_dir / f"curation_log_{ts}.txt"
        self._write(f"=== MIDAS Session started: {datetime.now():%Y-%m-%d %H:%M:%S} ===")

    def log(self, msg: str):
        self._write(f"[{datetime.now():%H:%M:%S}] {msg}")

    def _write(self, line: str):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE  (Req 8 & 9)
# ═══════════════════════════════════════════════════════════════════════════════

class SessionState:
    def __init__(self):
        self._ops: List[str] = []

    def mark_organised(self, desc: str):
        self._ops.append(desc)

    def mark_flushed(self):
        self._ops.clear()

    @property
    def has_unsaved(self) -> bool:
        return bool(self._ops)

    @property
    def summary(self) -> str:
        return "\n".join(f"  • {op}" for op in self._ops)


# ═══════════════════════════════════════════════════════════════════════════════
# UI — THUMBNAIL CARD  (Req 3: visual highlight of organised images)
# ═══════════════════════════════════════════════════════════════════════════════

class ThumbnailCard(QFrame):
    selection_changed = pyqtSignal()
    THUMB = 138
    CARD  = 158

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self._setup_ui()
        self._load_image()
        self._update_style()

    def _setup_ui(self):
        self.setFixedSize(self.CARD, self.CARD + 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.setSpacing(4)

        self.img_label = QLabel()
        self.img_label.setFixedSize(self.THUMB, self.THUMB)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.img_label)

        name = self.image_path.name
        if len(name) > 22:
            name = name[:19] + "..."
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet(
            "color:#8B949E; font-size:10px; background:transparent;")
        lay.addWidget(self.name_label)

        self.checkbox = QCheckBox(self)
        self.checkbox.setGeometry(self.CARD - 28, 8, 20, 20)
        self.checkbox.setStyleSheet("""
            QCheckBox::indicator { width:18px; height:18px; border-radius:4px;
                border:2px solid rgba(255,255,255,0.3); background:rgba(0,0,0,0.5); }
            QCheckBox::indicator:checked { background:#0ABDC6; border-color:#0ABDC6; }
            QCheckBox { background:transparent; }
        """)
        self.checkbox.stateChanged.connect(self._on_check)

        # Green "done" banner shown after organising
        self._done_badge = QLabel("✓ ORGANISED", self)
        self._done_badge.setGeometry(0, 0, self.CARD, 22)
        self._done_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_badge.setStyleSheet(
            "background:rgba(0,200,150,0.88); color:white; "
            "font-size:10px; font-weight:800;")
        self._done_badge.hide()

    def mark_organised(self):
        """Visually mark this image as already organised."""
        self._done_badge.show()
        self.checkbox.setChecked(False)
        self.checkbox.setEnabled(False)
        self._update_style(done=True)

    def _load_image(self):
        pix = QPixmap(str(self.image_path))
        if not pix.isNull():
            pix = pix.scaled(self.THUMB, self.THUMB,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            self.img_label.setPixmap(pix)
        else:
            self.img_label.setText("⚠ No Preview")
            self.img_label.setStyleSheet(
                "color:#F85149; font-size:11px; background:transparent;")

    def _update_style(self, done=False):
        if done:
            self.setStyleSheet(
                "QFrame{background:#0D2518;border:2px solid #00C896;border-radius:8px;}")
        elif self.is_selected:
            self.setStyleSheet(
                "QFrame{background:#0D2535;border:2px solid #0ABDC6;border-radius:8px;}")
        else:
            self.setStyleSheet("""
                QFrame{background:#1C2128;border:1px solid #30363D;border-radius:8px;}
                QFrame:hover{border-color:#484F58;background:#21262D;}
            """)

    def _on_check(self):
        self._update_style()
        self.selection_changed.emit()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.checkbox.isEnabled()):
            self.checkbox.setChecked(not self.checkbox.isChecked())

    @property
    def is_selected(self) -> bool:
        return self.checkbox.isChecked()


# ═══════════════════════════════════════════════════════════════════════════════
# UI — IMAGE PREVIEW PANEL  (Req 1 & 2)
# ═══════════════════════════════════════════════════════════════════════════════

class ImagePreviewPanel(QWidget):
    selection_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_folder: Optional[Path] = None
        self.thumbnails: List[ThumbnailCard] = []
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("IMAGE PREVIEW")
        title.setObjectName("subheading")
        hdr.addWidget(title)
        hdr.addStretch()
        clbl = QLabel("SELECTED")
        clbl.setStyleSheet(
            "color:#484F58;font-size:10px;font-weight:700;"
            "letter-spacing:1px;background:transparent;")
        self.sel_badge = QLabel("0")
        self.sel_badge.setObjectName("counter_badge")
        self.sel_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sel_badge.setMinimumWidth(36)
        hdr.addWidget(clbl)
        hdr.addSpacing(6)
        hdr.addWidget(self.sel_badge)
        lay.addLayout(hdr)

        # Source row
        src_frame = QFrame()
        src_frame.setStyleSheet(
            "QFrame{background:#161B22;border:1px solid #21262D;border-radius:8px;}")
        src_row = QHBoxLayout(src_frame)
        src_row.setContentsMargins(12, 8, 12, 8)
        src_row.setSpacing(10)
        self.source_label = QLabel("No source selected — plug USB or browse folder")
        self.source_label.setStyleSheet(
            "color:#484F58;font-size:11px;background:transparent;")
        src_row.addWidget(self.source_label, stretch=1)
        self.browse_btn = QPushButton("📁  Browse")
        self.browse_btn.setObjectName("btn_secondary")
        self.browse_btn.setFixedWidth(120)
        self.browse_btn.clicked.connect(self.browse_source)
        src_row.addWidget(self.browse_btn)
        self.refresh_btn = QPushButton("↻  Refresh")
        self.refresh_btn.setFixedWidth(90)
        self.refresh_btn.clicked.connect(self.refresh_images)
        src_row.addWidget(self.refresh_btn)
        lay.addWidget(src_frame)

        # Action row
        acts = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setFixedWidth(100)
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_btn = QPushButton("Deselect All")
        self.deselect_btn.setFixedWidth(100)
        self.deselect_btn.clicked.connect(self.deselect_all)
        acts.addWidget(self.select_all_btn)
        acts.addWidget(self.deselect_btn)
        acts.addStretch()
        self.total_label = QLabel("Total in folder: 0")
        self.total_label.setStyleSheet(
            "color:#484F58;font-size:11px;background:transparent;")
        acts.addWidget(self.total_label)
        lay.addLayout(acts)

        # Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_widget = QWidget()
        self.grid_widget.setStyleSheet("background:transparent;")
        from PyQt6.QtWidgets import QGridLayout
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_widget)

        self.empty_label = QLabel(
            "📷\n\nSelect a source folder to load images\nor browse to a USB device")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            "color:#484F58;font-size:14px;background:transparent;")
        lay.addWidget(self.empty_label, stretch=1)
        self.scroll.hide()
        lay.addWidget(self.scroll, stretch=1)

    def browse_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Source Folder (USB / Drive)", "",
            QFileDialog.Option.ShowDirsOnly)
        if folder:
            self.source_folder = Path(folder)
            self.source_label.setText(str(self.source_folder))
            self.source_label.setStyleSheet(
                "color:#C9D1D9;font-size:11px;background:transparent;")
            self.refresh_images()

    def refresh_images(self):
        if not self.source_folder:
            return
        self._clear_grid()
        files = sorted([f for f in self.source_folder.iterdir()
                        if f.is_file() and f.suffix.lower() in IMAGE_EXT])
        self.total_label.setText(f"Total in folder: {len(files)}")
        if not files:
            self.empty_label.setText(f"No images found in:\n{self.source_folder}")
            self.empty_label.show(); self.scroll.hide()
            self._set_badge(0); return
        self.empty_label.hide(); self.scroll.show()
        cols = 4
        for i, p in enumerate(files):
            card = ThumbnailCard(p)
            card.selection_changed.connect(self._update_count)
            self.thumbnails.append(card)
            self.grid_layout.addWidget(card, i // cols, i % cols)
        self._update_count()

    def select_all(self):
        for t in self.thumbnails:
            if t.checkbox.isEnabled():
                t.checkbox.setChecked(True)

    def deselect_all(self):
        for t in self.thumbnails:
            t.checkbox.setChecked(False)

    def get_selected_paths(self) -> List[Path]:
        return [t.image_path for t in self.thumbnails if t.is_selected]

    def mark_selected_organised(self):
        for t in self.thumbnails:
            if t.is_selected:
                t.mark_organised()

    def _clear_grid(self):
        self.thumbnails.clear()
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_count(self):
        n = sum(1 for t in self.thumbnails if t.is_selected)
        self._set_badge(n)
        self.selection_count_changed.emit(n)

    def _set_badge(self, n: int):
        self.sel_badge.setText(str(n))
        if n > 0:
            self.sel_badge.setStyleSheet(
                "color:#FFFFFF;font-size:12px;font-weight:800;"
                "background:#0ABDC6;border-radius:10px;padding:2px 10px;min-width:40px;")
        else:
            self.sel_badge.setStyleSheet(
                "color:#8B949E;font-size:12px;font-weight:800;"
                "background:#21262D;border-radius:10px;padding:2px 10px;min-width:40px;")


# ═══════════════════════════════════════════════════════════════════════════════
# UI — BODY SITE SELECTOR  (Req 4: single default + optional multi-select)
# ═══════════════════════════════════════════════════════════════════════════════

class BodySiteSelector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.multi_check = QCheckBox("Multiple body sites for this visit")
        self.multi_check.setStyleSheet("color:#C9D1D9;font-size:12px;")
        self.multi_check.toggled.connect(self._toggle_mode)
        lay.addWidget(self.multi_check)

        self.single_combo = QComboBox()
        for code, name in BODY_SITES:
            self.single_combo.addItem(f"{code}  —  {name}", userData=code)
        self.single_combo.currentIndexChanged.connect(self.changed)
        lay.addWidget(self.single_combo)

        self.multi_list = QListWidget()
        self.multi_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self.multi_list.setFixedHeight(140)
        for code, name in BODY_SITES:
            item = QListWidgetItem(f"{code}  —  {name}")
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.multi_list.addItem(item)
        self.multi_list.itemSelectionChanged.connect(self.changed)
        lay.addWidget(self.multi_list)
        self.multi_list.hide()

        self.hint = QLabel("Hold Ctrl / ⌘ to select multiple sites")
        self.hint.setStyleSheet(
            "color:#484F58;font-size:10px;background:transparent;")
        lay.addWidget(self.hint)
        self.hint.hide()

    def _toggle_mode(self, checked: bool):
        self.single_combo.setVisible(not checked)
        self.multi_list.setVisible(checked)
        self.hint.setVisible(checked)
        self.changed.emit()

    def get_sites(self) -> List[str]:
        if self.multi_check.isChecked():
            return [item.data(Qt.ItemDataRole.UserRole)
                    for item in self.multi_list.selectedItems()]
        code = self.single_combo.currentData()
        return [code] if code else []


# ═══════════════════════════════════════════════════════════════════════════════
# UI — FORM PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class FormPanel(QWidget):
    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(12, 12, 14, 12)
        lay.setSpacing(12)

        # Header banner
        hdr = QFrame()
        hdr.setStyleSheet("""
            QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #0ABDC6,stop:1 #00C896);border-radius:10px;}
        """)
        hfl = QVBoxLayout(hdr)
        hfl.setContentsMargins(16, 14, 16, 14)
        hfl.setSpacing(2)
        t1 = QLabel("MIDAS")
        t1.setStyleSheet(
            "color:white;font-size:24px;font-weight:900;"
            "letter-spacing:5px;background:transparent;")
        t2 = QLabel("Image Curation System  ·  v2.0")
        t2.setStyleSheet(
            "color:rgba(255,255,255,0.75);font-size:11px;"
            "letter-spacing:1px;background:transparent;")
        hfl.addWidget(t1); hfl.addWidget(t2)
        lay.addWidget(hdr)

        # Step 1
        g1 = QGroupBox("STEP 1  ·  ROOT STORAGE")
        v1 = QVBoxLayout(g1); v1.setSpacing(6)
        row = QHBoxLayout()
        self.root_edit = QLineEdit()
        self.root_edit.setReadOnly(True)
        self.root_edit.setPlaceholderText("Select root data directory…")
        self.root_edit.textChanged.connect(self.params_changed)
        row.addWidget(self.root_edit)
        btn = QPushButton("Browse"); btn.setFixedWidth(72)
        btn.clicked.connect(self._browse_root)
        row.addWidget(btn)
        v1.addLayout(row)
        lay.addWidget(g1)

        # Step 2
        g2 = QGroupBox("STEP 2  ·  PATIENT INFORMATION")
        v2 = QVBoxLayout(g2); v2.setSpacing(6)
        self.uhid_edit    = self._field(v2, "UHID *")
        self.midas_edit   = self._field(v2, "MIDAS Code *")
        self.curator_edit = self._field(v2, "Curator Name *")
        lbl = QLabel("Visit Date *")
        lbl.setStyleSheet("color:#8B949E;font-size:11px;background:transparent;")
        v2.addWidget(lbl)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_edit.dateChanged.connect(self.params_changed)
        v2.addWidget(self.date_edit)
        for w in (self.uhid_edit, self.midas_edit, self.curator_edit):
            w.textChanged.connect(self.params_changed)
        lay.addWidget(g2)

        # Step 3
        g3 = QGroupBox("STEP 3  ·  CATEGORY")
        v3 = QVBoxLayout(g3); v3.setSpacing(6)
        self.cat_group  = QButtonGroup(self)
        self.cat_radios: Dict[str, QRadioButton] = {}
        for code, label in CATEGORIES:
            rb = QRadioButton(f"  {code}   ·   {label}")
            self.cat_group.addButton(rb)
            self.cat_radios[code] = rb
            rb.toggled.connect(self._on_cat_changed)
            v3.addWidget(rb)
        lay.addWidget(g3)

        # Step 4 (conditional)
        self.g4 = QGroupBox("STEP 4  ·  SUBCATEGORY")
        v4 = QVBoxLayout(self.g4)
        self.subcat_combo = QComboBox()
        self.subcat_combo.currentTextChanged.connect(self._on_subcat_changed)
        v4.addWidget(self.subcat_combo)
        lay.addWidget(self.g4); self.g4.hide()

        # Step 5 (conditional)
        self.g5 = QGroupBox("STEP 5  ·  BODY SITE")
        v5 = QVBoxLayout(self.g5)
        self.body_selector = BodySiteSelector()
        self.body_selector.changed.connect(self.params_changed)
        v5.addWidget(self.body_selector)
        lay.addWidget(self.g5); self.g5.hide()

        # Step 6 (conditional)
        self.g6 = QGroupBox("STEP 6  ·  MAGNIFICATION")
        v6 = QVBoxLayout(self.g6)
        self.mag_combo = QComboBox()
        self.mag_combo.currentTextChanged.connect(self.params_changed)
        v6.addWidget(self.mag_combo)
        lay.addWidget(self.g6); self.g6.hide()

        lay.addStretch()

    def _field(self, layout, label) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setStyleSheet("color:#8B949E;font-size:11px;background:transparent;")
        layout.addWidget(lbl)
        le = QLineEdit()
        le.setPlaceholderText(f"Enter {label.replace(' *','')}…")
        layout.addWidget(le)
        return le

    def _browse_root(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Root Storage Directory", "",
            QFileDialog.Option.ShowDirsOnly)
        if folder:
            self.root_edit.setText(folder)

    def _on_cat_changed(self):
        cat = self.get_category()
        self.g4.hide(); self.g5.hide(); self.g6.hide()
        if cat in ("GM", "SM", "OT"):
            self.g4.show()
            self.subcat_combo.blockSignals(True)
            self.subcat_combo.clear()
            self.subcat_combo.addItems(
                {"GM": GM_SUBCATEGORIES,
                 "SM": SM_SUBCATEGORIES,
                 "OT": OT_SUBCATEGORIES}[cat])
            self.subcat_combo.blockSignals(False)
            self._on_subcat_changed(self.subcat_combo.currentText())
        self.params_changed.emit()

    def _on_subcat_changed(self, subcat: str):
        cat = self.get_category()
        self.g5.hide(); self.g6.hide()
        if subcat == "HISTOPATH" and cat in ("GM", "SM"):
            self.g5.show(); self.g6.show()
            self.mag_combo.blockSignals(True)
            self.mag_combo.clear(); self.mag_combo.addItems(MAGNIFICATIONS)
            self.mag_combo.blockSignals(False)
        elif subcat == "CYTOLOGY":
            self.g6.show()
            self.mag_combo.blockSignals(True)
            self.mag_combo.clear(); self.mag_combo.addItems(CYTOLOGY_MAGS)
            self.mag_combo.blockSignals(False)
        self.params_changed.emit()

    # Getters
    def get_root(self):         return self.root_edit.text().strip()
    def get_uhid(self):         return self.uhid_edit.text().strip()
    def get_midas_code(self):   return self.midas_edit.text().strip()
    def get_curator(self):      return self.curator_edit.text().strip()
    def get_visit_date(self):   return self.date_edit.date().toString("dd-MM-yyyy")
    def get_category(self):
        for code, rb in self.cat_radios.items():
            if rb.isChecked(): return code
        return None
    def get_subcategory(self):
        return self.subcat_combo.currentText() if not self.g4.isHidden() else None
    def get_body_sites(self) -> List[str]:
        return [] if self.g5.isHidden() else self.body_selector.get_sites()
    def get_magnification(self):
        return self.mag_combo.currentText() if not self.g6.isHidden() else None

    def validate(self) -> Tuple[bool, str]:
        if not self.get_root():       return False, "Please select a root storage directory."
        if not self.get_midas_code(): return False, "MIDAS Code is required."
        if not self.get_uhid():       return False, "UHID is required."
        if not self.get_curator():    return False, "Curator name is required."
        if not self.get_category():   return False, "Please select a category."
        cat, sub = self.get_category(), self.get_subcategory()
        if sub == "HISTOPATH" and cat in ("GM", "SM"):
            if not self.get_body_sites():
                return False, "Please select at least one Body Site."
        return True, ""


# ═══════════════════════════════════════════════════════════════════════════════
# UI — SAVE CONTROL BAR  (Req 7: three independent save actions)
# ═══════════════════════════════════════════════════════════════════════════════

class SaveControlBar(QFrame):
    organise_requested = pyqtSignal()
    save_csv_requested = pyqtSignal()
    save_log_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame{background:#161B22;border-top:1px solid #21262D;}")
        self.setFixedHeight(90)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(14)

        # Filename preview
        left = QVBoxLayout(); left.setSpacing(3)
        pl = QLabel("OUTPUT FILENAME PREVIEW")
        pl.setStyleSheet(
            "color:#484F58;font-size:10px;letter-spacing:1.5px;"
            "font-weight:700;background:transparent;")
        self.preview_lbl = QLabel("—")
        self.preview_lbl.setObjectName("filename_preview")
        self.preview_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left.addWidget(pl); left.addWidget(self.preview_lbl)
        lay.addLayout(left, stretch=1)

        self.progress = QProgressBar()
        self.progress.setFixedSize(130, 6)
        self.progress.setTextVisible(False); self.progress.setValue(0)
        self.progress.hide()
        lay.addWidget(self.progress)

        self.unsaved_badge = QLabel("● UNSAVED CHANGES")
        self.unsaved_badge.setObjectName("unsaved_badge")
        self.unsaved_badge.hide()
        lay.addWidget(self.unsaved_badge)

        self.organise_btn = QPushButton("✓  Organise Images")
        self.organise_btn.setObjectName("btn_primary")
        self.organise_btn.setFixedSize(190, 48)
        self.organise_btn.setEnabled(False)
        self.organise_btn.clicked.connect(self.organise_requested)
        lay.addWidget(self.organise_btn)

        self.csv_btn = QPushButton("💾  Save CSV")
        self.csv_btn.setObjectName("btn_secondary")
        self.csv_btn.setFixedSize(130, 48)
        self.csv_btn.setEnabled(False)
        self.csv_btn.clicked.connect(self.save_csv_requested)
        lay.addWidget(self.csv_btn)

        self.log_btn = QPushButton("📋  Save Log")
        self.log_btn.setObjectName("btn_warning")
        self.log_btn.setFixedSize(120, 48)
        self.log_btn.setEnabled(False)
        self.log_btn.clicked.connect(self.save_log_requested)
        lay.addWidget(self.log_btn)

    def set_preview(self, t: str): self.preview_lbl.setText(t)
    def set_organise_enabled(self, v): self.organise_btn.setEnabled(v)
    def set_csv_enabled(self, v):  self.csv_btn.setEnabled(v)
    def set_log_enabled(self, v):  self.log_btn.setEnabled(v)
    def set_unsaved(self, v):      self.unsaved_badge.setVisible(v)

    def set_progress(self, value: int, total: int):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(value)
            self.progress.show()
        else:
            self.progress.hide()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE}  {APP_VERSION}")
        self.setMinimumSize(1100, 720)
        self.resize(1400, 860)
        self._session           = SessionState()
        self._csv_writer:       Optional[CSVWriter]    = None
        self._logger:           Optional[SessionLogger] = None
        self._pending_csv_rows: List[dict]             = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        central = QWidget(); central.setObjectName("central")
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(14, 14, 14, 0)
        main.setSpacing(10)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.form_panel    = FormPanel()
        self.preview_panel = ImagePreviewPanel()
        self.splitter.addWidget(self.form_panel)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setSizes([400, 900])
        main.addWidget(self.splitter, stretch=1)

        self.save_bar = SaveControlBar()
        main.addWidget(self.save_bar)

        self.statusBar().setFixedHeight(26)
        self.statusBar().showMessage(f"Ready  ·  {APP_TITLE} {APP_VERSION}")

    def _connect_signals(self):
        self.form_panel.params_changed.connect(self._refresh_preview)
        self.preview_panel.selection_count_changed.connect(self._update_organise_state)
        self.save_bar.organise_requested.connect(self._organise_images)
        self.save_bar.save_csv_requested.connect(self._save_csv)
        self.save_bar.save_log_requested.connect(self._save_log)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _ensure_logger(self):
        root = self.form_panel.get_root()
        if self._logger is None and root:
            self._logger = SessionLogger(Path(root))
            self.save_bar.set_log_enabled(True)

    def _ensure_csv_writer(self, mc: str, root: str):
        midas_folder = Path(root) / mc
        if (self._csv_writer is None
                or self._csv_writer.csv_path.parent != midas_folder):
            self._csv_writer = CSVWriter(midas_folder, mc)

    def _refresh_preview(self):
        mc   = self.form_panel.get_midas_code() or "MIDAS_CODE"
        vd   = self.form_panel.get_visit_date()
        cat  = self.form_panel.get_category() or "XX"
        sites = self.form_panel.get_body_sites()
        bs   = sites[0] if sites else None
        mag  = self.form_panel.get_magnification()
        self.save_bar.set_preview(FileNamer.build(mc, vd, cat, bs, mag, 1))
        self._update_organise_state(
            sum(1 for t in self.preview_panel.thumbnails if t.is_selected))

    def _update_organise_state(self, n: int):
        ok, _ = self.form_panel.validate()
        self.save_bar.set_organise_enabled(ok and n > 0)

    def _update_unsaved_ui(self):
        self.save_bar.set_unsaved(self._session.has_unsaved or bool(self._pending_csv_rows))
        self.save_bar.set_csv_enabled(bool(self._pending_csv_rows))

    # ── Organise  ─────────────────────────────────────────────────────────────

    def _organise_images(self):
        try:
            self._do_organise()
        except Exception as exc:
            tb_text = traceback.format_exc()
            print(tb_text, file=sys.stderr)
            QMessageBox.critical(
                self, "Organise Failed",
                f"<b>An error occurred while organising images.</b><br><br>"
                f"<b>Error:</b> {exc}<br><br>"
                f"Please report this to the development team.<br><br>"
                f"<pre>{tb_text}</pre>"
            )
            self.save_bar.set_progress(0, 0)

    def _do_organise(self):
        """Core organise logic — called inside try/except in _organise_images."""
        ok, msg = self.form_panel.validate()
        if not ok:
            QMessageBox.warning(self, "Validation Error", msg); return

        selected = self.preview_panel.get_selected_paths()
        if not selected:
            QMessageBox.information(self, "Nothing Selected",
                                    "Please select at least one image."); return

        root    = self.form_panel.get_root()
        mc      = self.form_panel.get_midas_code()
        vd      = self.form_panel.get_visit_date()
        cat     = self.form_panel.get_category()
        subcat  = self.form_panel.get_subcategory()
        sites   = self.form_panel.get_body_sites() or [None]
        mag     = self.form_panel.get_magnification()
        curator = self.form_panel.get_curator()
        uhid    = self.form_panel.get_uhid()

        # Validate root path is accessible
        root_path = Path(root)
        if not root_path.exists():
            QMessageBox.warning(
                self, "Root Path Error",
                f"The root storage directory does not exist or is not accessible:\n{root}\n\n"
                "Please re-select the root directory."
            )
            return

        self._ensure_logger()
        self._ensure_csv_writer(mc, root)

        total, all_names = 0, []
        self.save_bar.set_progress(0, len(selected) * len(sites))
        step = 0

        for site in sites:
            dest  = FolderBuilder.get_path(root, mc, vd, cat, subcat, site, mag)
            FolderBuilder.ensure(dest)
            start = CounterManager.next_count(dest)
            names: List[str] = []
            for i, src in enumerate(selected):
                if not src.exists():
                    raise FileNotFoundError(
                        f"Source image no longer exists:\n{src}\n\n"
                        "The USB device may have been removed. Please re-browse the source folder."
                    )
                ext      = src.suffix.lower() if src.suffix.lower() in IMAGE_EXT else ".jpg"
                new_name = FileNamer.build(mc, vd, cat, site, mag, start + i, ext)
                dest_file = dest / new_name
                shutil.copy2(str(src), str(dest_file))
                names.append(new_name)
                step += 1
                self.save_bar.set_progress(step, len(selected) * len(sites))
                QApplication.processEvents()

            total     += len(names)
            all_names += names

            # Build metadata row for this site pass
            row = {h: 0 for h in CSV_HEADERS}
            row.update({"UHID": uhid, "MIDAS_CODE": mc, "VisitDate": vd,
                        "BodySite": site or "", "Curator": curator})
            n = len(names)
            if   cat == "XC":
                row["XC"] = n
            elif cat == "RG":
                row["RG"] = n
            elif cat in ("GM", "SM"):
                if subcat == "HISTOPATH":
                    mk = f"Histopath_{mag}" if mag else None
                    if mk and mk in row:
                        row[mk] = n
                elif subcat == "IHC":
                    row["IHC"] = n
                elif subcat == "SPECIAL_STAINS":
                    row["Special_Stains"] = n
                elif subcat == "CYTOLOGY":
                    row["Cytology"] = n
            elif cat == "OT":
                if   subcat == "GROSS":   row["Gross"]   = n
                elif subcat == "GENOMIC": row["Genomic"] = n
            self._pending_csv_rows.append(row)

            # Log immediately
            trail = cat
            if subcat: trail += f" -> {subcat}"
            if site:   trail += f" -> {site}"
            if mag:    trail += f" -> {mag}"
            if self._logger:
                self._logger.log(
                    f"ORGANISED | MIDAS:{mc} UHID:{uhid} | {n} file(s) | "
                    f"{trail} | Curator:{curator} | Dest:{dest}")

        self.preview_panel.mark_selected_organised()
        self._session.mark_organised(
            f"{total} image(s) — {mc} · {cat}"
            + (f" / {subcat}" if subcat else ""))
        self._update_unsaved_ui()

        self.statusBar().showMessage(
            f"✓  {total} image(s) organised  ·  "
            f"{datetime.now():%H:%M:%S}  ·  CSV & Log not yet saved")

        QMessageBox.information(
            self, "Images Organised",
            f"✓  {total} image(s) organised successfully.\n\n"
            f"First file:  {all_names[0] if all_names else '—'}\n\n"
            "⚠  Click  'Save CSV'  and  'Save Log'  before closing.")

        QTimer.singleShot(3000, lambda: self.save_bar.set_progress(0, 0))

    # ── Save CSV  (Req 6 & 7) ─────────────────────────────────────────────────

    @staticmethod
    def _aggregate_rows(rows: List[dict]) -> List[dict]:
        """
        Collapse a list of per-organise-pass rows into ONE row per
        (MIDAS_CODE, VisitDate) by summing all numeric columns.
        Text fields (UHID, BodySite, Curator) are taken from the first
        non-blank value found.
        """
        NUMERIC = {
            "XC", "RG", "Gross", "Special_Stains", "IHC", "Cytology",
            "Genomic", "Histopath_4x", "Histopath_10x", "Histopath_20x",
            "Histopath_40x", "Histopath_100x", "WSI",
        }
        merged: Dict[Tuple[str, str], dict] = {}
        for row in rows:
            key = (str(row.get("MIDAS_CODE", "")),
                   str(row.get("VisitDate",   "")))
            if key not in merged:
                merged[key] = {h: (0 if h in NUMERIC else "") for h in CSV_HEADERS}
            m = merged[key]
            for col in CSV_HEADERS:
                if col in NUMERIC:
                    try:
                        m[col] = int(m[col] or 0) + int(row.get(col) or 0)
                    except (ValueError, TypeError):
                        pass
                else:
                    if not m[col]:
                        m[col] = row.get(col, "")
        return list(merged.values())

    def _save_csv(self):
        if not self._pending_csv_rows:
            QMessageBox.information(self, "Nothing to Save",
                                    "No pending metadata rows."); return

        if self._csv_writer is None:
            QMessageBox.warning(
                self, "CSV Writer Error",
                "The CSV writer was not initialised.\n\n"
                "Please organise at least one image before saving the CSV."
            )
            return

        try:
            aggregated = self._aggregate_rows(self._pending_csv_rows)
            for row in aggregated:
                self._csv_writer.upsert(row)

            n_passes = len(self._pending_csv_rows)
            n_rows   = len(aggregated)
            self._pending_csv_rows.clear()
            self._session.mark_flushed()
            self._update_unsaved_ui()

            if self._logger:
                self._logger.log(
                    f"CSV SAVED | {n_passes} organise pass(es) -> "
                    f"{n_rows} visit row(s) upserted -> {self._csv_writer.csv_path}")
            self.statusBar().showMessage(
                f"✓  CSV saved  ·  {n_rows} visit row(s)  ->  {self._csv_writer.csv_path}")
            QMessageBox.information(
                self, "CSV Saved",
                f"✓  {n_rows} visit row(s) written to:\n{self._csv_writer.csv_path}\n\n"
                f"({n_passes} organise pass(es) merged into {n_rows} row(s))")

        except Exception as exc:
            tb_text = traceback.format_exc()
            print(tb_text, file=sys.stderr)
            QMessageBox.critical(
                self, "CSV Save Failed",
                f"<b>Failed to write CSV.</b><br><br>"
                f"<b>Error:</b> {exc}<br><br>"
                f"Your organised images are safe — only the metadata record failed to save.<br><br>"
                f"<pre>{tb_text}</pre>"
            )

    # ── Save Log  (Req 5 & 7) ─────────────────────────────────────────────────

    def _save_log(self):
        if self._logger is None:
            QMessageBox.information(self, "No Log",
                                    "No log file created yet."); return
        self._logger.log("USER CONFIRMED LOG SAVE")
        self.statusBar().showMessage(f"✓  Log: {self._logger.log_path}")
        QMessageBox.information(
            self, "Log File Location",
            f"Session log is continuously written to:\n\n{self._logger.log_path}")

    # ── Close Event  (Req 8 & 9) ──────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        has_unsaved = self._session.has_unsaved or bool(self._pending_csv_rows)
        if not has_unsaved:
            if self._logger:
                self._logger.log("=== Session ended ===")
            event.accept()
            return

        # Build detail text
        items = []
        if self._pending_csv_rows:
            items.append(
                f"  • CSV file  ({len(self._pending_csv_rows)} unsaved row(s))")
        if self._session.has_unsaved:
            items.append("  • Organised image session records")
        if self._logger:
            items.append("  • Session log file")

        dlg = QMessageBox(self)
        dlg.setWindowTitle("Unsaved Data")
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setText("<b>You have unsaved data from this session.</b>")
        dlg.setInformativeText(
            "The following items have not been saved:\n\n"
            + "\n".join(items)
            + "\n\nDo you want to save before exiting?")
        dlg.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        dlg.setDefaultButton(QMessageBox.StandardButton.Save)
        dlg.button(QMessageBox.StandardButton.Save).setText("Save & Exit")
        dlg.button(QMessageBox.StandardButton.Discard).setText("Exit Without Saving")

        result = dlg.exec()

        if result == QMessageBox.StandardButton.Save:
            self._save_csv()
            if self._logger:
                self._logger.log("=== Session ended (saved) ===")
            event.accept()
        elif result == QMessageBox.StandardButton.Discard:
            if self._logger:
                self._logger.log("=== Session ended (discarded) ===")
            event.accept()
        else:
            event.ignore()   # Req 9 — keep app open


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL EXCEPTION HOOK  — catches silent Qt slot crashes and shows a dialog
# ═══════════════════════════════════════════════════════════════════════════════

def _global_exception_hook(exc_type, exc_value, exc_tb):
    """
    PyQt6 silently kills the process on unhandled slot exceptions.
    This hook intercepts them and shows a QMessageBox with the full traceback
    so crashes are always visible during the pilot run.
    """
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(tb_text, file=sys.stderr)   # also print to terminal

    # Only show dialog if a QApplication exists
    app = QApplication.instance()
    if app is not None:
        msg = QMessageBox()
        msg.setWindowTitle("Unexpected Error")
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setText(
            "<b>An unexpected error occurred.</b><br><br>"
            "Please copy the details below and report them to the development team."
        )
        msg.setDetailedText(tb_text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(QSS)

    # Install global hook AFTER QApplication exists so dialogs work
    sys.excepthook = _global_exception_hook

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()