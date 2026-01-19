import os
import csv
import datetime
from pathlib import Path
import numpy as np
from PIL import Image
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UID, generate_uid, SecondaryCaptureImageStorage
import tempfile
import subprocess

# ==========================================
# CONFIGURATION
# ==========================================
INPUT_FOLDER = r"input_folder_path"
OUTPUT_FOLDER = r"output_folder_path"

# Set this to False if processing >10,000 images to speed up significantly
VALIDATE_WITH_DCM2XML = True 

# ==========================================
# LOGGING SETUP
# ==========================================
timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"dicom_process_log_{timestamp_str}.txt"
report_csv_filename = f"dicom_process_report_{timestamp_str}.csv"

def log(message, print_to_console=True):
    """Prints to console and appends to text file immediately."""
    if print_to_console:
        print(message)
    try:
        with open(log_txt_filename, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"CRITICAL ERROR: Cannot write to log file: {e}")

# ==========================================
# METADATA EXTRACTION LOGIC
# ==========================================
def extract_metadata_from_structure(folder_path):
    parts = Path(folder_path).parts
    patient_id = "Unknown"
    visit_date = None
    body_part = ""
    modality = "XC" 

    visit_index = -1
    for i, part in enumerate(parts):
        if part.startswith("VISIT_"):
            visit_index = i
            break
    
    if visit_index != -1:
        if visit_index > 0:
            patient_id = parts[visit_index - 1]
        
        visit_folder_name = parts[visit_index]
        visit_date = visit_folder_name.replace("VISIT_", "")

        if len(parts) > visit_index + 1:
            body_part = parts[visit_index + 1]

        if len(parts) > visit_index + 2:
            modality = parts[visit_index + 2]

    return patient_id, visit_date, body_part, modality

# ==========================================
# DICOM UTILS
# ==========================================
def calculate_meta_information_group_length(ds):
    temp_meta = ds.file_meta.copy()
    if 'FileMetaInformationGroupLength' in temp_meta:
        del temp_meta['FileMetaInformationGroupLength']
    meta_ds = FileDataset(None, {}, file_meta=temp_meta, preamble=b"\0" * 128)
    with tempfile.NamedTemporaryFile(delete=True) as temp_file:
        meta_ds.save_as(temp_file.name)
        meta_length = os.path.getsize(temp_file.name) - 132 
    return meta_length

def validate_dicom_file(dicom_file_path):
    if not VALIDATE_WITH_DCM2XML:
        return
    try:
        result = subprocess.run(
            ['dcm2xml', dicom_file_path],
            capture_output=True,
            text=False
        )
        if result.returncode != 0:
            error_output = result.stderr.decode('utf-8', errors='ignore')
            log(f"WARNING: Validation failed for {os.path.basename(dicom_file_path)}: {error_output}")
    except Exception as e:
        log(f"WARNING: Validation tool error: {e}")

