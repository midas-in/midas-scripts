import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
import shutil
import pydicom
from datetime import datetime
from pydicom.dataset import Dataset as DicomSubDataset
from pydicom.dataset import Dataset
import requests
import warnings
from logger_util import get_logger
from pydicom.sequence import Sequence

logger = get_logger()

warnings.filterwarnings("ignore", message="The value length .* exceeds the maximum length of 16 allowed for VR SH.")


# Define paths
input_base_path = "input path"
output_base_path = "output path"

# Scripts
jpeg_to_dicom_script = "jpeg to dicom script path"
microscope_jpeg_to_dicom_script = "microscope jpeg to dicom script path"

# Expand the ValueSet from HL7 v2-0550
url = "https://tx.fhir.org/r4/ValueSet/$expand"
params = {
    "url": "http://terminology.hl7.org/ValueSet/v2-0550",
    "_format": "application/json"
}

response = requests.get(url, params=params)
data = response.json()

# Extract code and display mapping
hl7_0550_map = {}
for concept in data.get("expansion", {}).get("contains", []):
    code = concept["code"]
    display = concept["display"]
    hl7_0550_map[code] = display

# Show a sample of the mapping
dict(list(hl7_0550_map.items())[:10])


def update_dicom_metadata(dicom_file, patient_id, patient_name, accession_number, visit_date, body_part, modality_folder):
    parts = accession_number.split("-")
    category = parts[-3].lower() if len(parts) > 3 else parts[-2].lower() if len(parts) > 2 else parts[-1].lower()
    suffix = parts[-1]
    subregion_code = parts[-2].upper() if len(parts) > 2 else ""

    # Determine prefix based on modality
    if modality_folder == "SM":
        description_map = {
            "cytology": f"Cytology WSI Images-{suffix}",
            "histopath": f"Histopath WSI Images-{suffix}",
            "clinical": "Clinical Image",
            "gross": "Gross",
            "radiograph": "Radiography"
        }
    elif modality_folder == "GM":
        description_map = {
            "cytology": f"Cytology Images-{subregion_code}-{suffix}",
            "histopath": f"Histopath Images-{subregion_code}-{suffix}",
            "clinical": "Clinical Image",
            "gross": "Gross",
            "radiograph": "Radiography"
        }
    else:
        description_map = {
            "cytology": f"Cytology Images-{subregion_code}-{suffix}",
            "histopath": f"Histopath Images-{subregion_code}-{suffix}",
            "clinical": "Clinical Image",
            "gross": "Gross",
            "radiograph": "Radiography"
        }

    description = description_map.get(category, "Unknown")


    if os.path.isfile(dicom_file):
        ds = pydicom.dcmread(dicom_file)
        ds.PatientID = patient_id
        ds.PatientName = patient_name
        ds.AccessionNumber = accession_number
        ds.StudyDescription = description
        visit_date_obj = datetime.strptime(visit_date, "%d-%m-%Y")
        ds.StudyDate = visit_date_obj.strftime("%Y%m%d")
        ds.BodyPartExamined = body_part
        ds.StudyID = 'dc75099e-b3ed-434e-bc07-5b27e95aa27a'
        ds.ClinicalTrialProtocolID = 'd01f56a5-5358-4523-979a-cef8d8a7f67a'
        # New fields
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

        # 🔽 Add AnatomicRegionSequence if subregion code is known
        if subregion_code and subregion_code in hl7_0550_map:
            display = hl7_0550_map[subregion_code]
            region_ds = DicomSubDataset()
            region_ds.CodeValue = subregion_code
            region_ds.CodingSchemeDesignator = "HL7"  # or "SCT" if SNOMED; adjust accordingly
            region_ds.CodeMeaning = display
            ds.AnatomicRegionSequence = [region_ds]

        ds.save_as(dicom_file)


def convert_jpeg_to_dicom(input_folder, output_folder):
    try:
        result = subprocess.run(['python3', jpeg_to_dicom_script, input_folder, output_folder], capture_output=True, text=True)
        logger.info(f"Standard Output: {result.stdout}")
        logger.info(f"Standard Error: {result.stderr}")
        if result.returncode != 0:
            logger.error(f"Error: Command failed with exit code {result.returncode} for input folder {input_folder}")
        else:
            logger.info(f"JPEG→DICOM conversion completed: {input_folder} -> {output_folder}")
    except Exception as e:
        logger.exception(f"Exception during JPEG→DICOM conversion for folder {input_folder}: {e}")

def convert_microscope_jpeg_to_dicom(input_folder, output_folder):
    try:
        result = subprocess.run(['python3', microscope_jpeg_to_dicom_script, input_folder, output_folder], capture_output=True, text=True)
        logger.info(f"Standard Output: {result.stdout}")
        logger.info(f"Standard Error: {result.stderr}")
        if result.returncode != 0:
            logger.error(f"Error: Command failed with exit code {result.returncode} for folder {input_folder}")
        else:
            logger.info(f"Microscope JPEG→DICOM conversion completed: {input_folder} -> {output_folder}")
    except Exception as e:
        logger.exception(f"Exception during microscope JPEG→DICOM conversion for folder {input_folder}: {e}")

def convert_ndpi_to_dicom(input_folder, output_folder):
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(".ndpi"):
            input_file = os.path.join(input_folder, filename)
            output_file = os.path.join(output_folder, os.path.splitext(filename)[0])
            os.makedirs(output_file, exist_ok=True)
            try:
                subprocess.run(['wsidicomizer', '--input', input_file, '--output', output_file], check=True)
                logger.info(f"NDPI→DICOM conversion completed for {input_file}")
            except Exception as e:
                logger.exception(f"NDPI→DICOM conversion failed for {input_file}: {e}")


