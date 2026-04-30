import os
import csv
from datetime import datetime
from PIL import Image

# ==========================================
# CONFIGURATION
# ==========================================
INPUT_FOLDER = r"/Users/triveous/Desktop/batch1"
OUTPUT_FOLDER = r"/Users/triveous/Dev/MIDAS Tools/midas-scripts/oral-cancer/histopath-labeling/compressed_output"
COMPRESSION_QUALITY = 65 

# ==========================================
# LOGGING SETUP
# ==========================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_txt_filename = f"compress_process_log_{timestamp}.txt"
report_csv_filename = f"compress_report_{timestamp}.csv"

def log(message, print_to_console=True):
    if print_to_console:
        print(message)
    try:
        with open(log_txt_filename, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

def compress_images_robust(source_root, dest_root, quality=60):
    valid_extensions = ('.jpg', '.jpeg', '.JPG', '.JPEG')
    log(f"--- STARTING COMPRESSION ---")
    log(f"Source: {source_root}")

    global_stats = {'files': 0, 'compressed': 0, 'skipped': 0, 'errors': 0}

    try:
        csv_file = open(report_csv_filename, 'w', newline='', encoding='utf-8')
        fieldnames = ['Folder Path', 'Total Input', 'Compressed', 'Skipped', 'Errors', 'Details']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        return

    for root, dirs, files in os.walk(source_root):
        if not files:
            continue

        folder_stats = {
            'folder': root,
            'total_files': len(files),
            'compressed': 0,
            'skipped': 0,
            'errors': 0,
            'details': [] 
        }

        relative_path = os.path.relpath(root, source_root)
        output_folder = os.path.join(dest_root, relative_path)

        if not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        for filename in files:
            input_path = os.path.join(root, filename)
            output_path = os.path.join(output_folder, filename)
            
            if not filename.lower().endswith(valid_extensions):
                folder_stats['skipped'] += 1
                continue

            try:
                with Image.open(input_path) as img:
                    if img.mode in ("RGBA", "P", "CMYK"):
                        img = img.convert("RGB")
                    img.save(output_path, "JPEG", optimize=True, quality=quality)
                    folder_stats['compressed'] += 1
            except Exception as e:
                folder_stats['errors'] += 1
                folder_stats['details'].append(f"{filename}: {str(e)}")

        global_stats['files'] += folder_stats['total_files']
        global_stats['compressed'] += folder_stats['compressed']
        global_stats['skipped'] += folder_stats['skipped']
        global_stats['errors'] += folder_stats['errors']

        writer.writerow({
            'Folder Path': folder_stats['folder'],
            'Total Input': folder_stats['total_files'],
            'Compressed': folder_stats['compressed'],
            'Skipped': folder_stats['skipped'],
            'Errors': folder_stats['errors'],
            'Details': " | ".join(folder_stats['details'])
        })
        csv_file.flush()

        if folder_stats['compressed'] > 0:
            log(f"Compressed {folder_stats['compressed']} images in {relative_path}")

    csv_file.close()
    log(f"\n--- COMPLETED ---\nTotal: {global_stats['compressed']} compressed.")

if __name__ == "__main__":
    compress_images_robust(INPUT_FOLDER, OUTPUT_FOLDER, quality=COMPRESSION_QUALITY)
