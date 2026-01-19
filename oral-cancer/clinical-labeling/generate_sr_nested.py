import os
import pandas as pd
import csv
import pydicom
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from pydicom.dataset import Dataset, FileDataset
from datetime import datetime

# ========================
# CONFIGURATION
# ========================
EXCEL_PATH = r"excel sheet path"
DICOM_ROOT = r"dicom root path"
OUTPUT_SUFFIX = "_SR"

# ========================
# LOGGING SETUP
# ========================
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"sr_process_log_{timestamp_str}.txt"
report_csv_filename = f"sr_process_report_{timestamp_str}.csv"

def log(message, print_to_console=True):
    """Prints to console and appends to text file immediately."""
    if print_to_console:
        print(message)
    try:
        with open(log_txt_filename, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"CRITICAL ERROR: Cannot write to log file: {e}")

# ========================
# LOGIC
# ========================

def load_excel_db():
    log(f"--- Loading Excel Database: {EXCEL_PATH} ---")
    try:
        # Load Excel
        df = pd.read_excel(EXCEL_PATH)
        df['comment'] = df['comment'].fillna("-")
        
        db = {}
        for _, row in df.iterrows():
            # Robust string conversion to handle numbers treated as float/int
            p_id = str(row['case']).strip()
            visit = str(row['visit']).strip()
            filename = str(row['file']).strip()
            
            file_stem = os.path.splitext(filename)[0]
            key = (p_id, visit, file_stem)
            
            db[key] = {
                'label': str(row['label']),
                'comment': str(row['comment'])
            }
        log(f"✅ Loaded {len(db)} records from Excel.")
        return db
    except Exception as e:
        log(f"❌ FATAL: Error loading Excel: {e}")
        exit(1)

def extract_context_from_path(folder_path):
    parts = folder_path.split(os.sep)
    patient_id = None
    visit_id = None
    for part in parts:
        if part.endswith("_P") and part[0].isdigit():
            patient_id = part
        if part.startswith("VISIT_"):
            visit_id = part
    return patient_id, visit_id

def generate_sr(save_path, original_ds, label_text, comment_text, source_filename):
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
    item_label.TextValue = label_text

    # 3. Comment
    item_comment = Dataset()
    item_comment.RelationshipType = "CONTAINS"
    item_comment.ValueType = "TEXT"
    item_comment.ConceptNameCodeSequence = [Dataset()]
    item_comment.ConceptNameCodeSequence[0].CodeValue = '121106'
    item_comment.ConceptNameCodeSequence[0].CodingSchemeDesignator = 'DCM'
    item_comment.ConceptNameCodeSequence[0].CodeMeaning = 'Comment'
    item_comment.TextValue = comment_text

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
    return True

def main():
    log(f"--- STARTING ROBUST SR GENERATION ---")
    log(f"Source: {DICOM_ROOT}")
    
    db = load_excel_db()
    
    # Stats counters
    stats = {
        'total': 0,
        'success': 0,
        'skipped': 0,
        'error': 0
    }

    log(f"\n🔍 Scanning folders and writing report live...")
    
    # --- OPEN CSV FILE *BEFORE* LOOPING ---
    try:
        csv_file = open(report_csv_filename, 'w', newline='', encoding='utf-8')
        fieldnames = ['PatientID', 'VisitID', 'Filename', 'Status', 'Label', 'Comment', 'Details', 'Folder']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
    except Exception as e:
        log(f"❌ FATAL: Cannot create CSV report file: {e}")
        exit(1)

    # Process
    for root, dirs, files in os.walk(DICOM_ROOT):
        p_id, visit_id = extract_context_from_path(root)
        
        if not p_id or not visit_id:
            continue

        for filename in files:
            if not filename.lower().endswith('.dcm'):
                continue
            if OUTPUT_SUFFIX in filename:
                continue

            stats['total'] += 1
            
            # Prepare row structure
            row_data = {
                'PatientID': p_id,
                'VisitID': visit_id,
                'Filename': filename,
                'Folder': root,
                'Status': '',
                'Label': '',
                'Comment': '',
                'Details': ''
            }

            file_stem = os.path.splitext(filename)[0]
            key = (p_id, visit_id, file_stem)

            if key in db:
                data = db[key]
                row_data['Label'] = data['label']
                row_data['Comment'] = data['comment']
                
                dicom_path = os.path.join(root, filename)
                sr_path = os.path.join(root, file_stem + OUTPUT_SUFFIX + ".dcm")

                try:
                    original_ds = pydicom.dcmread(dicom_path, stop_before_pixels=True)
                    
                    generate_sr(
                        sr_path, 
                        original_ds, 
                        data['label'], 
                        data['comment'],
                        filename
                    )
                    
                    # Success logging
                    log(f"✅ Created: {filename}", print_to_console=True)
                    row_data['Status'] = 'Success'
                    row_data['Details'] = 'Generated'
                    stats['success'] += 1

                except Exception as e:
                    # Error logging
                    err_msg = str(e)
                    log(f"❌ Error {filename}: {err_msg}", print_to_console=True)
                    row_data['Status'] = 'Error'
                    row_data['Details'] = err_msg
                    stats['error'] += 1
            else:
                # Skipped (Not in Excel)
                # Don't print to console (too noisy for large data), just log to CSV
                row_data['Status'] = 'Skipped'
                row_data['Details'] = 'Not in Excel DB'
                stats['skipped'] += 1

            # --- WRITE ROW IMMEDIATELY ---
            writer.writerow(row_data)
            
            # Flush buffer every 10 files to ensure data is safe on disk
            if stats['total'] % 10 == 0:
                csv_file.flush()

    # Close CSV at the end
    csv_file.close()

    log(f"\n--- JOB COMPLETED ---")
    log(f"Total Scanned: {stats['total']}")
    log(f"Success:       {stats['success']}")
    log(f"Skipped:       {stats['skipped']}")
    log(f"Errors:        {stats['error']}")
    log(f"Detailed Report: {os.path.abspath(report_csv_filename)}")

if __name__ == "__main__":
    main()