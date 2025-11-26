import os
import requests
from requests.auth import HTTPBasicAuth
import uuid

# PACS server upload URL
pacs_upload_url = "https://staging.meningioma.midaspacs.in/dcm4chee-arc/aets/DCM4CHEE/rs/studies"
# Path to the main data folder
main_folder_path = "/Users/triveous/Dev/Scripts/updatePatientIdForDcm/AIIMS-Del/00129AIIMSD160422"

def get_pacs_access_token():
    # Define the token URL and parameters
    pacs_token_url = "https://staging.meningioma.midaspacs.in/auth/realms/midas/protocol/openid-connect/token"
    client_id = "pacs-rs"
    client_secret = "dU22uVdEKvR87qeswXvpeRlnsIIBllzW"
    grant_type = "client_credentials"

    # Prepare the data payload for the POST request
    data = {
        'grant_type': grant_type,
        'client_id': client_id,
        'client_secret': client_secret
    }

    # Make the POST request to fetch the token
    try:
        response = requests.post(pacs_token_url, data=data)
        response.raise_for_status()  # Check for HTTP errors
        token_data = response.json()
        return token_data.get("access_token")
    
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return None


# Path to the log directory and files
log_dir = "/Users/triveous/Dev/Scripts/upload-scripts/logs"
success_file_path = os.path.join(log_dir, "success_uploads_batch7.txt")
failure_file_path = os.path.join(log_dir, "failure_uploads_batch7.txt")

# Function to read the contents of a log file and return them as a set
def read_log_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as log_file:
            return set(log_file.read().splitlines())
    return set()

# Function to write the updated set of paths to the log file
def write_log_file(file_path, data_set):
    with open(file_path, 'w') as log_file:
        log_file.write("\n".join(sorted(data_set)))


boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

def upload_dicom(file_path):
    try:
        # Retrieve the access token
        token = get_pacs_access_token()
        if not token:
            print("Failed to retrieve access token.")
            return False

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

            # Check if the upload was successful
            if response.status_code == 200:
                print(f"Uploaded successfully for {file_path}.")
                return True
            else:
                print(f"Upload failed for {file_path}. Status code: {response.status_code}")
                print("Response content:", response.text)  # Print response text for more details
                return False
    except Exception as e:
        print(f"Error uploading {file_path}: {e}")
        return False


# Ensure log directory exists
os.makedirs(log_dir, exist_ok=True)

# Function to log the result of the upload
def log_result(file_path, is_successful, success_set, failure_set):
    if is_successful:
        # Add to success set and remove from failure set if present
        success_set.add(file_path)
        failure_set.discard(file_path)
    else:
        # Add to failure set if not successful
        failure_set.add(file_path)

# Function to process each folder and upload DICOM files
def process_folder(folder_path, success_set, failure_set):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".dcm"):
                file_path = os.path.join(root, file)
                
                # Skip files that are already uploaded successfully
                if file_path in success_set:
                    print(f"Skipping already uploaded file: {file_path}")
                    continue

                print(f"Uploading file: {file_path}")
                is_successful = upload_dicom(file_path)
                
                # Log the result and update success/failure sets
                log_result(file_path, is_successful, success_set, failure_set)

# Main process
def main():
    if os.path.exists(main_folder_path):
        print(f"Starting upload process for folder: {main_folder_path}")

        # Load success and failure logs
        success_set = read_log_file(success_file_path)
        failure_set = read_log_file(failure_file_path)

        # Process the folder and upload DICOM files
        process_folder(main_folder_path, success_set, failure_set)

        # Write back updated success and failure logs
        write_log_file(success_file_path, success_set)
        write_log_file(failure_file_path, failure_set)

        print("Upload process completed.")
    else:
        print(f"Folder does not exist: {main_folder_path}")

if __name__ == "__main__":
    main()

