import os
import pandas as pd
import csv
import pydicom
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from pydicom.dataset import Dataset, FileDataset
from pathlib import Path
from datetime import datetime

# ========================
# CONFIGURATION
# ========================
EXCEL_PATH = r"/Users/triveous/Dev/MIDAS Tools/midas-scripts/oral-cancer/histopath-labeling/sheet.xlsx"
DICOM_ROOT = r"/Users/triveous/Dev/MIDAS Tools/midas-scripts/oral-cancer/histopath-labeling/dicom_output"
OUTPUT_SUFFIX = "_SR"

# ========================
# LOGGING
# ========================
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"sr_process_log_{timestamp_str}.txt"
report_csv_filename = f"sr_process_report_{timestamp_str}.csv"

def log(message):
    print(message)
    with open(log_txt_filename, "a", encoding="utf-8") as f:
        f.write(message + "\n")

# ========================
# CLEANING HELPER
# ========================
def clean_excel_value(val, default_text="Not Applicable"):
    """Handles NaN and empty strings from Excel/Pandas."""
    if pd.isna(val) or str(val).strip().lower() == 'nan' or not str(val).strip():
        return default_text
    return str(val).strip()

# ========================
# LOGIC
# ========================

def load_excel_db():
    log(f"--- Loading Excel: {EXCEL_PATH} ---")
    try:
        df = pd.read_excel(EXCEL_PATH)
        db = {}
        for _, row in df.iterrows():
            # Using your NEW Excel headers
            p_id = str(row['Case_ID']).strip()
            visit = str(row['Visit_ID']).strip()
            filename = str(row['Image_File']).strip()
            
            file_stem = os.path.splitext(filename)[0]
            key = (p_id, visit, file_stem)
            
            db[key] = {
                'label': clean_excel_value(row.get('Labels'), "N/A"),
                'grading': clean_excel_value(row.get('Severity_Grading'), "N/A"),
                'comment': clean_excel_value(row.get('Reviewed_Comment'), "Not Applicable")
            }
        log(f"✅ Loaded {len(db)} records.")
        return db
    except Exception as e:
        log(f"❌ Excel Error: {e}")
        exit(1)

def extract_context_from_path(folder_path):
    parts = Path(folder_path).parts
    visit_index = -1
    for i, part in enumerate(parts):
        if part.startswith("VISIT_"):
            visit_index = i
            break
    
    if visit_index != -1:
        patient_id = parts[visit_index - 1]
        visit_id = parts[visit_index]
        return patient_id, visit_id
    return None, None

