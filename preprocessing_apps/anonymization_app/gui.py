"""
gui.py – High-contrast, lightweight UI for Setup and Human Redaction Review.
Supports standard raster images, WSI previews, and DICOM pixel verification.
"""

import copy
import os
import shutil
import sys
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import cv2
import numpy as np

import config
import storage

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    TkinterDnD = None
    DND_FILES = None


# ──────────────────────────────────────────────────────────────────
# Color Palette & Typography
# ──────────────────────────────────────────────────────────────────

THEME = {
    "bg": "#10131a",
    "card": "#181c26",
    "input_bg": "#202534",
    "border": "#2e364a",
    "text": "#f8fafc",
    "text_muted": "#94a3b8",
    "accent_green": "#16a34a",
    "accent_green_hover": "#15803d",
    "accent_blue": "#2563eb",
    "accent_blue_hover": "#1d4ed8",
    "accent_red": "#dc2626",
    "accent_red_hover": "#b91c1c",
    "btn_slate": "#334155",
    "btn_slate_hover": "#475569",
}

FONT_TITLE = ("Helvetica", 14, "bold")
FONT_HEADING = ("Helvetica", 10, "bold")
FONT_BODY = ("Helvetica", 9)
FONT_BOLD = ("Helvetica", 9, "bold")
FONT_MONO = ("Courier", 9)

import dicom_profile


