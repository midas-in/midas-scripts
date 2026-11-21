#!/usr/bin/env python3
"""
main.py – Primary orchestrator running setup, docTR initialization, batch detection, and human review.
Supports 2D images, WSI (.ndpi), and DICOM (.dcm) files.
"""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import csv
from datetime import datetime
import sys
import tkinter as tk
from tkinter import messagebox
from doctr.models import ocr_predictor

import config
import cv_utils
import detectors
from gui import (
    ProcessingStatusWindow,
    ReviewGUI,
    StartupDialog,
    TKDND_AVAILABLE,
    TkinterDnD,
)
from keywords import KeywordMatcher
import storage
import wsi_scrubber


def run_phase1_detection(
    image_paths: list,
    model,
    matcher: KeywordMatcher,
    csv_path: str,
    status_window: ProcessingStatusWindow = None,
) -> list:
    print(f"\n{'═' * 60}")
    print(f"  PHASE 1 — Auto-detection on {len(image_paths)} image(s)")
    print(f"{'═' * 60}")

    detected = []
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "original_path",
            "filename",
            "num_auto_boxes",
            "auto_boxes_coords",
            "keyword_hits",
            "file_type",
            "detected_at",
        ])

        for index, path in enumerate(image_paths, start=1):
            name = os.path.basename(path)
            ext = os.path.splitext(name)[1].lower()

            # 1. Whole-Slide Image (Hamamatsu NDPI)
            if ext == ".ndpi":
                if status_window:
                    status_window.log_status(
                        f"Inspecting WSI macro label ({index}/{len(image_paths)}): {name}"
                    )
                print(f"  [WSI Slide] {name} flagged for Macro IFD unlinking & tag scrub")
                thumb = wsi_scrubber.get_ndpi_thumbnail_bgr(path)
                row = {
                    "original_path": path,
                    "filename": name,
                    "img": thumb,
                    "auto_boxes": [],
                    "kw_hits": 0,
                    "is_wsi": True,
                    "is_dcm": False,
                }
                detected.append(row)
                writer.writerow([
                    path,
                    name,
                    0,
                    "WSI_MACRO_STRIPPED",
                    0,
                    "WSI",
                    datetime.now().isoformat(timespec="seconds"),
                ])
                if status_window:
                    status_window.record_image_result(False)
                continue

            # 2. Standard 2D Images and DICOM Scans
            is_dcm = (ext == ".dcm")
            prefix_label = "[DICOM] " if is_dcm else ""
            if status_window:
                status_window.log_status(
                    f"Scanning slice {index}/{len(image_paths)} ({name})..."
                )
            print(f"  Scanning {prefix_label}{name} …", end=" ", flush=True)

            boxes, img, kw_hits = detectors.auto_detect(model, path, matcher)
            
            box_count = len(boxes) if boxes else 0
            kw_tag = f"  [{kw_hits} keyword hit(s)]" if kw_hits else ""
            status_tag = f"{box_count} box(es) detected{kw_tag}" if box_count > 0 else "0 boxes (flagged for review)"
            print(status_tag)

            row = {
                "original_path": path,
                "filename": name,
                "img": img,
                "auto_boxes": boxes if boxes else [],
                "kw_hits": kw_hits,
                "is_wsi": False,
                "is_dcm": is_dcm,
            }
            detected.append(row)
            writer.writerow([
                path,
                name,
                box_count,
                cv_utils.boxes_to_str(boxes) if boxes else "",
                kw_hits,
                "DICOM" if is_dcm else "2D_IMAGE",
                datetime.now().isoformat(timespec="seconds"),
            ])
            if status_window:
                status_window.record_image_result(bool(boxes or kw_hits))

    print(f"\n  → {len(detected)} item(s) queued for human review")
    print(f"  → detection_log written to {csv_path}\n")
    return detected


def main():
    # 1. Startup folder & file picker
    dialog = StartupDialog()
    if not dialog.confirmed:
        print("[INFO] Setup cancelled — exiting.")
        sys.exit(0)

    # 2. Derive timestamped session paths
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    paths = config.SessionPaths.create(
        input_dir=dialog.input_dir, output_dir=dialog.output_dir, timestamp=timestamp
    )

    print(f"[INFO] Input  → {paths.input_dir}")
    print(f"[INFO] Output → {paths.session_output_dir}")
    print(f"[INFO] Logs   → {paths.logs_dir}")

    # 3. Gather unique target files before loading the OCR model
    if dialog.selected_images:
        images = dialog.selected_images
    else:
        images = storage.collect_images([paths.input_dir])

    # De-duplicate while preserving insertion order
    seen = set()
    images = [x for x in images if not (x in seen or seen.add(x))]

    if not images:
        messagebox.showwarning(
            "No compatible files",
            f"No supported files found in:\n{paths.input_dir}\n\nSupported: {', '.join(config.SUPPORTED_EXTENSIONS)}",
        )
        sys.exit(0)

    status_window = ProcessingStatusWindow(total_files=len(images))
    try:
        # 4. Load docTR OCR engine
        status_window.log_status("Loading docTR OCR weights...")
        print("[INFO] Loading docTR model …")
        model = ocr_predictor(pretrained=True)

        # 5. Keyword rules initialization
        matcher = KeywordMatcher(paths.phi_keywords_file)

        # 6. Phase 1 — Batch detection
        detected = run_phase1_detection(
            images, model, matcher, paths.detection_csv, status_window=status_window
        )
    finally:
        status_window.close()

    if not detected:
        messagebox.showinfo("No images", "No valid images could be read.\nNothing to review.")
        sys.exit(0)

    # 7. Phase 2 — Interactive Review Window
    print(f"{'═' * 60}")
    print(f"  PHASE 2 — Human Review  ({len(detected)} item(s))")
    print(f"{'═' * 60}\n")
    print("  Controls:")
    print("    Left-click auto box    → toggle on/off")
    print("    Left-drag anywhere     → draw manual redaction box")
    print("    Right-click manual box → remove it")
    print("    Ctrl+Z / ↩ UNDO        → undo last action")
    print("    Enter / SAVE & NEXT    → save and advance\n")

    if TKDND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
    else:
        root = tk.Tk()

    root.geometry(f"{config.MAX_DISPLAY_W}x{config.MAX_DISPLAY_H + 140}")

    detect_callback = lambda p: detectors.auto_detect(model, p, matcher)
    ReviewGUI(root, detected, paths, auto_detect_cb=detect_callback)
    root.mainloop()

    print("\n[DONE]")
    print(f"  Detection log  → {paths.detection_csv}")
    print(f"  Anonymized log → {paths.anonymized_csv}")


if __name__ == "__main__":
    main()