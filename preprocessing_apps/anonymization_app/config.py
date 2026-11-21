"""
config.py – Global constants, detection thresholds, and geometry fractions.
"""

from dataclasses import dataclass
import os
import sys
from pathlib import Path


SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.ndpi', '.dcm')

# MIDAS DICOM tags are only applied when explicitly entered in the UI.
DEFAULT_MIDAS_TAGS = {
    "PatientID": "",
    "AccessionNumber": "",
    "StudyDate": "",
    "Modality": "",
    "StationName": "",
    "SeriesDescription": "",
    "InstitutionName": "",
    "InstitutionCodeSequence": {
        "CodeValue": "",
        "CodingSchemeDesignator": "",
        "CodeMeaning": "",
    },
    "IssuerOfPatientID": "",
    "OperatorsName": "",
    "ConsultingPhysicianName": "",
    "ROICreatorSequence": {
        "ObservationSubject": "",
        "ObserverType": "",
    },
    "ROIInterpreterSequence": {
        "ObservationSubject": "",
        "ObserverType": "",
    },
    "Manufacturer": "",
    "ConsentForDistributionFlag": "",
}

DEFAULT_INPUT_DIR = r"Paste/Your/Path/Here"
DEFAULT_OUTPUT_DIR = ""

# OCR
PADDING = 3
DOCTR_MIN_W = 12
DOCTR_MIN_H = 8
DOCTR_CONF_THRESHOLD = 0.30

# PHI Zones
PHI_TOP_FRAC = 0.16
PHI_BOT_FRAC = 0.09
PHI_SIDE_FRAC = 0.25

# White Paper Label Detector
LABEL_MIN_AREA = 2_500
LABEL_MAX_AREA_F = 0.25
LABEL_WHITE_THRESH = 195
LABEL_ASPECT_MAX = 6.0
LABEL_CIRCULARITY_MAX = 0.72
LABEL_SOLIDITY_MIN = 0.80
LABEL_EDGE_DENSITY_MIN = 0.02
LABEL_INTERNAL_STD_MIN = 5.0
LABEL_BORDER_MARGIN_F = 0.22

# Acquisition Parameter Strip
MASK_ACQ_PARAMS = False
ACQ_COL_WIDTH_F = 0.10
ACQ_ROW_START_F = 0.12
ACQ_ROW_END_F = 0.35
ACQ_EDGE_DENSITY_MIN = 0.06
ACQ_STD_MIN = 15.0

# Specular Reflection Guard
SPECULAR_MEAN_MIN = 230
SPECULAR_STD_MAX = 20
SPECULAR_MIN_AREA = 25 * 25

# NDPI De-identification Settings
NDPI_MAKE_BACKUP = True
NDPI_SCRUB_BINARY_SN = True
NDPI_DUMMY_DATETIME = b"0000:00:00 00:00:00\x00"

# UI & Display
NMS_IOU = 0.3
MAX_DISPLAY_W = 1280
MAX_DISPLAY_H = 800


@dataclass
class SessionPaths:
    """Holds dynamic session directory and log file paths."""
    input_dir: str
    output_dir: str
    session_output_dir: str
    logs_dir: str
    detection_csv: str
    anonymized_csv: str
    phi_keywords_file: str

    @classmethod
    def create(cls, input_dir: str, output_dir: str, timestamp: str) -> "SessionPaths":
        if not output_dir and getattr(sys, "frozen", False):
            base_out = os.path.join(str(Path.home()), "Desktop", "Anonymed_Outputs")
        elif output_dir:
            base_out = output_dir
        else:
            base_out = input_dir

        session_out = os.path.join(base_out, f"anonymized_{timestamp}")
        os.makedirs(session_out, exist_ok=True)

        # Logs stored directly with the session to keep runs synchronized
        detection_csv = os.path.join(session_out, f"detection_log_{timestamp}.csv")
        anonymized_csv = os.path.join(session_out, f"anonymized_log_{timestamp}.csv")

        return cls(
            input_dir=input_dir,
            output_dir=base_out,
            session_output_dir=session_out,
            logs_dir=session_out,
            detection_csv=detection_csv,
            anonymized_csv=anonymized_csv,
            phi_keywords_file=os.path.join(input_dir, "phi_keywords.txt"),
        )