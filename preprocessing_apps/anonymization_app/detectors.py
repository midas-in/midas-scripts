"""
detectors.py – OCR and visual heuristic detectors for paper labels and meta-strips.
"""

import os
import tempfile
import cv2
import numpy as np
from doctr.io import DocumentFile
import config
import cv_utils
import dicom_scrubber


def run_doctr_on_image(model, img_path: str):
    try:
        doc = DocumentFile.from_images([img_path])
        result = model(doc)
    except Exception as e:
        print(f"  [docTR ERROR] {e}")
        return []
    page = result.pages[0]
    h_dim, w_dim = page.dimensions
    words = []
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                words.append((word, h_dim, w_dim))
    return words


def run_doctr_on_crop(model, gray_crop: np.ndarray, offset_x: int, offset_y: int, full_shape: tuple):
    rgb_crop = cv2.cvtColor(gray_crop, cv2.COLOR_GRAY2RGB)
    tmp_path = "/tmp/_label_crop_doctr.png"
    cv2.imwrite(tmp_path, rgb_crop)
    try:
        doc = DocumentFile.from_images([tmp_path])
        result = model(doc)
    except Exception as e:
        print(f"  [docTR-crop ERROR] {e}")
        return []

    page = result.pages[0]
    h_dim, w_dim = page.dimensions
    boxes = []
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                if word.confidence < config.DOCTR_CONF_THRESHOLD:
                    continue
                (x1, y1), (x2, y2) = word.geometry
                x = int(x1 * w_dim) + offset_x
                y = int(y1 * h_dim) + offset_y
                bw = int((x2 - x1) * w_dim)
                bh = int((y2 - y1) * h_dim)
                if bw < config.DOCTR_MIN_W or bh < config.DOCTR_MIN_H:
                    continue
                boxes.append(cv_utils.clamp_box(x, y, bw, bh, full_shape))
    return boxes


def detect_ocr(model, img_path: str, img_bgr: np.ndarray, keyword_matcher=None):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    words = run_doctr_on_image(model, img_path)
    ruler_bbox = cv_utils.detect_ruler_strip(img_bgr)
    boxes = []
    kw_hits = 0

    for word, h_dim, w_dim in words:
        if word.confidence < config.DOCTR_CONF_THRESHOLD:
            continue
        (x1, y1), (x2, y2) = word.geometry
        x = int(x1 * w_dim)
        y = int(y1 * h_dim)
        bw = int((x2 - x1) * w_dim)
        bh = int((y2 - y1) * h_dim)

        if bw < config.DOCTR_MIN_W or bh < config.DOCTR_MIN_H:
            continue
        if cv_utils.is_specular(gray, x, y, bw, bh):
            continue
        if ruler_bbox is not None:
            rx, ry, rw, rh = ruler_bbox
            cx, cy = x + bw / 2, y + bh / 2
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh and word.value.strip().replace(".", "").isdigit():
                continue

        in_zone = cv_utils.box_in_phi_zone(x, y, bw, bh, img_bgr.shape)
        kw_match = keyword_matcher.matches(word.value) if keyword_matcher else False

        if not in_zone and not kw_match:
            continue

        if kw_match:
            kw_hits += 1
            print(
                f"    [KW HIT] '{word.value.strip()}' conf={word.confidence:.2f} "
                f"zone={'YES' if in_zone else 'NO (centre hit)'} box=({x},{y},{bw},{bh})"
            )
        boxes.append((x, y, bw, bh))

    return boxes, kw_hits


def detect_white_labels(img_bgr: np.ndarray):
    H, W = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, config.LABEL_WHITE_THRESH, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 9))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    max_area = H * W * config.LABEL_MAX_AREA_F
    label_boxes, label_rois = [], []

    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        roi = gray[y : y + h, x : x + w]
        if np.mean(roi) < config.LABEL_WHITE_THRESH * 0.85:
            continue
        if w * h < config.LABEL_MIN_AREA or w * h > max_area:
            continue
        if w / (h + 1e-6) > config.LABEL_ASPECT_MAX:
            continue
        if cv_utils.contour_circularity(c) > config.LABEL_CIRCULARITY_MAX:
            continue
        if cv_utils.contour_solidity(c) < config.LABEL_SOLIDITY_MIN:
            continue
        if np.std(roi) < config.LABEL_INTERNAL_STD_MIN:
            if cv_utils.edge_density(roi) < config.LABEL_EDGE_DENSITY_MIN * 2:
                continue
        if cv_utils.edge_density(roi) < config.LABEL_EDGE_DENSITY_MIN:
            continue
        if not cv_utils.near_border(x, y, w, h, img_bgr.shape):
            continue

        label_boxes.append((x, y, w, h))
        label_rois.append((roi.copy(), x, y))

    return label_boxes, label_rois


def detect_acq_params(img_shape: tuple, img_bgr: np.ndarray = None):
    if not config.MASK_ACQ_PARAMS:
        return []
    H, W = img_shape[:2]
    x = 0
    y = int(H * config.ACQ_ROW_START_F)
    w = int(W * config.ACQ_COL_WIDTH_F)
    h = int(H * (config.ACQ_ROW_END_F - config.ACQ_ROW_START_F))

    if img_bgr is not None:
        strip = img_bgr[y : y + h, x : x + w]
        if strip.size == 0:
            return []
        gray_strip = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
        if (
            cv_utils.edge_density(gray_strip) < config.ACQ_EDGE_DENSITY_MIN
            or float(np.std(gray_strip)) < config.ACQ_STD_MIN
        ):
            return []
    return [(x, y, w, h)]


def auto_detect(model, img_path: str, keyword_matcher=None):
    # Handle DICOM image extraction
    if img_path.lower().endswith(".dcm"):
        img = dicom_scrubber.extract_dicom_bgr_image(img_path)
        if img is None:
            return [], None, 0

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            cv2.imwrite(tmp_path, img)
            d1, kw_hits = detect_ocr(model, tmp_path, img, keyword_matcher)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        merged = cv_utils.merge_boxes(d1)
        padded = [cv_utils.pad_box(x, y, w, h, img.shape) for x, y, w, h in merged]
        return padded, img, kw_hits

    # Fix phone photo rotation via EXIF normalization
    img = cv_utils.load_oriented_image(img_path)
    if img is None:
        return [], None, 0

    # 1. OCR across PHI zones & keywords
    d1, kw_hits = detect_ocr(model, img_path, img, keyword_matcher)
    
    # 2. White sticker detector (D2: outer envelope, D2b: inner crop OCR)
    label_boxes, label_rois = detect_white_labels(img)
    d2 = label_boxes
    d2b = []

    for roi_gray, ox, oy in label_rois:
        processed = cv_utils.preprocess_for_handwriting(roi_gray)
        word_boxes = run_doctr_on_crop(model, processed, ox, oy, img.shape)
        d2b.extend(word_boxes)

    # 3. Acquisition strip (if enabled)
    d3 = detect_acq_params(img.shape, img)
    
    # Combine OCR and metadata boxes
    standard_boxes = d1 + d2b + d3

    # Retain full sticker boxes and drop internal redundant word boxes
    merged = cv_utils.merge_sticker_and_word_boxes(d2, standard_boxes)
    padded = [cv_utils.pad_box(x, y, w, h, img.shape) for x, y, w, h in merged]
    return padded, img, kw_hits