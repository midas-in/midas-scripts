import os
import csv
import datetime
from pathlib import Path
import numpy as np
from PIL import Image
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UID, generate_uid, SecondaryCaptureImageStorage
from pydicom.sequence import Sequence
import tempfile

# ==========================================
# CONFIGURATION
# ==========================================
INPUT_FOLDER = r"/Users/triveous/Dev/MIDAS Tools/midas-scripts/oral-cancer/histopath-labeling/compressed_output"
OUTPUT_FOLDER = r"/Users/triveous/Dev/MIDAS Tools/midas-scripts/oral-cancer/histopath-labeling/dicom_output"

# ==========================================
# LOGGING
# ==========================================
timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"dicom_process_log_{timestamp_str}.txt"
report_csv_filename = f"dicom_process_report_{timestamp_str}.csv"

def log(message):
    print(message)
    with open(log_txt_filename, "a", encoding="utf-8") as f:
        f.write(message + "\n")

# ==========================================
# UPDATED METADATA LOGIC
# ==========================================
def extract_metadata_from_structure(folder_path):
    parts = Path(folder_path).parts
    patient_id = "Unknown"
    visit_date = None
    body_part = "UNKNOWN"
    modality = "XC" 

    # Find the VISIT folder as the anchor
    visit_index = -1
    for i, part in enumerate(parts):
        if part.startswith("VISIT_"):
            visit_index = i
            break
    
    if visit_index != -1:
        # 1. Patient ID is always one folder before VISIT
        if visit_index > 0:
            patient_id = parts[visit_index - 1]
        
        # 2. Visit Date is inside the VISIT_ folder name
        visit_date = parts[visit_index].replace("VISIT_", "")

        # 3. Based on your structure: VISIT -> MOUTH -> GM -> HISTOPATH -> TONG
        # TONG is visit_index + 4
        if len(parts) > visit_index + 4:
            body_part = parts[visit_index + 4]

        # 4. Modality (GM) is visit_index + 2
        if len(parts) > visit_index + 2:
            modality = parts[visit_index + 2]

    return patient_id, visit_date, body_part, modality

def calculate_meta_information_group_length(ds):
    temp_meta = ds.file_meta.copy()
    if 'FileMetaInformationGroupLength' in temp_meta:
        del temp_meta['FileMetaInformationGroupLength']
    meta_ds = FileDataset(None, {}, file_meta=temp_meta, preamble=b"\0" * 128)
    with tempfile.NamedTemporaryFile(delete=True) as temp_file:
        meta_ds.save_as(temp_file.name)
        return os.path.getsize(temp_file.name) - 132

def create_dicom_from_jpg(jpg_path, dcm_path, metadata):
    p_id, v_date_str, b_part, mod_str, series_uid, study_uid = metadata
    img = Image.open(jpg_path).convert('RGB')
    img_array = np.array(img)

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = '1.2.840.10008.1.2'
    file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.8.498'

    ds = FileDataset(dcm_path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
    ds.SOPInstanceUID = generate_uid()
    ds.PatientName = ds.PatientID = p_id
    ds.Modality = mod_str.upper()
    ds.BodyPartExamined = b_part.upper()
    ds.SeriesInstanceUID = series_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesDescription = "General Microscopy"

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

    # Date Handling
    today = datetime.datetime.now().strftime("%Y%m%d")
    if v_date_str:
        try:
            ds.StudyDate = ds.SeriesDate = datetime.datetime.strptime(v_date_str, "%d-%m-%Y").strftime("%Y%m%d")
        except:
            ds.StudyDate = ds.SeriesDate = today
    else:
        ds.StudyDate = ds.SeriesDate = today

    ds.PixelData = img_array.tobytes()
    ds.Rows, ds.Columns = img_array.shape[:2]
    ds.SamplesPerPixel = 3 
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0 
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.file_meta.FileMetaInformationGroupLength = calculate_meta_information_group_length(ds) + 12
    ds.save_as(dcm_path)

def process_folders_robust(source_root, dest_root):
    log(f"--- STARTING DICOM CONVERSION ---")
    stats = {'total': 0, 'converted': 0, 'errors': 0}

    csv_file = open(report_csv_filename, 'w', newline='', encoding='utf-8')
    writer = csv.DictWriter(csv_file, fieldnames=['PatientID', 'VisitDate', 'Filename', 'Status', 'Output Path'])
    writer.writeheader()

    for root, dirs, files in os.walk(source_root):
        if not files: continue
        p_id, v_date, b_part, modality = extract_metadata_from_structure(root)
        series_uid, study_uid = generate_uid(), generate_uid()

        rel_path = os.path.relpath(root, source_root)
        out_folder = os.path.join(dest_root, rel_path)
        os.makedirs(out_folder, exist_ok=True)

        for filename in files:
            if not filename.lower().endswith(('.jpg', '.jpeg')): continue
            
            in_path = os.path.join(root, filename)
            out_path = os.path.join(out_folder, os.path.splitext(filename)[0] + ".dcm")
            
            try:
                create_dicom_from_jpg(in_path, out_path, (p_id, v_date, b_part, modality, series_uid, study_uid))
                writer.writerow({'PatientID': p_id, 'VisitDate': v_date, 'Filename': filename, 'Status': 'Success', 'Output Path': out_path})
                stats['converted'] += 1
            except Exception as e:
                log(f"Error {filename}: {e}")
                stats['errors'] += 1
            
            stats['total'] += 1
            if stats['total'] % 50 == 0: print(f"Processed {stats['total']} files...")

    csv_file.close()
    log(f"Finished. Successfully converted {stats['converted']} files.")

if __name__ == "__main__":
    process_folders_robust(INPUT_FOLDER, OUTPUT_FOLDER)