# ==========================================
# DICOM CREATION
# ==========================================
def create_dicom_from_jpg(jpg_path, dcm_path, metadata):
    p_id, v_date_str, b_part, mod_str, series_uid, study_uid = metadata

    img = Image.open(jpg_path)
    # Ensure RGB
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img_array = np.array(img)

    # -- File Meta --
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = '1.2.840.10008.1.2'
    file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.8.498'
    file_meta.ImplementationVersionName = 'MIDAS_1.0'

    # -- Dataset --
    ds = FileDataset(dcm_path, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # -- IDs & UIDs --
    ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'
    ds.SOPInstanceUID = generate_uid()
    ds.PatientName = p_id
    ds.PatientID = p_id
    ds.StudyID = 'add_study_id'
    ds.ClinicalTrialProtocolID = 'add_version_id'
    ds.AccessionNumber = f"{p_id}-clinical"
    ds.StudyDescription = "Clinical Image"
    ds.SeriesNumber = 1
    ds.SeriesDescription = "External-camera Photography"
    ds.Modality = mod_str.upper()
    ds.BodyPartExamined = b_part.upper()
    ds.SeriesInstanceUID = series_uid
    ds.StudyInstanceUID = study_uid

    # -- Dates --
    dt = datetime.datetime.now()
    ds.ContentDate = dt.strftime('%Y%m%d')
    ds.ContentTime = dt.strftime('%H%M%S')
   
    if v_date_str:
        try:
            dt_obj = datetime.datetime.strptime(v_date_str, "%d-%m-%Y")
            formatted_date = dt_obj.strftime("%Y%m%d")
            ds.StudyDate = formatted_date
            ds.SeriesDate = formatted_date
        except ValueError:
            today = datetime.datetime.now().strftime("%Y%m%d")
            ds.StudyDate = today
            ds.SeriesDate = today
    else:
        # Fallback if no date found
        today = datetime.datetime.now().strftime("%Y%m%d")
        ds.StudyDate = today
        ds.SeriesDate = today

    # -- Pixel Data --
    ds.PixelData = img_array.tobytes()
    ds.Rows, ds.Columns = img_array.shape[:2]
    ds.SamplesPerPixel = 3 
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0 # <--- CRITICAL FOR RGB COMPATIBILITY
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0

    # Meta Length Calc
    ds.file_meta.FileMetaInformationGroupLength = calculate_meta_information_group_length(ds) + 12
    
    # Save
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(dcm_path)
    
    validate_dicom_file(dcm_path)

# ==========================================
# MAIN EXECUTION
# ==========================================
def process_folders_robust(source_root, dest_root):
    
    valid_extensions = ('.jpg', '.jpeg')
    
    log(f"--- STARTING ROBUST DICOM CONVERSION ---")
    log(f"Time: {datetime.datetime.now()}")
    log(f"Source: {source_root}")
    
    # Stats
    stats = {'total': 0, 'converted': 0, 'skipped': 0, 'errors': 0}

    log(f"\n🔍 Scanning folders and streaming report to CSV...")

    # --- OPEN CSV FILE BEFORE LOOP ---
    try:
        csv_file = open(report_csv_filename, 'w', newline='', encoding='utf-8')
        # We record specific file details now, not just folder summaries
        fieldnames = ['PatientID', 'VisitDate', 'Filename', 'Status', 'Details', 'Output Path']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
    except Exception as e:
        log(f"FATAL: Cannot open CSV report for writing: {e}")
        exit(1)

    for root, dirs, files in os.walk(source_root):
        if not files:
            continue

        # Extract metadata for this folder
        p_id, v_date, b_part, modality = extract_metadata_from_structure(root)
        
        # Generate UIDs for this folder context
        series_uid = pydicom.uid.generate_uid()
        study_uid = pydicom.uid.generate_uid()

        # Create output directory
        rel_path = os.path.relpath(root, source_root)
        out_folder = os.path.join(dest_root, rel_path)
        if not os.path.exists(out_folder):
            os.makedirs(out_folder)

        for filename in files:
            in_path = os.path.join(root, filename)
            stats['total'] += 1
            
            # Prepare CSV Row
            row_data = {
                'PatientID': p_id,
                'VisitDate': v_date,
                'Filename': filename,
                'Status': '',
                'Details': '',
                'Output Path': ''
            }

            if not filename.lower().endswith(valid_extensions):
                row_data['Status'] = 'Skipped'
                row_data['Details'] = 'Not a JPG'
                stats['skipped'] += 1
                writer.writerow(row_data)
                continue

            # Output filename
            out_name = os.path.splitext(filename)[0] + ".dcm"
            out_path = os.path.join(out_folder, out_name)
            row_data['Output Path'] = out_path

            try:
                # Pack metadata
                meta = (p_id, v_date, b_part, modality, series_uid, study_uid)

                # Convert
                create_dicom_from_jpg(in_path, out_path, meta)
                
                # Success Log
                row_data['Status'] = 'Success'
                row_data['Details'] = 'Converted & Validated'
                stats['converted'] += 1
                
                # Console feedback every 10 files to keep it clean
                if stats['converted'] % 10 == 0:
                    print(f"Progress: {stats['converted']} files converted...")
            
            except Exception as e:
                # Error Log
                err_msg = str(e)
                log(f"❌ Error converting {filename}: {err_msg}")
                row_data['Status'] = 'Error'
                row_data['Details'] = err_msg
                stats['errors'] += 1

            # --- WRITE TO CSV IMMEDIATELY ---
            writer.writerow(row_data)
            
            # Flush buffer occasionally to ensure data is on disk
            if stats['total'] % 10 == 0:
                csv_file.flush()

    csv_file.close()

    log(f"\n--- COMPLETED ---")
    log(f"Total Files Scanned: {stats['total']}")
    log(f"Successfully Converted: {stats['converted']}")
    log(f"Skipped: {stats['skipped']}")
    log(f"Errors: {stats['errors']}")
    log(f"Full CSV Report: {os.path.abspath(report_csv_filename)}")

if __name__ == "__main__":
    process_folders_robust(INPUT_FOLDER, OUTPUT_FOLDER)