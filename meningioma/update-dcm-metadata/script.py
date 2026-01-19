import os
import shutil
import sys
import pydicom
from pydicom.uid import generate_uid
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence


def update_dicom_files(root_path, output_path):
    parent_dir = os.path.dirname(os.path.normpath(root_path))
    root_folder_name = os.path.basename(parent_dir)

    # Map to store consistent StudyInstanceUID for each subfolder
    study_uid_map = {}

    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            input_file = os.path.join(dirpath, filename)

            # Construct output path maintaining directory structure
            relative_path = os.path.relpath(dirpath, root_path)
            output_dir = os.path.join(output_path, relative_path)
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, filename)

            if filename.lower().endswith(".dcm"):
                try:
                    ds = pydicom.dcmread(input_file)

                    # Basic patient details
                    ds.PatientID = root_folder_name
                    ds.PatientName = root_folder_name

                    # Static values
                    ds.InstitutionName = "AIIMS, Bhubaneswar"
                    ds.IssuerOfPatientID = "AIIMS, Bhubaneswar"
                    ds.StudyID = "0fc29c06-390a-4c31-a705-42645b8b4e37"
                    ds.ClinicalTrialProtocolID = "e544b4d4-e4c5-4bb2-ae17-9d666e98cee6"
                    # Institution Code Sequence (as a sequence)
                    inst_code = Dataset()
                    inst_code.CodeValue = "aimbhu"
                    inst_code.CodingSchemeDesignator = "99LOCAL"
                    inst_code.CodeMeaning = "AIIMS, Bhubaneswar"
                    ds.InstitutionCodeSequence = Sequence([inst_code])

                    ds.ConsentForDistributionFlag = "YES"

                    # Folder-based logic
                    subfolders = relative_path.split(os.sep)
                    if len(subfolders) >= 2:
                        first_subfolder = subfolders[0]
                        second_subfolder = subfolders[1]
                        folder_key = os.path.join(first_subfolder, second_subfolder)
                    elif len(subfolders) == 1:
                        first_subfolder = subfolders[0]
                        folder_key = first_subfolder
                        second_subfolder = first_subfolder
                    else:
                        folder_key = "MRI"
                        first_subfolder = "MRI"
                        second_subfolder = "MRI"

                    # Assign same StudyInstanceUID for all files in same subfolder
                    if folder_key not in study_uid_map:
                        study_uid_map[folder_key] = generate_uid()
                    ds.StudyInstanceUID = study_uid_map[folder_key]


                    # Study and Series Descriptions
                    ds.StudyDescription = f"{first_subfolder}-{second_subfolder}"
                    ds.SeriesDescription = second_subfolder
                    ds.AccessionNumber = f"{first_subfolder}_{second_subfolder}"

                    # Save updated DICOM
                    ds.save_as(output_file)
                    print(f"✅ Updated DICOM: {output_file}")

                except Exception as e:
                    print(f"⚠️ Skipping file {input_file}, error: {e}")
            else:
                shutil.copy2(input_file, output_file)
                print(f"📁 Copied non-DICOM file: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python update_dicom.py <root_folder_path> <output_folder_path>")
        sys.exit(1)

    root_path = sys.argv[1]
    output_path = sys.argv[2]

    update_dicom_files(root_path, output_path)

