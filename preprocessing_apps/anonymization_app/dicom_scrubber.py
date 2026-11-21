"""
dicom_scrubber.py – DICOM metadata scrubbing, MIDAS tag injection, and pixel data serialization.
"""

import copy
import os
import shutil
from pathlib import Path
import numpy as np
import cv2
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid
import config

PHI_TAGS_TO_REMOVE = [
    "PatientName", "PatientBirthDate", "PatientSex", "PatientAge",
    "PatientAddress", "OtherPatientIDs", "OtherPatientNames", "PatientComments",
    "PatientMotherBirthName", "EthnicGroup", "Occupation", "AdditionalPatientHistory",
    "InstitutionAddress", "InstitutionalDepartmentName", "ReferringPhysicianName",
    "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers",
    "PerformingPhysicianName", "PhysiciansOfRecord", "NameOfPhysiciansReadingStudy",
    "RequestingPhysician", "AccessionNumber", "StudyID", "DeviceSerialNumber",
    "ProtocolName",
]

GLOBAL_UID_MAP = {}

MIDAS_INLINE_SCHEMA = [
    ("PatientID", "Patient ID (0010,0020)", None),
    ("AccessionNumber", "Accession Number (0008,0050)", None),
    ("StudyDate", "Study Date YYYYMMDD (0008,0020)", None),
    ("Modality", "Modality (0008,0060)", None),
    ("StationName", "Station Name (0008,1010)", None),
    ("SeriesDescription", "Series Description (0008,103E)", None),
    ("InstitutionName", "Institution Name (0008,0080)", None),
    ("InstitutionCodeValue", "Institution Code Value (0008,0082)", ("InstitutionCodeSequence", "CodeValue", (0x0008, 0x0082))),
    ("InstitutionCodeMeaning", "Institution Code Meaning (0008,0082)", ("InstitutionCodeSequence", "CodeMeaning", (0x0008, 0x0082))),
    ("IssuerOfPatientID", "Issuer of Patient ID (0010,0021)", None),
    ("OperatorsName", "Operators' Name (0008,1070)", None),
    ("ConsultingPhysicianName", "Consulting Physician (0008,009C)", None),
    ("ROICreatorID", "ROI Creator ID (3006,004D)", ("ROICreatorSequence", "ObservationSubject", (0x3006, 0x004D))),
    ("ROIInterpreterID", "ROI Interpreter ID (3006,004E)", ("ROIInterpreterSequence", "ObservationSubject", (0x3006, 0x004E))),
    ("Manufacturer", "Manufacturer (0008,0070)", None),
    ("ConsentForDistributionFlag", "Consent Flag (0012,0085)", None),
]


def dicom_has_pixel_data(dcm_path: str) -> bool:
    """Checks for non-empty PixelData without loading a deferred pixel payload."""
    ds = pydicom.dcmread(dcm_path, force=True, defer_size=1)
    pixel_data = ds.get_item((0x7FE0, 0x0010), keep_deferred=True)
    if pixel_data is None:
        return False
    length = getattr(pixel_data, "length", None)
    if length is not None:
        return length > 0
    return pixel_data.value is not None and len(pixel_data.value) > 0


def read_current_dicom_schema(dcm_path: str) -> list:
    """Returns inline editor rows with current values, blank when absent or empty."""
    ds = pydicom.dcmread(dcm_path, stop_before_pixels=True, force=True)
    rows = []
    for key, label, sequence_info in MIDAS_INLINE_SCHEMA:
        current_value = ""
        if sequence_info is None:
            if key in ds and ds[key].value is not None:
                current_value = str(ds[key].value).strip()
        else:
            sequence_name, sub_attribute, _ = sequence_info
            if sequence_name in ds and ds[sequence_name].value:
                item = ds[sequence_name].value[0]
                value = getattr(item, sub_attribute, None)
                if value is not None:
                    current_value = str(value).strip()
        rows.append({"key": key, "label": label, "current": current_value})
    return rows


def apply_inline_dicom_edits(ds: pydicom.Dataset, new_values: dict) -> None:
    """Applies only non-empty inline edits, preserving unedited sequence fields."""
    sequence_schema = {
        key: sequence_info
        for key, _, sequence_info in MIDAS_INLINE_SCHEMA
        if sequence_info is not None
    }

    for key, raw_value in new_values.items():
        value = str(raw_value).strip() if raw_value is not None else ""
        if not value:
            continue

        sequence_info = sequence_schema.get(key)
        if sequence_info is None:
            setattr(ds, key, value)
            if key == "PatientID":
                ds.PatientName = value
            elif key == "StudyDate":
                for date_tag in (
                    "StudyDate",
                    "SeriesDate",
                    "AcquisitionDate",
                    "ContentDate",
                ):
                    if date_tag in ds or date_tag == "StudyDate":
                        setattr(ds, date_tag, value)
            continue

        sequence_name, sub_attribute, tag = sequence_info
        items = copy.deepcopy(list(ds[sequence_name].value)) if sequence_name in ds else []
        if not items:
            items.append(Dataset())
        item = items[0]
        if sequence_name == "InstitutionCodeSequence":
            item.CodingSchemeDesignator = getattr(item, "CodingSchemeDesignator", "MIDAS")
        elif sequence_name == "ROICreatorSequence":
            item.ObserverType = getattr(item, "ObserverType", "DEVICE")
        elif sequence_name == "ROIInterpreterSequence":
            item.ObserverType = getattr(item, "ObserverType", "PERSON")
        setattr(item, sub_attribute, value)

        if sequence_name in ds:
            ds[sequence_name].value = Sequence(items)
        else:
            ds.add_new(tag, "SQ", Sequence(items))


