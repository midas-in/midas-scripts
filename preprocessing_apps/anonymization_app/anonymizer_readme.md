# Anonymizer Pro — Medical Image PHI Redaction Tool

A two-phase Python pipeline for detecting and redacting **Protected Health Information (PHI)** from clinical/dental images. Built for oral-cavity datasets but applicable to any medical imaging workflow.

---

# Overview

```
Phase 1 — Auto-Detection (runs silently on all images)
    ↓
    • docTR OCR          → printed text in PHI corner/edge zones
    • White-label finder → paper stickers with handwritten IDs
    • Ruler/scale guard  → prevents false hits on measurement bars
    • Keyword matcher    → catches PHI anywhere via phi_keywords.txt
    ↓
Phase 2 — Human Review GUI (image by image)
    ↓
    • Review auto-detected boxes overlaid on original
    • Toggle, add, or remove boxes manually
    • Save redacted output with one click
```

---

# Features

| Feature                      | Details                                                                     |
| ---------------------------- | --------------------------------------------------------------------------- |
| docTR OCR                    | Detects printed patient text in image corners and edges                     |
| Handwriting detection        | CLAHE + adaptive threshold pre-processing before OCR on label crops         |
| Reflection / teeth rejection | Circularity, solidity, edge-density and std filters prevent false positives |
| Ruler guard                  | Sobel-X heuristic suppresses scale-bar number false hits                    |
| Keyword matching             | Plain text, EXACT: and REGEX: patterns via phi_keywords.txt                 |
| Image-aware acq strip        | Acquisition parameter masking only fires when text is actually present      |
| Human-in-the-loop GUI        | Full undo, manual drawing, batch toggle, skip support                       |
| CSV audit trail              | detection_log.csv and anonymized_log.csv written alongside images           |

---

# Installation

## 1. Clone or copy the script

```
git clone <your-repo-url>
cd anonymizer-pro
```

## 2. Create virtual environment (recommended)

```
python -m venv venv
```

### Windows

```
venv\Scripts\activate
```

### macOS / Linux

```
source venv/bin/activate
```

## 3. Install dependencies

```
pip install -r requirements.txt
```

This will:

* Install required packages
* Download pretrained docTR model (~150MB) on first run

---

## 4. Pre-download docTR model (optional but recommended)

```
python -c "from doctr.models import ocr_predictor; ocr_predictor(pretrained=True); print('Model ready.')"
```

Model cache:

Windows

```
C:\Users\<you>\.cache\doctr\
```

Linux/macOS

```
~/.cache/doctr/
```

---

# Setup

Edit path inside script:

```
INPUT_DIR = r"C:\Users\Admin\Desktop\YASH Script\APPS\Model_case"
```

Supported formats:

```
.jpg  .jpeg  .png  .tiff  .bmp
```

Files already named:

```
anonymized_*
```

are automatically skipped.

---

# Usage

```
python anonymizer_pro.py
```

Workflow:

1. Phase 1 scans all images silently
2. Phase 2 GUI opens if PHI detected
3. Review boxes
4. Click **SAVE & NEXT**
5. Output saved as:

```
anonymized_<original_name>
```

---

# PHI Keyword File

Create:

```
phi_keywords.txt
```

inside `INPUT_DIR`

### Example

```
# Plain text
PatientID
Case No
Reg No

# EXACT match
EXACT:ID
EXACT:DOB
EXACT:MRN

# REGEX patterns
REGEX:\b\d{2}[/-]\d{2}[/-]\d{4}\b
REGEX:AIIMS\d+
REGEX:(?i)reg[\.\s#]*no
```

Behaviour:

* Keyword matches bypass PHI-zone gate
* Works even in image centre
* Optional file (pipeline still runs without it)

---

# Configuration Reference

| Parameter              | Default | Description        |
| ---------------------- | ------- | ------------------ |
| INPUT_DIR              | user    | image folder       |
| DOCTR_CONF_THRESHOLD   | 0.30    | OCR confidence     |
| PHI_TOP_FRAC           | 0.16    | top PHI zone       |
| PHI_BOT_FRAC           | 0.09    | bottom PHI zone    |
| PHI_SIDE_FRAC          | 0.25    | side PHI zone      |
| LABEL_MIN_AREA         | 2500    | min label size     |
| LABEL_CIRCULARITY_MAX  | 0.72    | reject reflections |
| LABEL_SOLIDITY_MIN     | 0.80    | reject teeth arcs  |
| LABEL_EDGE_DENSITY_MIN | 0.02    | label edge content |
| LABEL_INTERNAL_STD_MIN | 5.0     | reject blank blobs |
| LABEL_BORDER_MARGIN_F  | 0.22    | edge margin        |
| MASK_ACQ_PARAMS        | False   | disable acq strip  |
| SPECULAR_MEAN_MIN      | 230     | reflection filter  |
| SPECULAR_STD_MAX       | 20      | reflection filter  |
| NMS_IOU                | 0.3     | box merging        |

---

# Output Files

All written inside `INPUT_DIR`

| File               | Description        |
| ------------------ | ------------------ |
| anonymized_<name>  | redacted image     |
| detection_log.csv  | auto detection log |
| anonymized_log.csv | final save log     |

---

# GUI Controls

| Action            | Result              |
| ----------------- | ------------------- |
| Left-click orange | toggle auto box     |
| Left-drag         | draw manual box     |
| Right-click red   | remove manual       |
| Ctrl + Z          | undo                |
| ← / →             | navigate            |
| Enter             | save & next         |
| SKIP              | copy original       |
| ALL AUTO ON       | enable all          |
| ALL AUTO OFF      | disable all         |
| CLEAR MANUAL      | remove manual boxes |

---

# Detection Pipeline

## D1 — docTR OCR

Filters:

* confidence ≥ 0.30
* minimum size
* specular rejection
* ruler guard
* PHI zone OR keyword match

---

## D2 — White Label Finder

Filters:

1. Brightness
2. Area
3. Aspect ratio
4. Circularity
5. Solidity
6. Internal std
7. Edge density
8. Border bias

---

## D2b — Handwriting OCR

Pipeline:

```
CLAHE
↓
Adaptive threshold
↓
docTR on crop
```

---

## D3 — Acquisition Strip (optional)

Disabled by default.

Only fires when:

* high edge density
* high contrast std

---

# Troubleshooting

| Problem              | Fix                     |
| -------------------- | ----------------------- |
| Teeth redacted       | lower circularity       |
| Reflections detected | raise SPECULAR_MEAN_MIN |
| Handwriting missed   | lower edge density      |
| Centre labels missed | add keywords            |
| Scale bar detected   | adjust NMS_IOU          |
| No images found      | check INPUT_DIR         |
| GUI not opening      | install tkinter         |
| docTR download fails | run manual download     |

Linux tkinter:

```
sudo apt install python3-tk
```

---

# License

For **research / internal use only**.

