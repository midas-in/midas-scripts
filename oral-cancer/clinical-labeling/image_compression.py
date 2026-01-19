import os
import csv
from datetime import datetime
from PIL import Image

# ==========================================
# CONFIGURATION
# ==========================================
INPUT_FOLDER = r"input_folder_path"
OUTPUT_FOLDER = r"output_folder_path"
COMPRESSION_QUALITY = 65 

# ==========================================
# LOGGING SETUP
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"compress_process_log_{timestamp}.txt"
report_csv_filename = f"compress_report_{timestamp}.csv"

def log(message, print_to_console=True):
    """
    Helper function to print to console AND write to text file immediately.
    """
    if print_to_console:
        print(message)
    
    try:
        with open(log_txt_filename, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not write to log file: {e}")

# ==========================================
# MAIN LOGIC
# ==========================================
def compress_images_robust(source_root, dest_root, quality=60):
    
    valid_extensions = ('.jpg', '.jpeg', '.JPG', '.JPEG')
    
    log(f"--- STARTING ROBUST COMPRESSION JOB ---")
    log(f"Time: {datetime.now()}")
    log(f"Source: {source_root}")
    log(f"Destination: {dest_root}")
    log("-" * 60)

    # Global counters for final summary
    global_stats = {
        'files': 0,
        'compressed': 0,
        'skipped': 0,
        'errors': 0
    }

    # --- OPEN CSV FILE *BEFORE* THE LOOP ---
    try:
        csv_file = open(report_csv_filename, 'w', newline='', encoding='utf-8')
        fieldnames = ['Folder Path', 'Total Input', 'Compressed', 'Skipped', 'Errors', 'Details']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
    except Exception as e:
        log(f"FATAL ERROR: Cannot create CSV file: {e}")
        return

    log(f"Scanning folders and streaming results to CSV...")

    # Walk through every folder
    for root, dirs, files in os.walk(source_root):
        
        # Skip empty folders to keep report clean
        if not files:
            continue

        # --- PER FOLDER STATS ---
        folder_stats = {
            'folder': root,
            'total_files': len(files),
            'compressed': 0,
            'skipped': 0,
            'errors': 0,
            'details': [] 
        }

        # Calculate destination folder path
        relative_path = os.path.relpath(root, source_root)
        output_folder = os.path.join(dest_root, relative_path)

        # Create output folder
        if not os.path.exists(output_folder):
            try:
                os.makedirs(output_folder)
            except Exception as e:
                log(f"❌ Error creating folder {output_folder}: {e}")
                # If we can't create the folder, we fail all files in it
                folder_stats['errors'] = len(files)
                folder_stats['details'].append(f"Could not create directory: {e}")
                writer.writerow({
                    'Folder Path': root,
                    'Total Input': len(files),
                    'Compressed': 0,
                    'Skipped': 0,
                    'Errors': len(files),
                    'Details': str(e)
                })
                continue

        # Process files in this folder
        for filename in files:
            input_path = os.path.join(root, filename)
            output_path = os.path.join(output_folder, filename)
            
            # Check extension
            if not filename.lower().endswith(valid_extensions):
                folder_stats['skipped'] += 1
                # Optional: Uncomment if you want to see every non-jpg in the log
                # folder_stats['details'].append(f"[SKIPPED] {filename}") 
                continue

            try:
                with Image.open(input_path) as img:
                    # Handle Mode (RGBA/P -> RGB) to prevent crashes on PNGs renamed as JPGs
                    if img.mode in ("RGBA", "P", "CMYK"):
                        img = img.convert("RGB")

                    # Compress and Save
                    img.save(output_path, "JPEG", optimize=True, quality=quality)
                    
                    folder_stats['compressed'] += 1

            except Exception as e:
                folder_stats['errors'] += 1
                error_msg = f"[ERROR] {filename}: {str(e)}"
                folder_stats['details'].append(error_msg)
                log(f"  ❌ {error_msg}") # Print errors to console immediately

        # --- UPDATE GLOBALS ---
        global_stats['files'] += folder_stats['total_files']
        global_stats['compressed'] += folder_stats['compressed']
        global_stats['skipped'] += folder_stats['skipped']
        global_stats['errors'] += folder_stats['errors']

        # --- WRITE ROW TO CSV IMMEDIATELY ---
        try:
            writer.writerow({
                'Folder Path': folder_stats['folder'],
                'Total Input': folder_stats['total_files'],
                'Compressed': folder_stats['compressed'],
                'Skipped': folder_stats['skipped'],
                'Errors': folder_stats['errors'],
                'Details': " | ".join(folder_stats['details'])
            })
            # Force write to disk to prevent data loss on crash
            csv_file.flush() 
        except Exception as e:
            log(f"Error writing row to CSV: {e}")

        # --- LOG PROGRESS ---
        # Only log to console if something interesting happened (compression or error)
        # to avoid spamming the console for 10,000 folders
        if folder_stats['compressed'] > 0 or folder_stats['errors'] > 0:
            log(f"Processed: .../{relative_path} | Compressed: {folder_stats['compressed']} | Errors: {folder_stats['errors']}", print_to_console=True)

    # --- CLEANUP ---
    csv_file.close()

    # --- FINAL SUMMARY ---
    log(f"\n--- JOB COMPLETED ---")
    log(f"Total Files Found:     {global_stats['files']}")
    log(f"Successfully Compressed: {global_stats['compressed']}")
    log(f"Total Skipped:         {global_stats['skipped']} (Non-JPGs)")
    log(f"Total Errors:          {global_stats['errors']}")
    log(f"Log saved to: {os.path.abspath(log_txt_filename)}")
    log(f"CSV Report:   {os.path.abspath(report_csv_filename)}")

if __name__ == "__main__":
    compress_images_robust(INPUT_FOLDER, OUTPUT_FOLDER, quality=COMPRESSION_QUALITY)