def get_consistent_uid(original_uid: str) -> str:
    if not original_uid:
        return generate_uid()
    if original_uid not in GLOBAL_UID_MAP:
        GLOBAL_UID_MAP[original_uid] = generate_uid()
    return GLOBAL_UID_MAP[original_uid]


def scrub_phi_tags(ds: pydicom.Dataset) -> None:
    ds.remove_private_tags()

    for tag_name in PHI_TAGS_TO_REMOVE:
        if tag_name in ds:
            ds[tag_name].value = ""

    patient_id = str(getattr(ds, "PatientID", "")).strip()
    if patient_id:
        ds.PatientName = patient_id

    if "StudyInstanceUID" in ds:
        ds.StudyInstanceUID = get_consistent_uid(ds.StudyInstanceUID)
    if "SeriesInstanceUID" in ds:
        ds.SeriesInstanceUID = get_consistent_uid(ds.SeriesInstanceUID)

    ds.SOPInstanceUID = generate_uid()
    if hasattr(ds, "file_meta") and hasattr(ds.file_meta, "MediaStorageSOPInstanceUID"):
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "MIDAS DICOM De-identification Protocol"


def apply_midas_tags(ds: pydicom.Dataset, tag_config: dict = None) -> None:
    if tag_config is None:
        tag_config = config.DEFAULT_MIDAS_TAGS

    preview_and_apply_midas_tags(ds, tag_config)


def _format_tag_value(ds: pydicom.Dataset, key: str) -> str:
    if key not in ds:
        return "<NOT PRESENT>"

    element = ds[key]
    if element.VR == "SQ":
        if not element.value:
            return "<EMPTY>"
        item = element.value[0]
        fields = [f"{name}={getattr(item, name)}" for name in item.dir()]
        return "{" + ", ".join(fields) + "}"

    value = str(element.value).strip()
    return value if value else "<EMPTY>"


def preview_and_apply_midas_tags(
    ds: pydicom.Dataset,
    tag_config: dict = None,
    file_label: str = "",
) -> list:
    """Prints a current-to-planned tag diff and applies only non-empty changes."""
    if tag_config is None:
        tag_config = config.DEFAULT_MIDAS_TAGS

    changes = []
    header = f"[DICOM Metadata Diff] {file_label}" if file_label else "[DICOM Metadata Diff]"
    print(f"\n{header}")
    print("-" * 72)

    scalar_fields = (
        "PatientID",
        "AccessionNumber",
        "StudyDate",
        "Modality",
        "StationName",
        "SeriesDescription",
        "InstitutionName",
        "IssuerOfPatientID",
        "OperatorsName",
        "ConsultingPhysicianName",
        "Manufacturer",
        "ConsentForDistributionFlag",
    )

    for key in scalar_fields:
        current_value = _format_tag_value(ds, key)
        new_value = tag_config.get(key)
        planned_value = str(new_value).strip() if new_value is not None else ""

        if planned_value and planned_value != current_value:
            setattr(ds, key, planned_value)
            if key == "PatientID":
                ds.PatientName = planned_value
            elif key == "StudyDate":
                for date_tag in (
                    "StudyDate",
                    "SeriesDate",
                    "AcquisitionDate",
                    "ContentDate",
                ):
                    if date_tag in ds or date_tag == "StudyDate":
                        setattr(ds, date_tag, planned_value)
            changes.append(
                {"tag": key, "old": current_value, "new": planned_value, "action": "UPDATED"}
            )
            action = "UPDATE"
        else:
            planned_value = current_value
            changes.append(
                {"tag": key, "old": current_value, "new": current_value, "action": "KEPT"}
            )
            action = "KEEP"

        shown_value = planned_value if planned_value else "<NO NEW ENTRY>"
        print(f"  [{action}] {key:<26}: {current_value} -> {shown_value}")

    sequence_specs = {
        "InstitutionCodeSequence": (0x0008, 0x0082),
        "ROICreatorSequence": (0x3006, 0x004D),
        "ROIInterpreterSequence": (0x3006, 0x004E),
    }
    for key, tag in sequence_specs.items():
        current_value = _format_tag_value(ds, key)
        new_values = tag_config.get(key)
        non_empty_values = (
            {name: str(value).strip() for name, value in new_values.items()
             if value is not None and str(value).strip()}
            if isinstance(new_values, dict)
            else {}
        )

        if non_empty_values:
            items = copy.deepcopy(list(ds[key].value)) if key in ds else []
            if not items:
                items.append(Dataset())
            item = items[0]
            changed = False
            for name, value in non_empty_values.items():
                if str(getattr(item, name, "")).strip() != value:
                    setattr(item, name, value)
                    changed = True

            if changed:
                if key in ds:
                    ds[key].value = Sequence(items)
                else:
                    ds.add_new(tag, "SQ", Sequence(items))
                planned_value = _format_tag_value(ds, key)
                changes.append(
                    {"tag": key, "old": current_value, "new": planned_value, "action": "UPDATED"}
                )
                action = "UPDATE"
            else:
                planned_value = current_value
                changes.append(
                    {"tag": key, "old": current_value, "new": current_value, "action": "KEPT"}
                )
                action = "KEEP"
        else:
            planned_value = current_value
            changes.append(
                {"tag": key, "old": current_value, "new": current_value, "action": "KEPT"}
            )
            action = "KEEP"

        print(f"  [{action}] {key:<26}: {current_value} -> {planned_value}")

    print("-" * 72)
    return changes


