# Anonymed — Medical Image De-Identification Suite

**Anonymed** is a local, human-in-the-loop medical image de-identification desktop application built for clinical research workflows (such as the MIDAS consortium). It strips Protected Health Information (PHI) from standard 2D clinical images, volumetric **DICOM** studies (MRI, CT, Ultrasound, Secondary Captures), and gigapixel **Whole-Slide Images (WSI)** like Hamamatsu `.ndpi` scans—without ever uploading sensitive patient data to external servers.

Instead of blindly trusting automated scripts, Anonymed follows a **three-phase pipeline**:
1. **Phase 1 — Automated PHI Detection:** Uses deep-learning OCR (`docTR`), heuristic spatial rules, and domain keyword matching to flag burned-in text, slide labels, and metadata headers.
2. **Phase 2 — Interactive Visual Review:** Opens an interactive Tkinter GUI where you can inspect, adjust, add, or remove redaction bounding boxes before anything is finalized.
3. **Phase 3 — Non-Destructive Persistence & Audit Logging:** Writes scrubbed copies into a timestamped session folder while keeping your original files untouched, generating full CSV audit trails (`detection_log_*.csv` and `anonymized_log_*.csv`).

---

## How Volumetric & Gigapixel Data Are Handled

Medical imaging formats are rarely just flat pictures—they store 3D volumes, multi-slice sequences, and multi-resolution pyramids. Anonymed handles these formats carefully so clinical utility is preserved while privacy leaks are closed:

### 1. Volumetric DICOM Studies (`.dcm`)
A DICOM study (such as a 3D brain MRI or chest CT) is a volumetric stack of dozens or hundreds of individual 2D slices linked together by shared relational identifiers.
* **Preserving 3D Volume Consistency (`GLOBAL_UID_MAP`):** If you naively delete or randomize `StudyInstanceUID` and `SeriesInstanceUID` on each slice independently, 3D DICOM viewers (like 3D Slicer, Horos, or PACS workstations) can no longer reconstruct the volume. Anonymed maps original Study and Series UIDs to consistent pseudo-UIDs across all slices in a scan, while assigning every individual slice a fresh `SOPInstanceUID`.
* **Metadata Scrubbing & MIDAS Standardization:** Strips all vendor-proprietary private tags (`remove_private_tags()`), wipes HIPAA Safe Harbor PHI fields (`PatientName`, `PatientBirthDate`, `DeviceSerialNumber`, clinician names, dates/times), and injects standardized consortium metadata (`Modality`, `StationName`, `IssuerOfPatientID`, `InstitutionCodeSequence`, `ROICreatorSequence`, `ConsentForDistributionFlag`).
* **Pixel-Level Burned-In Redaction:** Modalities like Ultrasound (`US`) and Secondary Capture (`SC`) often burn patient names and MRNs directly into the image pixel array. Anonymed normalizes the raw pixel buffer (handling 12-bit/16-bit grayscale and RGB), runs OCR over the slice to locate exact text coordinates, and blacks out those regions directly in `ds.PixelData` before saving.

### 2. Whole-Slide Images / Digital Pathology (`.ndpi`)
Whole-slide images are massive, multi-gigabyte **pyramidal volumes** containing tissue scans at multiple magnification levels (e.g., 40x down to 0.08x) stored inside a TIFF-based container.
* **Zero-Recompression Macro IFD Unlinking:** Whole-slide scanners take a low-magnification optical camera photo of the entire glass slide—called the **`macro` image**—which captures the paper label, handwritten patient name, surgical accession number, and barcode. Re-encoding an 80,000 × 80,000 pixel pyramid to remove that label would take huge amounts of RAM and degrade image quality. Instead, Anonymed parses the TIFF Image File Directory (IFD) byte pointers directly on a copy of the file and **unlinks the macro IFD pointer** from the directory chain. Once unlinked, pathology viewers (QuPath, OpenSlide, Aperio ImageScope) cannot access the slide label, while the gigapixel tissue pyramid remains 100% lossless.
* **Binary Header & Serial Number Scrubbing:** Overwrites TIFF timestamp tags (`DateTime`, Tag 306) and zeroes out scanner hardware serial numbers (`NDP.S/N=`) directly in the binary metadata stream so the slide cannot be traced back to a specific scanner log.

---

## Project Architecture & Module Breakdown

Here is what each file in the repository does:

