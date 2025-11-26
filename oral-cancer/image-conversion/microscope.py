import os
import sys
import pydicom
import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, Dataset
from datetime import datetime
import warnings
import tempfile
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from logger_util import get_logger
from pydicom.sequence import Sequence

logger = get_logger()

warnings.filterwarnings("ignore", message="The value length .* exceeds the maximum length of 16 allowed for VR SH.")

def calculate_meta_information_group_length(ds):
    """Calculate the length of all group 0002 elements."""
    # Temporarily remove the FileMetaInformationGroupLength tag to calculate its size correctly
    temp_meta = ds.file_meta.copy()
    if 'FileMetaInformationGroupLength' in temp_meta:
        del temp_meta['FileMetaInformationGroupLength']

    # Create a dataset with just the meta information to calculate the size
    meta_ds = FileDataset(None, {}, file_meta=temp_meta, preamble=b"\0" * 128)

    # Use a temporary file to calculate the size
    with tempfile.NamedTemporaryFile(delete=True) as temp_file:
        meta_ds.save_as(temp_file.name)
        # Calculate the length of the meta information group
        meta_length = os.path.getsize(temp_file.name) - 132  # Subtract the preamble (128 bytes) + DICM (4 bytes)

    return meta_length


def validate_dicom_file(dicom_file_path):
    """Validate a DICOM file using dcm2xml from DCMTK."""
    try:
        # Run the validation command (dcm2xml)
        result = subprocess.run(
            ['dcm2xml', dicom_file_path],
            capture_output=True,
            text=False  # Set text to False to handle binary output
        )

        # Decode the output, allowing it to ignore decoding errors
        output = result.stdout.decode('utf-8', errors='ignore')
        error_output = result.stderr.decode('utf-8', errors='ignore')

        # Check if the command was successful
        if result.returncode == 0:
            logger.info(f"Validation successful for {dicom_file_path}")
            logger.info(f'output: {output}')
        else:
            logger.error(f"Validation failed for {dicom_file_path}")
            logger.error(f'error_output: {error_output}')

    except Exception as e:
        logger.exception(f"Error during DICOM validation: {e}")


def microscope_jpeg_to_dicom(jpeg_path, dicom_output_path, patient_name, patient_id, description, accessionNumber, visit_date, series_uid, study_uid, body_part):
    """Convert a JPEG image to a DICOM instance within a series."""
    # Read the image
    img = Image.open(jpeg_path)
    img_array = np.array(img)

    # Create a DICOM dataset
    file_meta = Dataset()

    file_meta.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = '1.2.840.10008.1.2'
    file_meta.ImplementationClassUID = '1.2.826.0.1.3680043.8.498'  # Example UID for your implementation
    file_meta.ImplementationVersionName = 'MY_APP_1.0'

    # Create the main dataset (empty) with the file metadata
    ds = FileDataset(jpeg_path, {}, file_meta=file_meta, preamble=b"\0" * 128)

    # Set creation date and time
    dt = datetime.now()
    ds.ContentDate = dt.strftime('%Y%m%d')  # Set the content date
    ds.ContentTime = dt.strftime('%H%M%S')  # Set the content time

    # Add DICOM-specific information
    ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.7'

    ds.SOPInstanceUID = generate_uid()  # Unique identifier for each DICOM instance
    ds.PatientName = patient_name
    ds.PatientID = patient_id
    ds.StudyDescription = description
    ds.Modality = "GM"  # Secondary Capture
    ds.AccessionNumber = accessionNumber

    # Convert string to datetime
    visit_date_obj = datetime.strptime(visit_date, "%d-%m-%Y")

    # Format it as YYYYMMDD for DICOM
    ds.StudyDate = visit_date_obj.strftime("%Y%m%d")
    ds.SeriesInstanceUID = series_uid  # Same SeriesInstanceUID for all instances in the series
    ds.StudyInstanceUID = study_uid  # Same StudyInstanceUID for all instances in the study
    ds.BodyPartExamined = body_part  

    ds.StudyID = 'dc75099e-b3ed-434e-bc07-5b27e95aa27a'
    ds.ClinicalTrialProtocolID = 'd01f56a5-5358-4523-979a-cef8d8a7f67a'

    # Add Series Number and Series Description
    ds.SeriesNumber = "1"
    ds.SeriesDescription = "General Microscopy"

    # Add the pixel data to the dataset
    ds.PixelData = img_array.tobytes()
    ds.Rows, ds.Columns = img_array.shape[:2]
    ds.SamplesPerPixel = 3 if len(img_array.shape) == 3 else 1
    ds.PhotometricInterpretation = "RGB"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0

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

    # Dynamically calculate FileMetaInformationGroupLength
    ds.file_meta.FileMetaInformationGroupLength = calculate_meta_information_group_length(ds) + 12
    filename = os.path.basename(jpeg_path).split('.')[0]
    output_file = os.path.join(dicom_output_path, f"{filename}.dcm")
    ds.save_as(output_file)

def convert_folder(jpeg_folder, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    logger.info(f"jpeg_folder : {jpeg_folder}")
    series_uid = pydicom.uid.generate_uid()
    study_uid = pydicom.uid.generate_uid() 
    parts = jpeg_folder.split(os.sep)
    patient_name = parts[parts.index(next(p for p in parts if p.startswith("VISIT_"))) - 1]
    logger.info(f"Patient Name: {patient_name}")

    # Extract visit date using next() and a generator expression
    visit_date = next((part[6:] for part in jpeg_folder.split(os.sep) if part.startswith("VISIT_")), None)
    logger.info(f"Visit Date: {visit_date}")  # Output: 11-03-2025

    body_part = next((parts[i + 1] for i, part in enumerate(parts) if part.startswith("VISIT_") and i + 1 < len(parts)), None)
    logger.info(f"Body Part: {body_part}")

    magnificationLevel = os.path.basename(jpeg_folder)
    parts = os.path.normpath(jpeg_folder).split(os.sep)
    magnificationLevel = parts[-1]        # '10x'
    imgType = parts[-2]        # 'HISTOPATH'
    description = imgType + "-" + magnificationLevel
    accessionNumber = patient_name + "-" + imgType + "-" + magnificationLevel

    for filename in os.listdir(jpeg_folder):
        if filename.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")):
            jpeg_path = os.path.join(jpeg_folder, filename)
            microscope_jpeg_to_dicom(jpeg_path, output_folder, patient_name, patient_name, description, accessionNumber, visit_date, series_uid, study_uid, body_part)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        logger.error("Usage: python microscope.py <input_folder> <output_folder>")
        sys.exit(1)
    convert_folder(sys.argv[1], sys.argv[2])