def extract_dicom_bgr_image(file_path: str):
    """
    Extracts the pixel array from a DICOM file and normalizes it to
    an 8-bit BGR OpenCV array. Handles missing PlanarConfiguration and
    metadata-only files.
    """
    try:
        ds = pydicom.dcmread(file_path, stop_before_pixels=False, force=True)
        if "PixelData" not in ds:
            return None

        if getattr(ds, "SamplesPerPixel", 1) > 1 and "PlanarConfiguration" not in ds:
            ds.PlanarConfiguration = 0

        pixel_array = ds.pixel_array
        
        if pixel_array.ndim == 2:
            norm = cv2.normalize(pixel_array, None, 0, 255, cv2.NORM_MINMAX)
            img_8bit = np.uint8(norm)
            return cv2.cvtColor(img_8bit, cv2.COLOR_GRAY2BGR)
        elif pixel_array.ndim == 3 and pixel_array.shape[-1] in (3, 4):
            return cv2.cvtColor(pixel_array[:, :, :3], cv2.COLOR_RGB2BGR)
        elif pixel_array.ndim == 3:  # First frame of a multi-frame volume
            norm = cv2.normalize(pixel_array[0], None, 0, 255, cv2.NORM_MINMAX)
            return cv2.cvtColor(np.uint8(norm), cv2.COLOR_GRAY2BGR)
    except Exception as e:
        print(f"  [DICOM WARN] Could not extract pixel preview: {e}")
    return None


def save_anonymized_dicom(
    src_path: str,
    target_out_path: str,
    boxes: list,
    tag_config: dict = None,
    inline_modifications: dict = None,
) -> str:
    """
    Copies source DICOM to target_out_path, scrubs PHI metadata, applies either
    configured MIDAS tags or explicit inline edits, and blacks out pixel boxes.
    """
    src = Path(src_path).resolve()
    dst = Path(target_out_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, dst)
    ds = pydicom.dcmread(str(dst), force=True)

    # 1. Scrub metadata & regenerate UIDs
    scrub_phi_tags(ds)

    # 2. Apply either explicit inline edits or the configured MIDAS tag set.
    if inline_modifications is None:
        preview_and_apply_midas_tags(ds, tag_config, file_label=src.name)
    else:
        apply_inline_dicom_edits(ds, inline_modifications)

    if boxes and "PixelData" in ds:
        try:
            if getattr(ds, "SamplesPerPixel", 1) > 1 and "PlanarConfiguration" not in ds:
                ds.PlanarConfiguration = 0

            pixel_array = ds.pixel_array.copy()
            for x, y, w, h in boxes:
                if pixel_array.ndim == 2:
                    pixel_array[y : y + h, x : x + w] = 0
                elif pixel_array.ndim == 3 and pixel_array.shape[-1] in (3, 4):
                    pixel_array[y : y + h, x : x + w, :] = 0
                elif pixel_array.ndim == 3:
                    pixel_array[:, y : y + h, x : x + w] = 0

            ds.PixelData = pixel_array.tobytes()
            ds.BurnedInAnnotation = "NO"
            ds.DerivationDescription = "Burned-in text redacted via OCR pipeline"
        except Exception as e:
            print(f"  [DICOM WARN] Could not apply pixel redaction: {e}")

    ds.save_as(str(dst), write_like_original=False)
    return str(dst)