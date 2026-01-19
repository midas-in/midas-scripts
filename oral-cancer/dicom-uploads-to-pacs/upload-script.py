import os
import requests
from requests.auth import HTTPBasicAuth
import uuid
import logging
from datetime import datetime

# =========================
# CONFIGURATION
# =========================
pacs_upload_url = "https://{HOST}/dcm4chee-arc/aets/DCM4CHEE/rs/studies"
main_folder_path = "***/path/to/input/dicom/folder***"

# Logging setup
log_dir = "***/path/to/log/directory***"
log_file_path = os.path.join(log_dir, "upload_validation.log")
success_file_path = os.path.join(log_dir, "success_uploads_batch.txt")
failure_file_path = os.path.join(log_dir, "failure_uploads_batch.txt")

# Setup logger
logger = logging.getLogger("pacs_upload")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def get_pacs_access_token():
    # Define the token URL and parameters
    pacs_token_url = "https://{HOST}/auth/realms/midas/protocol/openid-connect/token"
    client_id = "***CLIENT_ID***"
    client_secret = "***CLIENT_SECRET***"
    grant_type = "client_credentials"

    # Prepare the data payload for the POST request
    data = {
        'grant_type': grant_type,
        'client_id': client_id,
        'client_secret': client_secret
    }

    # Make the POST request to fetch the token
    try:
        logger.info("Fetching PACS access token...")
        response = requests.post(pacs_token_url, data=data, verify=False)
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("access_token")
        logger.info("✅ PACS access token obtained successfully")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to retrieve access token: {e}")
        return None

def read_log_file(file_path):
    """Read log file contents as a set."""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as log_file:
                return set(log_file.read().splitlines())
        except Exception as e:
            logger.error(f"Error reading log file {file_path}: {e}")
    return set()

def write_log_file(file_path, data_set):
    """Write set contents back to log file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as log_file:
            log_file.write("\n".join(sorted(data_set)))
        logger.debug(f"Updated log file: {file_path} with {len(data_set)} entries")
    except Exception as e:
        logger.error(f"Error writing log file {file_path}: {e}")

def collect_input_dicom_files(folder_path):
    """Recursively collect all DICOM files from input folder."""
    dicom_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".dcm"):
                file_path = os.path.join(root, file)
                dicom_files.append(file_path)
    return dicom_files


boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

def upload_dicom(file_path):
    """Upload single DICOM file to PACS."""
    try:
        # Retrieve the access token
        token = get_pacs_access_token()
        if not token:
            logger.error(f"Failed to get token for {file_path}")
            return False
        
        logger.debug(f"Starting upload for: {file_path}")
        # Open the DICOM file in binary mode
        with open(file_path, 'rb') as dicom_file:
            # Manually set the content type with boundary
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': f'multipart/related; boundary={boundary}; type="application/dicom"'
            }
            # Create the files dictionary with a proper tuple format (field_name, file_content)
            files = {
                'file': (file_path, dicom_file, 'application/dicom')
            }
            # Manually craft the body of the request
            body = f'--{boundary}\r\nContent-Type: application/dicom\r\n\r\n'
            with open(file_path, 'rb') as dicom_file:
                body += dicom_file.read().decode('latin1') 
            body += f'\r\n--{boundary}--\r\n'  # Closing the multipart
            
            response = requests.post(pacs_upload_url, headers=headers, data=body.encode('latin1'), verify=False)

            logger.debug(f"Upload response status for {file_path}: {response.status_code}")
            # Check if the upload was successful
            if response.status_code in [200, 201]:
                logger.info(f"✅ Uploaded successfully: {file_path}")
                return True
            else:
                logger.error(f"❌ Upload failed for {file_path}. Status: {response.status_code}")
                logger.error(f"Response: {response.text[:500]}...")  # First 500 chars
                return False
    except Exception as e:
        logger.error(f"❌ Exception uploading {file_path}: {str(e)}")
        return False

# Ensure log directory exists
os.makedirs(log_dir, exist_ok=True)

# Function to log the result of the upload
def log_result(file_path, is_successful, success_set, failure_set):
    """Log upload result to success/failure sets."""
    if is_successful:
        success_set.add(file_path)
        failure_set.discard(file_path)
        logger.debug(f"Added to success: {os.path.basename(file_path)}")
    else:
        failure_set.add(file_path)
        logger.debug(f"Added to failure: {os.path.basename(file_path)}")

# Function to process each folder and upload DICOM files
def process_folder(folder_path, success_set, failure_set):
    """Process folder and upload DICOM files with validation."""
    logger.info(f"Scanning input folder: {folder_path}")
    # Collect all input DICOM files first
    input_dicom_files = collect_input_dicom_files(folder_path)
    logger.info(f"Found {len(input_dicom_files)} DICOM files in input folder")
    
    if not input_dicom_files:
        logger.warning("No DICOM files found in input folder")
        return
    
    processed_count = 0
    skipped_count = 0
    failed_uploads = []


    for file_path in input_dicom_files:
        # Skip already successfully uploaded files
        if file_path in success_set:
            logger.info(f"⏭️  Skipping already uploaded: {os.path.basename(file_path)}")
            skipped_count += 1
            continue

        processed_count += 1
        logger.info(f"📤 Uploading ({processed_count}/{len(input_dicom_files)}): {os.path.basename(file_path)}")
        
        is_successful = upload_dicom(file_path)
        log_result(file_path, is_successful, success_set, failure_set)
        
        if not is_successful:
            failed_uploads.append(file_path)
    
    # Final validation summary
    logger.info("="*80)
    logger.info("📊 UPLOAD VALIDATION SUMMARY")
    logger.info(f"Total input DICOM files: {len(input_dicom_files)}")
    logger.info(f"Skipped (already uploaded): {skipped_count}")
    logger.info(f"Processed: {processed_count}")
    logger.info(f"Successfully uploaded: {len(success_set)}")
    logger.info(f"Failed uploads: {len(failed_uploads)}")
    
    if failed_uploads:
        logger.error("❌ FAILED FILES:")
        for failed_file in failed_uploads:
            logger.error(f"  {os.path.basename(failed_file)}")
    
    logger.info("="*80)

# Main process
def main():
    """Main execution with full validation."""
    logger.info("🚀 Starting PACS DICOM upload with validation")
    logger.info(f"Input folder: {main_folder_path}")
    
    if not os.path.exists(main_folder_path):
        logger.error(f"❌ Input folder does not exist: {main_folder_path}")
        return

    try:
        # Load existing success/failure logs
        success_set = read_log_file(success_file_path)
        failure_set = read_log_file(failure_file_path)
        logger.info(f"Loaded {len(success_set)} success records, {len(failure_set)} failure records")
        
        # Process with validation
        process_folder(main_folder_path, success_set, failure_set)
        
        # Save final logs
        write_log_file(success_file_path, success_set)
        write_log_file(failure_file_path, failure_set)
        
        logger.info("✅ Upload process completed with validation")
        logger.info(f"Final logs saved to:")
        logger.info(f"  Success: {success_file_path}")
        logger.info(f"  Failures: {failure_file_path}")
        logger.info(f"  Detailed log: {log_file_path}")
        
    except Exception as e:
        logger.error(f"💥 Unexpected error in main: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