### Core Entrypoint & Configuration
* **`main.py`** — The main orchestrator. It initializes the `StartupDialog`, loads the `docTR` OCR model and `KeywordMatcher`, runs **Phase 1** batch scanning across 2D images, DICOM files, and WSIs, launches the **Phase 2** interactive `ReviewGUI`, and triggers **Phase 3** saving and CSV logging.
* **`config.py`** — Central configuration and path management (`SessionPaths`). Defines display thresholds, OCR confidence cutoffs, ROI padding margins, and output directory routing. When running as a packaged desktop app (`.app` or `.exe`), leaving the output path blank automatically routes results to `~/Desktop/Anonymed_Outputs/anonymized_<timestamp>/` so outputs are never hidden inside the app bundle.

### User Interface
* **`gui.py`** — Contains the Tkinter graphical interfaces:
  * `StartupDialog`: Lets users drag-and-drop or browse for an input folder, choose an output destination, or click **Load model_dataset** to test with the built-in sample dataset.
  * `ReviewGUI`: The interactive human-in-the-loop verification canvas where users review detected redaction boxes, draw new manual boxes, delete false positives, and inspect DICOM/WSI summaries before clicking **Save & Next**.

### Detection & Computer Vision
* **`detectors.py`** — The Phase 1 detection engine. Combines deep-learning text detection (`docTR`) with spatial heuristics (flagging top-banner text overlays and high-contrast label regions) and cross-checks recognized strings against `KeywordMatcher`.
* **`cv_utils.py`** — OpenCV image preprocessing and redaction helpers. Handles image normalization, CLAHE contrast enhancement, bounding-box coordinate scaling between high-res source images and GUI display canvases, and solid black-box pixel masking.
* **`keywords.py`** — Implements `KeywordMatcher`, which checks OCR-extracted text against medical PHI patterns (dates, MRNs, patient/doctor prefixes, hospital terms, and custom `phi_keywords.txt` lists).

### Modality-Specific Scrubbers & Persistence
* **`dicom_scrubber.py`** — Handles volumetric `.dcm` files. Performs HIPAA Safe Harbor metadata wiping, private tag removal, consistent Study/Series UID remapping, MIDAS tag injection, and pixel-level OCR redaction on DICOM pixel arrays.
* **`dicom_profile.py`** — Stores the `MIDAS_TAG_CONFIG` schema and helper builders for structured DICOM sequences (`InstitutionCodeSequence`, `ROICreatorSequence`, `ROIInterpreterSequence`) as well as persistent tag memory (`midas_tag_memory.json`).
* **`wsi_scrubber.py`** — Handles `.ndpi` whole-slide images using `OpenSlide`, `tifffile`, and binary stream pointer manipulation (`struct`). Copies the slide safely, unlinks the `macro` label IFD, scrubs binary serial numbers and timestamps, and extracts sanitized slide telemetry.
* **`storage.py`** — Manages Phase 3 persistence. Copies/writes anonymized 2D images, DICOM volumes, and WSIs into the session output directory (preserving nested folder structures) and writes the synchronized `detection_log_*.csv` and `anonymized_log_*.csv` audit reports.

### Packaging & Sample Assets
* **`Anonymed.spec`** — PyInstaller build specification configured for macOS (`.app`) and Windows (`.exe`), bundling `docTR`, `pydicom`, `openslide` / `openslide_bin`, `tkinterdnd2`, and `model_dataset`.
* **`rthook_omp.py`** — PyInstaller runtime hook that sets `KMP_DUPLICATE_LIB_OK=TRUE` before importing PyTorch or SciPy, preventing OpenMP library initialization crashes on macOS.
* **`model_dataset/`** — Built-in sample dataset containing test images so new users can verify the full pipeline right out of the box.
* **`anonymous.ico`** — Application icon bundled into the desktop executable.

---

## Quick Start

### Running from Source
1. Activate your Python 3.11 environment containing `python-doctr`, `pydicom`, `openslide-python`, `tifffile`, `opencv-python`, `numpy`, and `tkinterdnd2`.
2. Run the application:
   ```bash
   python main.py
   ```
3. In the startup window, click **Load model_dataset** (or select your own folder containing `.dcm`, `.ndpi`, `.png`, or `.jpg` files) and click **Start**.

### Running the Packaged macOS App (`Anonymed.app`)
1. Unzip `Anonymed_macOS_App.zip` and double-click **`Anonymed.app`** (on first launch, right-click → **Open** if macOS Gatekeeper prompts).
2. All anonymized files and CSV audit logs will be saved to `~/Desktop/Anonymed_Outputs/anonymized_<YYYYMMDD_HHMMSS>/` unless you choose a custom output folder.