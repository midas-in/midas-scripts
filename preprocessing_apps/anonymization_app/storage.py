"""
storage.py – Recursive discovery, directory mirroring, image saving, and CSV audit logs.
"""

import csv
from datetime import datetime
import os
import re
import cv2
from PIL import Image
import config

from wsi_scrubber import process_wsi_pipeline

def save_anonymized_wsi(session_output_dir: str, src_path: str, filename: str) -> str:
    """Wrapper to run binary unlinking and metadata scrubbing for NDPI files."""
    out_ndpi, out_json = process_wsi_pipeline(src_path, session_output_dir)
    return out_ndpi


def collect_images(paths: list) -> list:
    images = set()
    for path in paths:
        path = path.strip().strip("{}").strip('"').strip("'")
        if not os.path.exists(path):
            print(f"  [WARN] Path not found: {path}")
            continue

        try:
            if os.path.isfile(path):
                if path.lower().endswith(config.SUPPORTED_EXTENSIONS):
                    if not os.path.basename(path).startswith("anonymized_"):
                        images.add(os.path.abspath(path))
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for file in files:
                        if file.startswith(".") or file.startswith("anonymized_"):
                            continue
                        if file.lower().endswith(config.SUPPORTED_EXTENSIONS):
                            images.add(os.path.abspath(os.path.join(root, file)))
        except PermissionError:
            print(f"  [WARN] Permission denied: {path}")
        except Exception as e:
            print(f"  [WARN] Error processing {path}: {e}")

    return sorted(images)


def parse_drop_data(data: str) -> list:
    if "{" in data:
        paths = re.findall(r"\{([^}]+)\}", data)
    else:
        parts = data.split()
        paths = [p.strip('"').strip("'") for p in parts if p.strip()]
    return [p for p in paths if p]


def get_destination_path(session_output_dir: str, original_path: str, base_input_dir: str) -> str:
    """Return an anonymized path under the session directory, preserving relative folders."""
    try:
        rel_dir = os.path.relpath(os.path.dirname(original_path), base_input_dir)
        if rel_dir == os.pardir or rel_dir.startswith(os.pardir + os.sep):
            raise ValueError("Source file is outside the input directory")
        target_dir = session_output_dir if rel_dir in (".", "") else os.path.join(session_output_dir, rel_dir)
    except (OSError, ValueError):
        target_dir = session_output_dir

    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, f"anonymized_{os.path.basename(original_path)}")


def save_anonymized(target_out_path: str, img, boxes: list) -> str:
    """Save a 2D image with redacted boxes to its explicit destination path."""
    os.makedirs(os.path.dirname(target_out_path), exist_ok=True)
    out = img.copy()
    for x, y, w, h in boxes:
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 0), -1)
    if not cv2.imwrite(target_out_path, out):
        raise OSError(f"Could not write anonymized image to {target_out_path}")
    return target_out_path


def append_anonymized_csv(csv_path: str, row: dict):
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "original_path",
                "anonymized_path",
                "num_auto_boxes_kept",
                "num_manual_boxes",
                "total_boxes_applied",
                "reviewed_at",
            ])
        writer.writerow([
            row["original_path"],
            row["anonymized_path"],
            row["num_auto_kept"],
            row["num_manual"],
            row["total"],
            datetime.now().isoformat(timespec="seconds"),
        ])

def copy_sanitized_image(src_path: str, dst_path: str):
    """
    Copies image while stripping EXIF metadata (GPS, serials, timestamps).
    Keeps file naming intact without transferring raw camera tags.
    """
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with Image.open(src_path) as im:
        data = list(im.getdata())
        clean_im = Image.new(im.mode, im.size)
        clean_im.putdata(data)
        clean_im.save(dst_path)