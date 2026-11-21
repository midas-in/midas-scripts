"""
dicom_profile.py – Persistent memory and smart auto-incrementing for MIDAS DICOM tags.
"""

import copy
import json
from pathlib import Path
import re
import config

PROFILE_FILE = Path(__file__).resolve().parent / "midas_tag_memory.json"


def load_saved_midas_tags() -> dict:
    """Loads the last-used MIDAS tag values from disk, falling back to config defaults."""
    base = copy.deepcopy(config.DEFAULT_MIDAS_TAGS)
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Merge saved values while preserving nested sequence dict structure
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    base[k].update(v)
                else:
                    base[k] = v
        except Exception as e:
            print(f"  [DICOM PROFILE WARN] Could not read saved profile: {e}")
    return base


def save_midas_tags(tag_dict: dict) -> None:
    """Persists the user's current MIDAS tag configuration to disk for future runs."""
    try:
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(tag_dict, f, indent=4)
    except Exception as e:
        print(f"  [DICOM PROFILE WARN] Could not save profile: {e}")


def increment_patient_id(patient_id: str) -> str:
    """
    Finds the last numeric group in a PatientID and increments it while preserving
    zero-padding and suffixes.
    Examples:
      '01_001_P'       -> '01_002_P'
      'MIDAS_SUBJ_001' -> 'MIDAS_SUBJ_002'
      'PAT-099'        -> 'PAT-100'
    """
    matches = list(re.finditer(r"\d+", patient_id))
    if not matches:
        return f"{patient_id}_001"

    last_match = matches[-1]
    num_str = last_match.group(0)
    width = len(num_str)
    next_num = str(int(num_str) + 1).zfill(width)

    return patient_id[: last_match.start()] + next_num + patient_id[last_match.end() :]