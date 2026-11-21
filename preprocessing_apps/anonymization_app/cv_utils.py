"""
cv_utils.py – Image transformations, geometry checks, and optical rejection guards.
"""

import cv2
import numpy as np
import config
from PIL import Image, ImageOps

def clamp_box(x: int, y: int, w: int, h: int, shape: tuple) -> tuple:
    H, W = shape[:2]
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return (x, y, w, h)


def pad_box(x: int, y: int, w: int, h: int, shape: tuple) -> tuple:
    return clamp_box(
        x - config.PADDING,
        y - config.PADDING,
        w + 2 * config.PADDING,
        h + 2 * config.PADDING,
        shape,
    )


def box_in_phi_zone(x: int, y: int, w: int, h: int, img_shape: tuple) -> bool:
    H, W = img_shape[:2]
    cx, cy = x + w / 2, y + h / 2
    return (
        cy < H * config.PHI_TOP_FRAC
        or cy > H * (1 - config.PHI_BOT_FRAC)
        or (cy > H * 0.72 and cx < W * config.PHI_SIDE_FRAC)
        or (cy > H * 0.72 and cx > W * (1 - config.PHI_SIDE_FRAC))
    )


def merge_boxes(boxes: list) -> list:
    if not boxes:
        return []
    scores = [1.0] * len(boxes)
    idx = cv2.dnn.NMSBoxes(boxes, scores, 0.0, config.NMS_IOU)
    if len(idx) == 0:
        return []
    return [boxes[i] for i in idx.flatten()]


def boxes_to_str(boxes: list) -> str:
    return "|".join(f"{x},{y},{w},{h}" for x, y, w, h in boxes)

def load_oriented_image(path: str) -> np.ndarray:
    """Loads image and rotates it according to EXIF orientation metadata."""
    with Image.open(path) as pil_img:
        transposed = ImageOps.exif_transpose(pil_img)
        # Convert RGB/RGBA to BGR for OpenCV
        if transposed.mode in ("RGBA", "LA"):
            transposed = transposed.convert("RGB")
        bgr = cv2.cvtColor(np.array(transposed), cv2.COLOR_RGB2BGR)
    return bgr


def merge_sticker_and_word_boxes(sticker_boxes: list, word_boxes: list) -> list:
    """
    Separates containment merging from intersection suppression.
    If an outer sticker box contains inner word boxes, discard the inner boxes
    and retain the full protective sticker envelope.
    """
    kept_boxes = list(sticker_boxes)
    for wx, wy, ww, wh in word_boxes:
        w_cx = wx + ww / 2.0
        w_cy = wy + wh / 2.0
        # Check if the word center falls inside any confirmed sticker box
        inside_sticker = any(
            sx <= w_cx <= sx + sw and sy <= w_cy <= sy + sh
            for sx, sy, sw, sh in sticker_boxes
        )
        if not inside_sticker:
            kept_boxes.append((wx, wy, ww, wh))
    return merge_boxes(kept_boxes)


def is_specular(gray_img: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    if w * h > config.SPECULAR_MIN_AREA:
        return False
    pad = 6
    H_img, W_img = gray_img.shape[:2]
    sx = max(0, x - pad)
    sy = max(0, y - pad)
    ex = min(W_img, x + w + pad)
    ey = min(H_img, y + h + pad)
    roi = gray_img[sy:ey, sx:ex]
    if roi.size == 0:
        return False
    m = float(np.mean(roi))
    s = float(np.std(roi))
    return m > config.SPECULAR_MEAN_MIN and s < config.SPECULAR_STD_MAX


def detect_ruler_strip(img_bgr: np.ndarray):
    H, _ = img_bgr.shape[:2]
    search_y = int(H * 0.80)
    strip = img_bgr[search_y:, :]
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    col_mean = np.mean(np.abs(sobelx), axis=0)
    threshold = np.percentile(col_mean, 70) * 1.5
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


def contour_circularity(cnt) -> float:
    area = cv2.contourArea(cnt)
    peri = cv2.arcLength(cnt, True)
    if peri < 1:
        return 0.0
    return 4 * np.pi * area / (peri**2)


def contour_solidity(cnt) -> float:
    area = cv2.contourArea(cnt)
    hull_area = cv2.contourArea(cv2.convexHull(cnt))
    if hull_area < 1:
        return 0.0
    return area / hull_area


def near_border(x: int, y: int, w: int, h: int, img_shape: tuple) -> bool:
    H, W = img_shape[:2]
    mx = int(W * config.LABEL_BORDER_MARGIN_F)
    my = int(H * config.LABEL_BORDER_MARGIN_F)
    return x < mx or y < my or (x + w) > (W - mx) or (y + h) > (H - my)


def edge_density(gray_roi: np.ndarray) -> float:
    edges = cv2.Canny(gray_roi, 50, 150)
    return float(np.count_nonzero(edges)) / max(edges.size, 1)


def preprocess_for_handwriting(gray_roi: np.ndarray) -> np.ndarray:
    cv2.imwrite("panel1_original.png", gray_roi)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_roi)
    cv2.imwrite("panel2_clahe.png", enhanced)

    binary = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    cv2.imwrite("panel3_threshold.png", binary)

    if np.mean(binary) < 128:
        binary = cv2.bitwise_not(binary)
    cv2.imwrite("panel4_final.png", binary)
    return binary