def add_metadata_to_dicom_files(folder_path, patient_id, patient_name, accession_number, visit_date, body_part, modality_folder):
    counter = 1
    for root, _, files in os.walk(folder_path):
        for file in sorted(files):
            if file.lower().endswith(".dcm"):
                dicom_file_path = os.path.join(root, file)
                try:
                    update_dicom_metadata(dicom_file_path, patient_id, patient_name, accession_number, visit_date, body_part, modality_folder)
                    new_filename = f"{counter}.dcm"
                    os.rename(dicom_file_path, os.path.join(root, new_filename))
                    counter += 1
                except Exception as e:
                    logger.exception(f"Failed updating metadata for DICOM file {dicom_file_path}: {e}")

def process_submodality(submodality_path, output_submodality_path, case_folder, visit_date, body_part_folder, submodality_folder, modality_folder):
    try:
        os.makedirs(output_submodality_path, exist_ok=True)
        submodality_upper = submodality_folder.upper()
        logger.info(f"----- Processing sub modality folder: {submodality_upper} -----")

        if submodality_upper in {"CLINICAL", "GROSS", "RADIOGRAPH"}:
            logger.info(f"Process starting for sub modality folder: {submodality_upper} -----")
            convert_jpeg_to_dicom(submodality_path, output_submodality_path)
            parts = os.path.normpath(submodality_path).split(os.sep)
            imgType = parts[-1]
            accessionNumber = case_folder + "-" + imgType.lower()
            add_metadata_to_dicom_files(output_submodality_path, case_folder, case_folder, accessionNumber, visit_date, body_part_folder, modality_folder)
            logger.info(f"Process completed for sub modality folder: {submodality_upper} -----")

        elif modality_folder in {"GM"} and submodality_upper in {"HISTOPATH", "CYTOLOGY"}:
            logger.info(f"Process starting for sub modality folder: {submodality_upper} -----")
            for root, _, files in os.walk(submodality_path):
                image_files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))]
                if not image_files:
                    logger.warning(f"No matching input files in {root} for modality {modality_folder}/{submodality_folder}")
                    continue
                relative_path = os.path.relpath(root, submodality_path)
                out_path = os.path.join(output_submodality_path, relative_path)
                os.makedirs(out_path, exist_ok=True)
                convert_microscope_jpeg_to_dicom(root, out_path)
                parts = os.path.normpath(out_path).split(os.sep)
                magnificationLevel = parts[-1]
                imgType = parts[-3]
                imgTypeBodyPart = parts[-2]
                accessionNumber = case_folder + "-" + imgType.lower() + "-" + imgTypeBodyPart.lower() + "-" + magnificationLevel
                add_metadata_to_dicom_files(out_path, case_folder, case_folder, accessionNumber, visit_date, body_part_folder, modality_folder)
            logger.info(f"Process completed for sub modality folder: {submodality_upper} -----")

        elif modality_folder in {"SM"} and submodality_upper in {"HISTOPATH", "CYTOLOGY"}:
            logger.info(f"Process starting for sub modality folder: {submodality_upper} -----")
            for root, _, files in os.walk(submodality_path):
                image_files = [f for f in files if f.lower().endswith(".ndpi")]
                if not image_files:
                    logger.warning(f"No matching input files in {root} for modality {modality_folder}/{submodality_folder}")
                    continue
                relative_path = os.path.relpath(root, submodality_path)
                out_path = os.path.join(output_submodality_path, relative_path)
                os.makedirs(out_path, exist_ok=True)
                convert_ndpi_to_dicom(root, out_path)
                parts = os.path.normpath(out_path).split(os.sep)
                subregionBodyPart = parts[-1]
                imgType = parts[-3]
                imgTypeBodyPart = parts[-2]
                accessionNumber = case_folder + "-" + imgTypeBodyPart.lower() + "-" + subregionBodyPart
                add_metadata_to_dicom_files(out_path, case_folder, case_folder, accessionNumber, visit_date, body_part_folder, modality_folder)
            logger.info(f"Process completed for sub modality folder: {submodality_upper} -----")
    except Exception as e:
        logger.exception(f"Failed processing submodality_path={submodality_path}: {e}")

def gather_tasks(input_base, output_base):
    tasks = []
    for case_folder in os.listdir(input_base):
        case_folder_path = os.path.join(input_base, case_folder)
        if not os.path.isdir(case_folder_path):
            continue
        output_patient_folder = os.path.join(output_base, case_folder)
        for visit_folder in os.listdir(case_folder_path):
            visit_path = os.path.join(case_folder_path, visit_folder)
            if not os.path.isdir(visit_path):
                continue
            visit_date = visit_folder.replace("VISIT_", "")
            for body_part_folder in os.listdir(visit_path):
                body_part_path = os.path.join(visit_path, body_part_folder)
                if not os.path.isdir(body_part_path):
                    continue
                for modality_folder in os.listdir(body_part_path):
                    modality_path = os.path.join(body_part_path, modality_folder)
                    if not os.path.isdir(modality_path):
                        continue
                    for submodality_folder in os.listdir(modality_path):
                        submodality_path = os.path.join(modality_path, submodality_folder)
                        if not os.path.isdir(submodality_path):
                            continue
                        output_submodality_path = os.path.join(output_patient_folder, visit_folder, body_part_folder, modality_folder, submodality_folder)
                        tasks.append((submodality_path, output_submodality_path, case_folder, visit_date, body_part_folder, submodality_folder, modality_folder))
    return tasks

def process_all_in_parallel(tasks):
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_submodality, *task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.exception(f"Error in process_submodality for task={task}: {e}")


if __name__ == "__main__":
    tasks = gather_tasks(input_base_path, output_base_path)
    process_all_in_parallel(tasks)

