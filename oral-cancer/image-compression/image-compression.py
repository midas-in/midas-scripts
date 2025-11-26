from PIL import Image
import os
import shutil
import logging

# Set up logging
log_file_path = '/Users/triveous/Dev/Scripts/image-compression/error_log.txt'
logging.basicConfig(filename=log_file_path, level=logging.ERROR, format='%(asctime)s - %(message)s')


def resize_image_fixed_dimensions(input_path, output_path, new_width, new_height, quality=90):
    try:
        with Image.open(input_path) as img:
            original_width, original_height = img.size
            aspect_ratio = original_width / original_height

            if original_width > original_height:
                resized_width = new_width
                resized_height = int(resized_width / aspect_ratio)
            else:
                resized_height = new_height
                resized_width = int(resized_height * aspect_ratio)

            img = img.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

            ext = input_path.lower().split('.')[-1]
            if ext in ['jpg', 'jpeg', 'png']:
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert("RGB")
                img.save(output_path, format='JPEG', quality=quality, optimize=True)
            elif ext in ['tif', 'tiff']:
                img.save(output_path, format='TIFF', compression="tiff_adobe_deflate")

            print(f"Processed {input_path} -> {output_path} ({resized_width}x{resized_height})")

    except Exception as e:
        logging.error(f"Error processing {input_path}: {str(e)}")


def is_under_folder(path, target_folder_names):
    return any(folder in os.path.normpath(path).split(os.sep) for folder in target_folder_names)


def process_images_in_structure(input_folder, output_folder, new_width, new_height, quality=90):
    for root, dirs, files in os.walk(input_folder):
        relative_path = os.path.relpath(root, input_folder)
        output_dir = os.path.join(output_folder, relative_path)

        try:
            if is_under_folder(root, ['GM', 'XC']):
                os.makedirs(output_dir, exist_ok=True)

                for file_name in files:
                    if file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')):
                        input_path = os.path.join(root, file_name)
                        ext = file_name.lower().split('.')[-1]
                        new_ext = 'jpg' if ext in ['jpg', 'jpeg', 'png'] else 'tif'
                        output_file_name = os.path.splitext(file_name)[0] + f".{new_ext}"
                        output_path = os.path.join(output_dir, output_file_name)

                        print(f"Processing image: {input_path}")
                        resize_image_fixed_dimensions(input_path, output_path, new_width, new_height, quality)
            else:
                if not os.path.exists(output_dir):
                    print(f"Copying folder: {root} to {output_dir}")
                    shutil.copytree(root, output_dir, dirs_exist_ok=True)

        except Exception as e:
            logging.error(f"Error processing folder {root}: {str(e)}")


# === Loop Through Batches ===
# batch_numbers = [1,2,3, 4, 5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24]  # Add batch numbers you want to process here

# for batch_num in batch_numbers:
input_folder = '/Users/triveous/Dev/Scripts/conversions/dummy-data'
output_folder = '/Users/triveous/Dev/Scripts/image-compression/output'

print(f"\nStarting processing for batch1")
try:
    process_images_in_structure(input_folder, output_folder, new_width=700, new_height=700, quality=100)
except Exception as e:
    logging.error(f"Unexpected error during batch1: {str(e)}")