def generate_sr(save_path, original_ds, data, source_filename):
    try:
        # Extract Meta
        study_uid = original_ds.StudyInstanceUID
        series_uid = original_ds.SeriesInstanceUID
        sop_class_uid = original_ds.SOPClassUID
        sop_instance_uid = original_ds.SOPInstanceUID
        patient_id = original_ds.PatientID if 'PatientID' in original_ds else "UNKNOWN"
        patient_name = original_ds.PatientName if 'PatientName' in original_ds else "Anonymous"
        study_description = original_ds.StudyDescription if 'StudyDescription' in original_ds else "Unlabeled Study"
        accession_number = original_ds.AccessionNumber if 'AccessionNumber' in original_ds else ""
    except AttributeError as e:
        raise ValueError(f"Missing DICOM UID: {e}")

    # Standard SR Header
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    # Meta
    ds = FileDataset(save_path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = "SR"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = patient_id
    ds.PatientName = patient_name
    ds.SeriesNumber = 999
    ds.InstanceNumber = 1
    ds.SeriesDescription = "Image label/diagnoses"

    ds.StationName = "AIIMS Delhi"
    ds.InstitutionName = "AIIMS Delhi"

    # Institution Code Sequence (as a sequence)
    inst_code = Dataset()
    inst_code.CodeValue = "AIIMS"
    inst_code.CodingSchemeDesignator = "99LOCAL"
    inst_code.CodeMeaning = "All India Institute of Medical Sciences"
    ds.InstitutionCodeSequence = Sequence([inst_code])

    ds.IssuerOfPatientID = "AIIMS Delhi"
    ds.ConsentForDistributionFlag = "YES"

    # --- ROI Creator Sequence ---
    roi_creator = Dataset()
    roi_creator.PersonName = "annotator1"
    roi_creator.InstitutionName = "AIIMS Delhi"
    ds.ROICreatorSequence = Sequence([roi_creator])

    # --- ROI Interpreter Sequence ---
    roi_interpreter = Dataset()
    roi_interpreter.PersonName = "reviewer1"
    roi_interpreter.InstitutionName = "AIIMS Delhi"
    ds.ROIInterpreterSequence = Sequence([roi_interpreter])
    
    dt = datetime.now()
    ds.ContentDate = ds.StudyDate = dt.strftime("%Y%m%d")
    ds.ContentTime = ds.StudyTime = dt.strftime("%H%M%S")

    # Content Tree
    root = Dataset()
    root.RelationshipType = "CONTAINS"
    root.ValueType = "CONTAINER"
    root.ContinuityOfContent = "SEPARATE"
    root.ConceptNameCodeSequence = [Dataset()]
    root.ConceptNameCodeSequence[0].CodeValue = '18748-4'
    root.ConceptNameCodeSequence[0].CodingSchemeDesignator = 'LN'
    root.ConceptNameCodeSequence[0].CodeMeaning = 'Diagnostic Imaging Report'


    # 1. Ref Image
    item_ref = Dataset()
    item_ref.RelationshipType = "CONTAINS"
    item_ref.ValueType = "TEXT"
    item_ref.ConceptNameCodeSequence = [Dataset()]
    item_ref.ConceptNameCodeSequence[0].CodeValue = '121139'
    item_ref.ConceptNameCodeSequence[0].CodingSchemeDesignator = 'DCM'
    item_ref.ConceptNameCodeSequence[0].CodeMeaning = 'Referenced Image'
    item_ref.TextValue = source_filename

    # 2. Label
    item_label = Dataset()
    item_label.RelationshipType = "CONTAINS"
    item_label.ValueType = "TEXT"
    item_label.ConceptNameCodeSequence = [Dataset()]
    item_label.ConceptNameCodeSequence[0].CodeValue = '121071'
    item_label.ConceptNameCodeSequence[0].CodingSchemeDesignator = 'DCM'
    item_label.ConceptNameCodeSequence[0].CodeMeaning = 'Findings'
    item_label.TextValue = f"Label: {data['label']}, Grading: {data['grading']}"

    # 3. Comment
    item_comment = Dataset()
    item_comment.RelationshipType = "CONTAINS"
    item_comment.ValueType = "TEXT"
    item_comment.ConceptNameCodeSequence = [Dataset()]
    item_comment.ConceptNameCodeSequence[0].CodeValue = '121106'
    item_comment.ConceptNameCodeSequence[0].CodingSchemeDesignator = 'DCM'
    item_comment.ConceptNameCodeSequence[0].CodeMeaning = 'Comment'
    item_comment.TextValue = (data['comment'] if pd.notna(data['comment']) and data['comment'] != "" else "Not Applicable")

    root.ContentSequence = [item_ref, item_label, item_comment]
    ds.ContentSequence = [root]
    # Evidence Linking
    evidence = Dataset()
    evidence.ReferencedSOPClassUID = sop_class_uid
    evidence.ReferencedSOPInstanceUID = sop_instance_uid
    ref_series = Dataset()
    ref_series.SeriesInstanceUID = series_uid
    ref_series.ReferencedSOPSequence = [evidence]
    ds.CurrentRequestedProcedureEvidenceSequence = [Dataset()]
    ds.CurrentRequestedProcedureEvidenceSequence[0].ReferencedSeriesSequence = [ref_series]

    ds.save_as(save_path, write_like_original=False)

def main():
    db = load_excel_db()
    stats = {'success': 0, 'skipped': 0}

    for root, dirs, files in os.walk(DICOM_ROOT):
        p_id, visit_id = extract_context_from_path(root)
        if not p_id: continue

        for filename in files:
            if not filename.lower().endswith('.dcm') or OUTPUT_SUFFIX in filename: continue

            file_stem = os.path.splitext(filename)[0]
            key = (p_id, visit_id, file_stem)

            if key in db:
                dicom_path = os.path.join(root, filename)
                sr_path = os.path.join(root, file_stem + OUTPUT_SUFFIX + ".dcm")
                try:
                    original_ds = pydicom.dcmread(dicom_path, stop_before_pixels=True)
                    generate_sr(sr_path, original_ds, db[key], filename)
                    stats['success'] += 1
                except Exception as e:
                    log(f"Error {filename}: {e}")
            else:
                stats['skipped'] += 1

    log(f"SR Generation Complete. Success: {stats['success']}, Skipped: {stats['skipped']}")

if __name__ == "__main__":
    main()