class ProcessingStatusWindow:
    """Shows live detection progress and the image-level PHI count."""

    def __init__(self, total_files: int = 0):
        self.root = tk.Tk()
        self.root.title("Anonymed - Processing")
        self.root.geometry("560x230")
        self.root.resizable(False, False)
        self.root.configure(bg=THEME["bg"])
        set_window_icon(self.root, "anonymous.ico")

        self.total_files = total_files
        self.scanned_count = 0
        self.images_with_phi = 0
        self._log_lines = deque(["Preparing the processing pipeline..."], maxlen=3)

        tk.Label(
            self.root,
            text="Anonymed - Scanning & De-Identification",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=FONT_TITLE,
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self.counter_var = tk.StringVar(value=self._counter_text())
        tk.Label(
            self.root,
            textvariable=self.counter_var,
            bg=THEME["card"],
            fg=THEME["accent_green"],
            font=FONT_HEADING,
            padx=10,
            pady=8,
        ).pack(fill="x", padx=16, pady=(0, 8))

        self.progress = ttk.Progressbar(
            self.root,
            orient="horizontal",
            mode="determinate",
            maximum=max(1, total_files),
        )
        self.progress.pack(fill="x", padx=16, pady=(0, 8))

        self.feed_var = tk.StringVar(value="\n".join(self._log_lines))
        tk.Label(
            self.root,
            textvariable=self.feed_var,
            bg=THEME["card"],
            fg=THEME["text_muted"],
            font=FONT_MONO,
            justify="left",
            anchor="nw",
            height=3,
            padx=10,
            pady=8,
        ).pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.refresh()

    def _counter_text(self) -> str:
        return (
            f"Images likely to reveal patient identity : {self.images_with_phi} / "
            f"{self.scanned_count} scanned"
        )

    def log_status(self, message: str) -> None:
        self._log_lines.append(message)
        self.feed_var.set("\n".join(self._log_lines))
        self.refresh()

    def record_image_result(self, has_phi: bool) -> None:
        self.scanned_count += 1
        if has_phi:
            self.images_with_phi += 1
        self.progress["value"] = self.scanned_count
        self.counter_var.set(self._counter_text())
        self.refresh()

    def refresh(self) -> None:
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass


class DicomTagDialog(tk.Toplevel):
    """
    Optional dialog for editing MIDAS DICOM tags for this file or this session.
    """

    def __init__(self, parent, current_tags: dict, title: str = "MIDAS DICOM Tag Settings"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result_tags = None
        self.remember_var = tk.BooleanVar(value=False)
        self.auto_inc_var = tk.BooleanVar(value=True)
        self.entries = {}

        def make_btn(parent_widget, text, cmd, bg_color, fg_color="#ffffff", padx=12, pady=5, bold=True):
            lbl = tk.Label(
                parent_widget,
                text=text,
                bg=bg_color,
                fg=fg_color,
                font=("Segoe UI", 9, "bold" if bold else "normal"),
                padx=padx,
                pady=pady,
                cursor="hand2",
                relief="flat",
            )
            lbl.bind("<Button-1>", lambda event: cmd())
            lbl.bind("<Enter>", lambda event: lbl.config(relief="ridge"))
            lbl.bind("<Leave>", lambda event: lbl.config(relief="flat"))
            return lbl

        tk.Label(
            self,
            text="DICOM Metadata & MIDAS Schema (Optional)",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(12, 2))

        tk.Label(
            self,
            text="Fields start blank. Only non-empty values you enter will be applied.",
            bg=THEME["bg"],
            fg=THEME["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        form = tk.Frame(self, bg=THEME["bg"])
        form.pack(fill="both", expand=True, padx=16, pady=4)

        # Flat + Sequence field mapping
        fields = [
            ("PatientID", "Patient ID", current_tags.get("PatientID", "")),
            ("AccessionNumber", "Accession Number (0008,0050)", current_tags.get("AccessionNumber", "")),
            ("StudyDate", "Study Date YYYYMMDD (0008,0020)", current_tags.get("StudyDate", "")),
            ("Modality", "Modality (0008,0060)", current_tags.get("Modality", "")),
            ("StationName", "Station Name (0008,1010)", current_tags.get("StationName", "")),
            ("SeriesDescription", "Series Description (0008,103E)", current_tags.get("SeriesDescription", "")),
            ("InstitutionName", "Institution Name (0008,0080)", current_tags.get("InstitutionName", "")),
            ("InstCodeValue", "Institution Code Value (0008,0082)", current_tags.get("InstitutionCodeSequence", {}).get("CodeValue", "")),
            ("InstCodeMeaning", "Institution Code Meaning", current_tags.get("InstitutionCodeSequence", {}).get("CodeMeaning", "")),
            ("IssuerOfPatientID", "Issuer of Patient ID (0010,0021)", current_tags.get("IssuerOfPatientID", "")),
            ("OperatorsName", "Operators' Name (0008,1070)", current_tags.get("OperatorsName", "")),
            ("ConsultingPhysicianName", "Consulting Physician (0008,009C)", current_tags.get("ConsultingPhysicianName", "")),
            ("ROICreator", "ROI Creator ID (3006,004D)", current_tags.get("ROICreatorSequence", {}).get("ObservationSubject", "")),
            ("ROIInterpreter", "ROI Interpreter ID (3006,004E)", current_tags.get("ROIInterpreterSequence", {}).get("ObservationSubject", "")),
            ("Manufacturer", "Manufacturer (0008,0070)", current_tags.get("Manufacturer", "")),
            ("ConsentForDistributionFlag", "Consent Flag (YES/NO)", current_tags.get("ConsentForDistributionFlag", "")),
        ]

        for row_idx, (key, label, val) in enumerate(fields):
            tk.Label(form, text=label, bg=THEME["bg"], fg=THEME["text"], font=("Segoe UI", 9)).grid(
                row=row_idx, column=0, sticky="w", pady=3, padx=(0, 12)
            )
            ent = tk.Entry(
                form,
                bg=THEME["input_bg"],
                fg=THEME["text"],
                insertbackground=THEME["text"],
                width=34,
                relief="flat",
            )
            ent.insert(0, str(val))
            ent.grid(row=row_idx, column=1, sticky="ew", pady=3)
            self.entries[key] = ent

            # Add quick "+1" increment button next to PatientID
            if key == "PatientID":
                make_btn(
                    form,
                    text="+1 ID",
                    cmd=self._bump_id,
                    bg_color=THEME["accent_blue"],
                    fg_color="#ffffff",
                    padx=10,
                    pady=3,
                ).grid(row=row_idx, column=2, padx=(6, 0))

        # Options Checkboxes
        opts = tk.Frame(self, bg=THEME["bg"])
        opts.pack(fill="x", padx=16, pady=(8, 4))

        tk.Checkbutton(
            opts,
            text="Use entered fields as defaults for the rest of this session",
            variable=self.remember_var,
            bg=THEME["bg"],
            fg=THEME["text"],
            selectcolor=THEME["input_bg"],
            activebackground=THEME["bg"],
            activeforeground=THEME["text"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        tk.Checkbutton(
            opts,
            text="Auto-increment PatientID for subsequent patients/folders",
            variable=self.auto_inc_var,
            bg=THEME["bg"],
            fg=THEME["text"],
            selectcolor=THEME["input_bg"],
            activebackground=THEME["bg"],
            activeforeground=THEME["text"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")

        # Action Buttons
        btns = tk.Frame(self, bg=THEME["bg"])
        btns.pack(fill="x", padx=16, pady=(10, 14))

        make_btn(
            btns,
            text="Cancel (Keep Current)",
            cmd=self.destroy,
            bg_color="#374151",
            fg_color="#f9fafb",
            padx=14,
            pady=6,
            bold=False,
        ).pack(side="left")

        make_btn(
            btns,
            text="Apply Tags",
            cmd=self._apply,
            bg_color="#16a34a",
            fg_color="#ffffff",
            padx=16,
            pady=6,
            bold=True,
        ).pack(side="right")

        self.wait_window()

    def _bump_id(self):
        curr = self.entries["PatientID"].get().strip()
        self.entries["PatientID"].delete(0, "end")
        self.entries["PatientID"].insert(0, dicom_profile.increment_patient_id(curr))

    def _apply(self):
        updated = {
            "PatientID": self.entries["PatientID"].get().strip(),
            "AccessionNumber": self.entries["AccessionNumber"].get().strip(),
            "StudyDate": self.entries["StudyDate"].get().strip(),
            "Modality": self.entries["Modality"].get().strip(),
            "StationName": self.entries["StationName"].get().strip(),
            "SeriesDescription": self.entries["SeriesDescription"].get().strip(),
            "InstitutionName": self.entries["InstitutionName"].get().strip(),
            "InstitutionCodeSequence": {
                "CodeValue": self.entries["InstCodeValue"].get().strip(),
                "CodingSchemeDesignator": "MIDAS",
                "CodeMeaning": self.entries["InstCodeMeaning"].get().strip(),
            },
            "IssuerOfPatientID": self.entries["IssuerOfPatientID"].get().strip(),
            "OperatorsName": self.entries["OperatorsName"].get().strip(),
            "ConsultingPhysicianName": self.entries["ConsultingPhysicianName"].get().strip(),
            "ROICreatorSequence": {
                "ObservationSubject": self.entries["ROICreator"].get().strip(),
                "ObserverType": "DEVICE",
            },
            "ROIInterpreterSequence": {
                "ObservationSubject": self.entries["ROIInterpreter"].get().strip(),
                "ObserverType": "PERSON",
            },
            "Manufacturer": self.entries["Manufacturer"].get().strip(),
            "ConsentForDistributionFlag": self.entries["ConsentForDistributionFlag"].get().strip().upper(),
        }
        self.result_tags = updated
        self.destroy()


def get_asset_path(filename: str) -> str:
    """Resolve asset paths for both local development and PyInstaller bundles."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def get_sample_dataset_path() -> str:
    """Resolve model_dataset alongside the application or in its PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        main_module = sys.modules.get("__main__")
        main_file = getattr(main_module, "__file__", None)
        base_dir = (
            Path(main_file).resolve().parent
            if main_file
            else Path(__file__).resolve().parent
        )

    sample_dir = base_dir / "model_dataset"
    return str(sample_dir) if sample_dir.is_dir() else ""


def set_window_icon(root_window, icon_filename: str = "anonymous.ico"):
    """Cross-platform icon setter supporting Windows, macOS, and Linux."""
    icon_path = get_asset_path(icon_filename)
    if not os.path.exists(icon_path):
        return

    try:
        root_window.iconbitmap(icon_path)
    except Exception:
        pass

    try:
        img = Image.open(icon_path)
        icon_photo = ImageTk.PhotoImage(img)
        root_window.iconphoto(True, icon_photo)
        root_window._app_icon_ref = icon_photo
    except Exception:
        pass


class ModernButton(tk.Label):
    """
    Label-based button bypassing the macOS Tkinter Aqua bug,
    providing predictable background colors, borders, and hover states.
    """
    def __init__(self, master, text="", command=None, bg=THEME["btn_slate"],
                 fg="#ffffff", hover_bg=THEME["btn_slate_hover"],
                 font=FONT_BOLD, padx=14, pady=7, **kwargs):
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
            relief="flat",
            **kwargs
        )
        self.command = command
        self.default_bg = bg
        self.hover_bg = hover_bg
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self.configure(bg=self.hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self.default_bg))

    def _on_click(self, event):
        if self.command:
            self.command()


# ──────────────────────────────────────────────────────────────────
# Setup & Import Dialog
# ──────────────────────────────────────────────────────────────────

class StartupDialog:
    def __init__(self):
        self.confirmed = False
        self.selected_images = []
        self.input_dir = ""
        self.output_dir = ""

        if TKDND_AVAILABLE:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("Anonymed — Workspace Setup")
        set_window_icon(self.root, "anonymous.ico")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(True, True)
        self.root.minsize(720, 620)

        w, h = 760, 650
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.root.mainloop()

    def _build(self):
        # Header
        header = tk.Frame(self.root, bg=THEME["bg"], padx=20, pady=14)
        header.pack(fill="x")

        tk.Label(
            header,
            text="Anonymed",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=FONT_TITLE,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Multi-modal medical anonymization (Images, NDPI Slides, DICOM Scans)",
            bg=THEME["bg"],
            fg=THEME["text_muted"],
            font=FONT_BODY,
        ).pack(anchor="w", pady=(2, 0))

        # Main Card
        card = tk.Frame(self.root, bg=THEME["card"], padx=18, pady=16, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # 1. Drag & Drop Zone
        self.drop_frame = tk.Frame(
            card,
            bg=THEME["input_bg"],
            relief="solid",
            bd=1,
            padx=16,
            pady=16,
            cursor="hand2" if TKDND_AVAILABLE else "arrow"
        )
        self.drop_frame.pack(fill="x", pady=(0, 14))

        self.drop_icon = tk.Label(
            self.drop_frame,
            text="📁",
            font=("Helvetica", 22),
            bg=THEME["input_bg"],
            fg=THEME["text"],
        )
        self.drop_icon.pack()

        self.drop_title = tk.Label(
            self.drop_frame,
            text="Drag & drop images, NDPI slides, or DICOM files here",
            font=FONT_HEADING,
            bg=THEME["input_bg"],
            fg=THEME["text"],
        )
        self.drop_title.pack(pady=(2, 2))

        self.drop_sub = tk.Label(
            self.drop_frame,
            text="Supports JPG, PNG, TIFF, BMP, NDPI, DCM (Folders scanned recursively)",
            font=FONT_BODY,
            bg=THEME["input_bg"],
            fg=THEME["text_muted"],
        )
        self.drop_sub.pack()

        if TKDND_AVAILABLE:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            self.drop_frame.dnd_bind("<<DropLeave>>", self._on_drop_leave)
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.drop_sub.config(
                text="⚠️ Drag & drop inactive (tkinterdnd2 not installed). Use Browse below.",
                fg="#f59e0b"
            )

        # 2. Input Source Row
        tk.Label(
            card,
            text="Input Source (File, Folder, or typed path):",
            bg=THEME["card"],
            fg=THEME["text"],
            font=FONT_HEADING,
        ).pack(anchor="w", pady=(0, 4))

        input_row = tk.Frame(card, bg=THEME["card"])
        input_row.pack(fill="x", pady=(0, 12))

        self.var_in = tk.StringVar(value="")
        self.entry_in = tk.Entry(
            input_row,
            textvariable=self.var_in,
            bg=THEME["input_bg"],
            fg=THEME["text"],
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["accent_blue"],
            font=FONT_BODY,
        )
        self.entry_in.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.entry_in.bind("<Return>", lambda e: self._on_entry_input())
        self.entry_in.bind("<FocusOut>", lambda e: self._on_entry_input())

        ModernButton(
            input_row,
            text="Browse Files",
            bg=THEME["accent_blue"],
            hover_bg=THEME["accent_blue_hover"],
            command=self._browse_file,
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 6))

        ModernButton(
            input_row,
            text="Browse Folder",
            bg=THEME["accent_blue"],
            hover_bg=THEME["accent_blue_hover"],
            command=self._browse_folder,
            padx=12,
            pady=6,
        ).pack(side="left")

        sample_path = get_sample_dataset_path()
        if sample_path:
            ModernButton(
                input_row,
                text="Load model_dataset",
                bg=THEME["accent_blue"],
                hover_bg=THEME["accent_blue_hover"],
                command=lambda path=sample_path: self._load_sample_dataset(path),
                padx=10,
                pady=6,
            ).pack(side="left", padx=(6, 0))

        # 3. Queued Items Preview
        queue_header = tk.Frame(card, bg=THEME["card"])
        queue_header.pack(fill="x", pady=(4, 4))

        self.lbl_queue_count = tk.Label(
            queue_header,
            text="Queued Items (0)",
            bg=THEME["card"],
            fg=THEME["text"],
            font=FONT_HEADING,
        )
        self.lbl_queue_count.pack(side="left")

        ModernButton(
            queue_header,
            text="Clear All",
            bg=THEME["card"],
            hover_bg=THEME["input_bg"],
            fg=THEME["text_muted"],
            command=self._clear_all,
            font=FONT_BODY,
            padx=8,
            pady=2,
        ).pack(side="right")

        ModernButton(
            queue_header,
            text="Remove Selected",
            bg=THEME["card"],
            hover_bg=THEME["input_bg"],
            fg=THEME["accent_red"],
            command=self._remove_selected,
            font=FONT_BODY,
            padx=8,
            pady=2,
        ).pack(side="right", padx=(0, 6))

        list_container = tk.Frame(card, bg=THEME["input_bg"], bd=1, relief="solid")
        list_container.pack(fill="both", expand=True, pady=(0, 12))

        scrollbar = tk.Scrollbar(list_container, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.selected_listbox = tk.Listbox(
            list_container,
            bg=THEME["input_bg"],
            fg=THEME["text"],
            selectbackground=THEME["accent_blue"],
            selectforeground="#ffffff",
            font=FONT_MONO,
            activestyle="none",
            highlightthickness=0,
            relief="flat",
            yscrollcommand=scrollbar.set,
            height=5,
        )
        self.selected_listbox.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scrollbar.config(command=self.selected_listbox.yview)

        # 4. Output Destination
        tk.Label(
            card,
            text="Output Folder (Optional — leave blank to save alongside originals):",
            bg=THEME["card"],
            fg=THEME["text_muted"],
            font=FONT_BODY,
        ).pack(anchor="w", pady=(0, 2))

        out_row = tk.Frame(card, bg=THEME["card"])
        out_row.pack(fill="x")

        self.var_out = tk.StringVar(value="")
        self.entry_out = tk.Entry(
            out_row,
            textvariable=self.var_out,
            bg=THEME["input_bg"],
            fg=THEME["text"],
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["accent_blue"],
            font=FONT_BODY,
        )
        self.entry_out.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        ModernButton(
            out_row,
            text="Browse…",
            bg=THEME["btn_slate"],
            hover_bg=THEME["btn_slate_hover"],
            command=self._browse_out,
            padx=12,
            pady=6,
        ).pack(side="left")

        # Footer
        footer = tk.Frame(self.root, bg=THEME["bg"], padx=20, pady=12)
        footer.pack(fill="x")

        self.lbl_status = tk.Label(
            footer,
            text="Ready • Select files or folders to begin",
            bg=THEME["bg"],
            fg=THEME["text_muted"],
            font=FONT_BODY,
        )
        self.lbl_status.pack(side="left")

        ModernButton(
            footer,
            text="Cancel",
            bg=THEME["accent_red"],
            hover_bg=THEME["accent_red_hover"],
            command=self._cancel,
            padx=18,
            pady=8,
        ).pack(side="right", padx=(10, 0))

        ModernButton(
            footer,
            text="Start Processing ▶",
            bg=THEME["accent_green"],
            hover_bg=THEME["accent_green_hover"],
            command=self._confirm,
            padx=20,
            pady=8,
        ).pack(side="right")

    def _on_drop_enter(self, event):
        self.drop_frame.config(bg="#1e3a29")
        self.drop_title.config(bg="#1e3a29", text="Drop items to load", fg=THEME["accent_green"])
        self.drop_sub.config(bg="#1e3a29")
        self.drop_icon.config(bg="#1e3a29")

    def _on_drop_leave(self, event):
        self._reset_drop_style()

    def _reset_drop_style(self):
        self.drop_frame.config(bg=THEME["input_bg"])
        self.drop_title.config(bg=THEME["input_bg"], text="Drag & drop images, NDPI slides, or DICOM files here", fg=THEME["text"])
        self.drop_sub.config(bg=THEME["input_bg"])
        self.drop_icon.config(bg=THEME["input_bg"])

    def _on_drop(self, event):
        self._reset_drop_style()
        try:
            paths = storage.parse_drop_data(event.data)
            self._load_paths(paths)
        except Exception as e:
            self.lbl_status.config(text=f"Error reading drop data: {e}", fg=THEME["accent_red"])

    def _load_paths(self, raw_paths: list):
        if not raw_paths:
            return

        images = storage.collect_images(raw_paths)
        if not images:
            self.lbl_status.config(text="⚠️ No compatible files found in selected path(s).", fg="#f59e0b")
            return

        existing = set(self.selected_images)
        new_items = [img for img in images if img not in existing]
        self.selected_images.extend(new_items)
        self._refresh_queue()

        first_path = raw_paths[0].strip().strip("{}").strip('"').strip("'")
        if os.path.isdir(first_path):
            self.var_in.set(os.path.abspath(first_path))
        elif os.path.isfile(first_path):
            self.var_in.set(os.path.dirname(os.path.abspath(first_path)))

        self.lbl_status.config(text=f"✓ Added {len(new_items)} item(s) to queue", fg=THEME["accent_green"])

    def _on_entry_input(self):
        val = self.var_in.get().strip().strip('"').strip("'")
        if val and os.path.exists(val):
            self._load_paths([val])

    def _load_sample_dataset(self, sample_path: str):
        self.var_in.set(sample_path)
        self.var_out.set("")
        self._load_paths([sample_path])

    def _browse_file(self):
        files = filedialog.askopenfilenames(
            title="Select Medical Files",
            filetypes=[
                ("All Supported Formats", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.ndpi *.dcm"),
                ("DICOM Scans", "*.dcm"),
                ("Hamamatsu NDPI Slides", "*.ndpi"),
                ("Standard Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif"),
                ("All files", "*.*")
            ],
            parent=self.root,
        )
        if files:
            self._load_paths(list(files))

    def _browse_folder(self):
        d = filedialog.askdirectory(
            title="Select Target Folder",
            initialdir=self.var_in.get() or os.path.expanduser("~"),
            parent=self.root,
        )
        if d:
            self._load_paths([d])

    def _browse_out(self):
        d = filedialog.askdirectory(
            title="Select Destination Folder",
            initialdir=self.var_out.get() or self.var_in.get() or os.path.expanduser("~"),
            parent=self.root,
        )
        if d:
            self.var_out.set(d)

    def _refresh_queue(self):
        self.selected_listbox.delete(0, tk.END)
        for img in self.selected_images:
            self.selected_listbox.insert(tk.END, f"  {os.path.basename(img)}  ({img})")
        self.lbl_queue_count.config(text=f"Queued Items ({len(self.selected_images)})")

    def _remove_selected(self):
        selection = self.selected_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        self.selected_images.pop(idx)
        self._refresh_queue()

    def _clear_all(self):
        self.selected_images.clear()
        self._refresh_queue()
        self.lbl_status.config(text="Queue cleared", fg=THEME["text_muted"])

    def _confirm(self):
        in_path = self.var_in.get().strip().strip('"').strip("'")
        out_path = self.var_out.get().strip().strip('"').strip("'")

        if in_path and os.path.exists(in_path) and not self.selected_images:
            self._load_paths([in_path])

        if not self.selected_images:
            messagebox.showerror(
                "Missing Input",
                "Please select one or more files, choose a folder, or drop files.",
                parent=self.root,
            )
            return

        if in_path and os.path.isdir(in_path):
            self.input_dir = in_path
        elif self.selected_images:
            self.input_dir = os.path.dirname(self.selected_images[0])
        else:
            self.input_dir = config.DEFAULT_INPUT_DIR

        self.output_dir = out_path
        self.confirmed = True
        self.root.destroy()

    def _cancel(self):
        self.confirmed = False
        self.root.destroy()


# ──────────────────────────────────────────────────────────────────
# Human Review Interface
# ──────────────────────────────────────────────────────────────────

class ReviewGUI:
    def __init__(self, root, detected_records: list, session_paths: config.SessionPaths, auto_detect_cb=None):
        self.root = root
        set_window_icon(self.root, "anonymous.ico")
        self.records = detected_records
        self.session_paths = session_paths
        self.auto_detect_cb = auto_detect_cb
        self.idx = 0
        self.history = []

        self.img_cv = None
        self.auto_boxes = []
        self.active_auto = []
        self.user_boxes = []
        self.draw_start = None
        self.draw_rect = None
        self.scale = 1.0
        self._metadata_only = False

        self._build_ui()
        self.root.after(150, lambda: self._load(0))

        self.midas_tags = copy.deepcopy(config.DEFAULT_MIDAS_TAGS)
        self.auto_increment_id = True
        self.patient_id_map = {}  # Maps original source folder/patient key -> assigned pseudo PatientID
        self.saved_inline_dcm_edits = {}
    
    def _get_tags_for_record(self, rec: dict) -> dict:
        """
        Returns per-file manual tags if customized; otherwise resolves explicitly
        entered session tags and an optional auto-incremented PatientID per folder.
        """
        if "custom_midas_tags" in rec:
            return rec["custom_midas_tags"]

        # Group slices in the same directory under the same PatientID; increment for new folders
        parent_key = os.path.dirname(rec["original_path"])
        if parent_key not in self.patient_id_map:
            assigned_id = self.midas_tags.get("PatientID", "")
            self.patient_id_map[parent_key] = assigned_id
            if self.auto_increment_id and assigned_id:
                self.midas_tags["PatientID"] = dicom_profile.increment_patient_id(assigned_id)

        resolved = copy.deepcopy(self.midas_tags)
        resolved["PatientID"] = self.patient_id_map[parent_key]
        return resolved

    def _edit_dicom_tags_for_current(self):
        """Button handler allowing optional manual tag editing for the current DICOM file."""
        rec = self.records[self.idx]
        if not rec.get("is_dcm", False):
            return
        current = self._get_tags_for_record(rec)
        dlg = DicomTagDialog(
            self.root,
            current,
            title=f"Edit DICOM Tags — {rec['filename']}",
        )
        if dlg.result_tags is not None:
            rec["custom_midas_tags"] = dlg.result_tags
            self.auto_increment_id = dlg.auto_inc_var.get()
            if dlg.remember_var.get():
                # Update the session baseline and prepare the next folder's ID.
                self.midas_tags = copy.deepcopy(dlg.result_tags)
                if self.auto_increment_id and dlg.result_tags["PatientID"]:
                    self.midas_tags["PatientID"] = dicom_profile.increment_patient_id(
                        dlg.result_tags["PatientID"]
                    )
                        
    def _build_ui(self):
        self.root.title("Anonymed — Review & Quality Control")
        self.root.configure(bg=THEME["bg"])
        self.root.resizable(True, True)

        # Top Information Bar
        top = tk.Frame(self.root, bg=THEME["card"], pady=8, padx=16)
        top.pack(fill="x")

        self.lbl_file = tk.Label(
            top, text="", bg=THEME["card"], fg=THEME["text"],
            font=("Helvetica", 11, "bold"), anchor="w"
        )
        self.lbl_file.pack(side="left", fill="x", expand=True)

        self.lbl_stat = tk.Label(
            top, text="", bg=THEME["card"], fg=THEME["text_muted"],
            font=FONT_BODY
        )
        self.lbl_stat.pack(side="right")

        # Canvas Area
        self.canvas = tk.Canvas(
            self.root, bg="#000000", cursor="crosshair",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._right_click)

        self._build_inline_dicom_editor(self.root)

        # Bottom Controls
        bot = tk.Frame(self.root, bg=THEME["card"], pady=10, padx=12)
        bot.pack(fill="x")

        # Navigation & Edits (Left)
        ModernButton(bot, text="◀ Prev", bg=THEME["accent_blue"], hover_bg=THEME["accent_blue_hover"],
                     command=self._prev, padx=10, pady=6).pack(side="left", padx=3)
        ModernButton(bot, text="Next ▶", bg=THEME["accent_blue"], hover_bg=THEME["accent_blue_hover"],
                     command=self._next, padx=10, pady=6).pack(side="left", padx=3)
        ModernButton(bot, text="↩ Undo", bg=THEME["btn_slate"], hover_bg=THEME["btn_slate_hover"],
                     command=self._undo, padx=10, pady=6).pack(side="left", padx=3)
        ModernButton(bot, text="Clear Manual", bg=THEME["accent_red"], hover_bg=THEME["accent_red_hover"],
                     command=self._clear_manual, padx=10, pady=6).pack(side="left", padx=3)
        ModernButton(bot, text="All Auto ON", bg=THEME["btn_slate"], hover_bg=THEME["btn_slate_hover"],
                     command=self._all_auto_on, padx=8, pady=6).pack(side="left", padx=3)
        ModernButton(bot, text="All Auto OFF", bg=THEME["btn_slate"], hover_bg=THEME["btn_slate_hover"],
                     command=self._all_auto_off, padx=8, pady=6).pack(side="left", padx=3)
        self.btn_dicom_tags = tk.Label(
            bot,
            text="DICOM Tags",
            bg=THEME["card"],
            fg=THEME["text_muted"],
            relief="flat",
            padx=10,
            pady=6,
            font=FONT_BOLD,
            cursor="arrow",
        )
        self.btn_dicom_tags.pack(side="left", padx=3)
        self._dicom_btn_enabled = False

        def on_dicom_click(event=None):
            if self._dicom_btn_enabled:
                self._edit_dicom_tags_for_current()

        def on_dicom_enter(event=None):
            if self._dicom_btn_enabled:
                self.btn_dicom_tags.config(bg=THEME["accent_blue_hover"])

        def on_dicom_leave(event=None):
            if self._dicom_btn_enabled:
                self.btn_dicom_tags.config(bg=THEME["accent_blue"])

        self.btn_dicom_tags.bind("<Button-1>", on_dicom_click)
        self.btn_dicom_tags.bind("<Enter>", on_dicom_enter)
        self.btn_dicom_tags.bind("<Leave>", on_dicom_leave)

        # Primary Actions (Right)
        ModernButton(bot, text="✔ Save & Next", bg=THEME["accent_green"], hover_bg=THEME["accent_green_hover"],
                     command=self._save_next, padx=16, pady=6).pack(side="right", padx=4)
        ModernButton(bot, text="Skip (Leave Intact)", bg=THEME["btn_slate"], hover_bg=THEME["btn_slate_hover"],
                     command=self._skip, padx=10, pady=6).pack(side="right", padx=4)

        # Legend
        leg = tk.Frame(bot, bg=THEME["card"])
        leg.pack(side="right", padx=16)
        for r, (sym, col, txt) in enumerate([
            ("■", "#f59e0b", " Auto"),
            ("■", "#ef4444", " Manual"),
            ("■", "#555869", " Disabled"),
        ]):
            tk.Label(leg, text=sym, fg=col, bg=THEME["card"], font=("Arial", 11)).grid(row=r, column=0, sticky="w")
            tk.Label(leg, text=txt, fg=THEME["text_muted"], bg=THEME["card"], font=FONT_BODY).grid(row=r, column=1, sticky="w")

        # Bottom-Left Physical File Path Bar
        bottom_bar = tk.Frame(self.root, bg=THEME["card"], pady=4, padx=10)
        bottom_bar.pack(side="bottom", fill="x")

        tk.Label(
            bottom_bar,
            text="Location:",
            font=FONT_HEADING,
            fg="#89b4fa",
            bg=THEME["card"],
        ).pack(side="left", padx=(0, 6))

        self.file_path_var = tk.StringVar(value="")
        self.file_path_entry = tk.Entry(
            bottom_bar,
            textvariable=self.file_path_var,
            state="readonly",
            readonlybackground=THEME["card"],
            fg=THEME["text_muted"],
            relief="flat",
            font=FONT_MONO,
        )
        self.file_path_entry.pack(side="left", fill="x", expand=True)

        # Shortcuts
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Left>", lambda e: self._prev())
        self.root.bind("<Right>", lambda e: self._next())
        self.root.after(500, lambda: self.root.bind("<Return>", lambda e: self._save_next()))

        if TKDND_AVAILABLE:
            try:
                self.canvas.drop_target_register(DND_FILES)
                self.canvas.dnd_bind("<<Drop>>", self._on_review_drop)
            except Exception:
                pass

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_inline_dicom_editor(self, parent_container):
        """Creates the inline DICOM metadata table used when a file has no pixels."""
        import dicom_scrubber

        self.dcm_meta_frame = tk.Frame(
            parent_container, bg=THEME["bg"], padx=18, pady=14
        )
        self.inline_dcm_entries = {}
        self.inline_dcm_current_vars = {}
        self.inline_dcm_original_values = {}

        tk.Label(
            self.dcm_meta_frame,
            text="Metadata-Only DICOM Detected (No Pixel Data) — Direct Tag Editor",
            font=FONT_TITLE,
            fg=THEME["text"],
            bg=THEME["bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            self.dcm_meta_frame,
            text="Enter a value only for tags to modify. Leave Column 3 blank to keep the current value.",
            font=FONT_BODY,
            fg=THEME["text_muted"],
            bg=THEME["bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        table = tk.Frame(self.dcm_meta_frame, bg=THEME["bg"])
        table.pack(fill="both", expand=True)
        for column, width in enumerate((2, 2, 2)):
            table.columnconfigure(column, weight=width, minsize=220)

        headers = (
            "1. Metadata Name & DICOM Tag",
            "2. Current / Saved Preview",
            "3. Modify With (Leave Blank to Keep)",
        )
        for column, text in enumerate(headers):
            tk.Label(
                table,
                text=text,
                font=FONT_HEADING,
                fg=THEME["text"],
                bg=THEME["card"],
                anchor="w",
                padx=8,
                pady=6,
            ).grid(row=0, column=column, sticky="ew", padx=2, pady=(0, 6))

        for row_index, (key, label, _) in enumerate(
            dicom_scrubber.MIDAS_INLINE_SCHEMA, start=1
        ):
            tk.Label(
                table,
                text=label,
                font=FONT_BODY,
                fg=THEME["text"],
                bg=THEME["bg"],
                anchor="w",
                padx=8,
                pady=4,
            ).grid(row=row_index, column=0, sticky="ew", padx=2, pady=2)

            current_var = tk.StringVar(value="")
            self.inline_dcm_current_vars[key] = current_var
            tk.Entry(
                table,
                textvariable=current_var,
                state="readonly",
                readonlybackground=THEME["card"],
                fg=THEME["text_muted"],
                relief="flat",
                font=FONT_MONO,
            ).grid(row=row_index, column=1, sticky="ew", padx=4, pady=2, ipady=4)

            new_entry = tk.Entry(
                table,
                bg=THEME["input_bg"],
                fg=THEME["text"],
                insertbackground=THEME["text"],
                relief="flat",
                font=FONT_MONO,
            )
            new_entry.grid(row=row_index, column=2, sticky="ew", padx=4, pady=2, ipady=4)
            new_entry.bind(
                "<KeyRelease>",
                lambda event, field_key=key: self._update_inline_dicom_preview(field_key),
            )
            self.inline_dcm_entries[key] = new_entry

    def _populate_inline_dicom_editor(self, dcm_path: str, rec: dict):
        import dicom_scrubber

        path_key = os.path.abspath(dcm_path)
        saved_edits = self.saved_inline_dcm_edits.get(path_key, {})
        for row in dicom_scrubber.read_current_dicom_schema(dcm_path):
            key = row["key"]
            self.inline_dcm_original_values[key] = row["current"]
            entry = self.inline_dcm_entries[key]
            entry.delete(0, tk.END)
            entry.insert(0, saved_edits.get(key, ""))
            self._update_inline_dicom_preview(key)

    def _update_inline_dicom_preview(self, key: str) -> None:
        self.inline_dcm_current_vars[key].set(
            self.inline_dcm_entries[key].get().strip()
            or self.inline_dcm_original_values.get(key, "")
        )

    def get_inline_dicom_modifications(self) -> dict:
        return {
            key: entry.get().strip()
            for key, entry in self.inline_dcm_entries.items()
        }

    def _cache_inline_dicom_edits(self, rec: dict) -> dict:
        edits = {
            key: value
            for key, value in self.get_inline_dicom_modifications().items()
            if value
        }
        path_key = os.path.abspath(rec["original_path"])
        if edits:
            self.saved_inline_dcm_edits[path_key] = edits
        else:
            self.saved_inline_dcm_edits.pop(path_key, None)
        return edits

    def _on_close(self):
        if messagebox.askyesno("Exit Review", "Exit review now?\nPreviously saved items will remain intact."):
            self.root.destroy()

    def _persist_current_state(self):
        """Preserves user edits and box toggles across PREV / NEXT navigation."""
        if 0 <= self.idx < len(self.records):
            self.records[self.idx]["active_auto"] = copy.copy(self.active_auto)
            self.records[self.idx]["user_boxes"] = copy.copy(self.user_boxes)
            self.records[self.idx]["persisted"] = True
            if self._metadata_only:
                self._cache_inline_dicom_edits(self.records[self.idx])

    def _load(self, idx):
        self.idx = idx
        self.history = []
        rec = self.records[idx]
        self.file_path_var.set(os.path.abspath(rec["original_path"]))
        self._metadata_only = False
        is_dcm = bool(rec.get("is_dcm", False))
        if is_dcm:
            import dicom_scrubber

            if "has_pixel_data" not in rec:
                try:
                    rec["has_pixel_data"] = dicom_scrubber.dicom_has_pixel_data(
                        rec["original_path"]
                    )
                except Exception as error:
                    rec["dicom_pixel_check_error"] = str(error)
                    messagebox.showerror(
                        "DICOM Read Error",
                        f"Could not inspect pixel data in {rec['filename']}:\n{error}",
                        parent=self.root,
                    )
                    rec["has_pixel_data"] = True
            self._metadata_only = not rec["has_pixel_data"]

        self._dicom_btn_enabled = is_dcm and not self._metadata_only
        if self._dicom_btn_enabled:
            self.btn_dicom_tags.config(
                bg=THEME["accent_blue"],
                fg="#ffffff",
                cursor="hand2",
            )
        else:
            self.btn_dicom_tags.config(
                bg=THEME["card"],
                fg=THEME["text_muted"],
                cursor="arrow",
            )
        if self._metadata_only:
            self.canvas.pack_forget()
            self.dcm_meta_frame.pack(fill="both", expand=True, padx=6, pady=6)
            self.btn_dicom_tags.pack_forget()
            try:
                self._populate_inline_dicom_editor(rec["original_path"], rec)
            except Exception as error:
                messagebox.showerror(
                    "DICOM Metadata Read Error",
                    f"Could not load metadata for {rec['filename']}:\n{error}",
                    parent=self.root,
                )
                self._metadata_only = False
                self._dicom_btn_enabled = True
                self.dcm_meta_frame.pack_forget()
                self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
                self.btn_dicom_tags.config(
                    bg=THEME["accent_blue"],
                    fg="#ffffff",
                    cursor="hand2",
                )
                self.btn_dicom_tags.pack(side="left", padx=3)
        else:
            self.dcm_meta_frame.pack_forget()
            if not self.canvas.winfo_manager():
                self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
            if is_dcm and not self.btn_dicom_tags.winfo_manager():
                self.btn_dicom_tags.pack(side="left", padx=3)

        self.img_cv = rec["img"]

        # Restore previously toggled state or initialize freshly
        if rec.get("persisted", False):
            self.auto_boxes = list(rec["auto_boxes"])
            self.active_auto = list(rec["active_auto"])
            self.user_boxes = list(rec["user_boxes"])
        else:
            self.auto_boxes = list(rec["auto_boxes"])
            self.active_auto = [True] * len(self.auto_boxes)
            self.user_boxes = []

        self._refresh_labels()
        self._render()

    def _refresh_labels(self):
        rec = self.records[self.idx]
        n_on = sum(self.active_auto)
        n_man = len(self.user_boxes)
        kw = rec.get("kw_hits", 0)
        kw_tag = f"  │  Keywords: {kw}" if kw else ""

        file_type_tag = ""
        if rec.get("is_wsi", False):
            file_type_tag = " [WSI NDPI Slide]"
        elif rec.get("is_dcm", False):
            file_type_tag = " [DICOM Scan]"

        self.lbl_file.config(text=f"{rec['filename']}{file_type_tag}")
        self.lbl_stat.config(
            text=f"Item {self.idx + 1} of {len(self.records)}   Auto: {n_on}/{len(self.auto_boxes)}   Manual: {n_man}   Total: {n_on + n_man}{kw_tag}"
        )

    def _c(self, x, y, w, h):
        s = self.scale
        return int(x * s), int(y * s), int(w * s), int(h * s)

    def _img_pt(self, cx, cy):
        return cx / self.scale, cy / self.scale

    def _render(self):
        self.canvas.delete("all")
        if self._metadata_only:
            self._refresh_labels()
            return

        if self.img_cv is None:
            rec = self.records[self.idx]
            cw = max(self.canvas.winfo_width(), config.MAX_DISPLAY_W)
            ch = max(self.canvas.winfo_height(), config.MAX_DISPLAY_H)
            if rec.get("is_dcm", False):
                msg = "[DICOM Pixels or Metadata Could Not Be Displayed]"
                text_color = THEME["accent_red"]
            else:
                msg = "[Binary WSI Slide Mode — Click 'Save & Next' to Unlink Macro IFD]"
                text_color = THEME["text_muted"]

            self.canvas.create_text(
                cw // 2,
                ch // 2,
                text=msg,
                fill=text_color,
                font=("Segoe UI", 12, "bold"),
                justify="center",
            )
            self._refresh_labels()
            return

        img = self.img_cv
        H, W = img.shape[:2]
        self.root.update_idletasks()
        cw = max(self.canvas.winfo_width(), config.MAX_DISPLAY_W)
        ch = max(self.canvas.winfo_height(), config.MAX_DISPLAY_H)
        self.scale = min(cw / W, ch / H, 1.0)
        dw = max(1, int(W * self.scale))
        dh = max(1, int(H * self.scale))

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(pil)
        self.canvas.config(width=dw, height=dh)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

        # Render auto detected boxes
        for i, (x, y, w, h) in enumerate(self.auto_boxes):
            cx, cy, cw2, ch2 = self._c(x, y, w, h)
            on = self.active_auto[i]
            self.canvas.create_rectangle(
                cx, cy, cx + cw2, cy + ch2,
                outline="#f59e0b" if on else "#555869",
                width=2 if on else 1, dash=(8, 3), tags=f"auto_{i}",
            )

        # Render manually drawn boxes
        for i, (x, y, w, h) in enumerate(self.user_boxes):
            cx, cy, cw2, ch2 = self._c(x, y, w, h)
            self.canvas.create_rectangle(cx, cy, cx + cw2, cy + ch2, outline="#ef4444", width=2, tags=f"usr_{i}")

        self._refresh_labels()

    def _press(self, event):
        if self.img_cv is None:
            return
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
        self.draw_rect = self.canvas.create_rectangle(x0, y0, event.x, event.y, outline="#ef4444", width=2, dash=(4, 2))

    def _release(self, event):
        if not self.draw_start or self.img_cv is None:
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
        if self.img_cv is None:
            return
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
            "user_boxes": copy.copy(self.user_boxes),
        })

    def _undo(self):
        if not self.history:
            return
        state = self.history.pop()
        self.active_auto = state["active_auto"]
        self.user_boxes = state["user_boxes"]
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
        rec = self.records[self.idx]
        target_out_path = storage.get_destination_path(
            self.session_paths.session_output_dir,
            rec["original_path"],
            self.session_paths.input_dir,
        )

        # 1. Whole-Slide Image (NDPI)
        if rec.get("is_wsi", False):
            import wsi_scrubber
            out_path = wsi_scrubber.anonymize_ndpi_file(
                rec["original_path"],
                target_out_path,
            )
            storage.append_anonymized_csv(
                self.session_paths.anonymized_csv,
                {
                    "original_path": rec["original_path"],
                    "anonymized_path": out_path,
                    "num_auto_kept": 0,
                    "num_manual": 0,
                    "total": 0,
                },
            )
            print(f"  [SAVED WSI] {out_path} (Macro IFD unlinked + metadata scrubbed)")
            self._advance()
            return

        final_boxes = [b for i, b in enumerate(self.auto_boxes) if self.active_auto[i]] + self.user_boxes
        n_auto = sum(self.active_auto)
        n_man = len(self.user_boxes)
        # 2. DICOM Scan (.dcm)
        if rec.get("is_dcm", False):
            import dicom_scrubber

            inline_modifications = self._cache_inline_dicom_edits(rec) if self._metadata_only else None
            active_tags = None if self._metadata_only else self._get_tags_for_record(rec)
            out_path = dicom_scrubber.save_anonymized_dicom(
                rec["original_path"],
                target_out_path,
                final_boxes,
                tag_config=active_tags,
                inline_modifications=inline_modifications,
            )

            storage.append_anonymized_csv(
                self.session_paths.anonymized_csv,
                {
                    "original_path": rec["original_path"],
                    "anonymized_path": out_path,
                    "num_auto_kept": n_auto,
                    "num_manual": n_man,
                    "total": n_auto + n_man,
                },
            )
            print(f"  [SAVED DICOM] {out_path} (auto:{n_auto} manual:{n_man} + MIDAS tags applied)")
            self._advance()
            return

        # 3. Standard 2D Image (.jpg, .png, .tiff, .bmp)
        out_path = storage.save_anonymized(
            target_out_path, self.img_cv, final_boxes
        )
        storage.append_anonymized_csv(
            self.session_paths.anonymized_csv,
            {
                "original_path": rec["original_path"],
                "anonymized_path": out_path,
                "num_auto_kept": n_auto,
                "num_manual": n_man,
                "total": n_auto + n_man,
            },
        )
        print(f"  [SAVED] {out_path} (auto:{n_auto} manual:{n_man})")
        self._advance()

    def _skip(self):
        rec = self.records[self.idx]
        target_out_path = storage.get_destination_path(
            self.session_paths.session_output_dir,
            rec["original_path"],
            self.session_paths.input_dir,
        )
        shutil.copy2(rec["original_path"], target_out_path)
        storage.append_anonymized_csv(
            self.session_paths.anonymized_csv,
            {
                "original_path": rec["original_path"],
                "anonymized_path": target_out_path,
                "num_auto_kept": 0,
                "num_manual": 0,
                "total": 0,
            },
        )
        print(f"  [SKIP]  {rec['filename']} → copied unchanged to {target_out_path}")
        self._advance()

    def _advance(self):
        if self.idx < len(self.records) - 1:
            self._load(self.idx + 1)
        else:
            messagebox.showinfo(
                "Review Complete",
                f"All {len(self.records)} items processed successfully.\n\nAudit log saved to:\n{self.session_paths.anonymized_csv}",
                parent=self.root
            )
            self.root.quit()

    def _prev(self):
        if self.idx > 0:
            self._persist_current_state()
            self._load(self.idx - 1)

    def _next(self):
        if self.idx < len(self.records) - 1:
            self._persist_current_state()
            self._load(self.idx + 1)

    def _on_review_drop(self, event):
        if not self.auto_detect_cb:
            return
        try:
            paths = storage.parse_drop_data(event.data)
            new_images = storage.collect_images(paths)
            if not new_images:
                return

            existing = {rec["original_path"] for rec in self.records}
            truly_new = [img for img in new_images if img not in existing]
            if not truly_new:
                messagebox.showinfo("Already Loaded", "Dropped items are already in queue.", parent=self.root)
                return

            for img_path in truly_new:
                ext = os.path.splitext(img_path)[1].lower()
                if ext == ".ndpi":
                    import wsi_scrubber
                    thumb = wsi_scrubber.get_ndpi_thumbnail_bgr(img_path)
                    self.records.append({
                        "original_path": img_path,
                        "filename": os.path.basename(img_path),
                        "img": thumb,
                        "auto_boxes": [],
                        "kw_hits": 0,
                        "is_wsi": True,
                        "is_dcm": False,
                    })
                else:
                    boxes, img, kw_hits = self.auto_detect_cb(img_path)
                    self.records.append({
                        "original_path": img_path,
                        "filename": os.path.basename(img_path),
                        "img": img,
                        "auto_boxes": boxes if boxes else [],
                        "kw_hits": kw_hits,
                        "is_wsi": False,
                        "is_dcm": (ext == ".dcm"),
                    })

            messagebox.showinfo("Queue Updated", f"Added {len(truly_new)} new item(s) to review queue.", parent=self.root)
            self._refresh_labels()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self.root)