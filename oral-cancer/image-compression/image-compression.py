from PIL import Image
import os
import shutil
import logging

# Set up logging
log_file_path = '/logs/log.txt'
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

            logging.info(f"Processed {input_path} -> {output_path} ({resized_width}x{resized_height})")

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
                logging.info(f"Compressing images in folder: {root}")
                os.makedirs(output_dir, exist_ok=True)

                image_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff'))]
                logging.info(f"Found {len(image_files)} images to compress in {root}")

                compressed_count = 0
                for file_name in image_files:
                    input_path = os.path.join(root, file_name)
                    ext = file_name.lower().split('.')[-1]
                    new_ext = 'jpg' if ext in ['jpg', 'jpeg', 'png'] else 'tif'
                    output_file_name = os.path.splitext(file_name)[0] + f".{new_ext}"
                    output_path = os.path.join(output_dir, output_file_name)

                    logging.info(f"Processing image: {input_path}")
                    resize_image_fixed_dimensions(input_path, output_path, new_width, new_height, quality)

                    if os.path.exists(output_path):
                        compressed_count += 1
                    else:
                        logging.error(f"Failed to create compressed file: {output_path}")

                logging.info(f"Compressed {compressed_count} images out of {len(image_files)} in {root}")

            else:
                logging.info(f"Copying folder: {root} to {output_dir}")
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                shutil.copytree(root, output_dir, dirs_exist_ok=True)

                copied_files = []
                for dirpath, _, filenames in os.walk(output_dir):
                    for fname in filenames:
                        full_path = os.path.join(dirpath, fname)
                        copied_files.append(os.path.relpath(full_path, output_dir))

                original_files = []
                for dirpath, _, filenames in os.walk(root):
                    for fname in filenames:
                        original_files.append(os.path.relpath(os.path.join(dirpath, fname), root))

                # Check if all original files are copied
                missing_files = set(original_files) - set(copied_files)
                if missing_files:
                    logging.error(f"Missing copied files in {output_dir}: {missing_files}")
                else:
                    logging.info(f"Successfully copied all {len(original_files)} files to {output_dir}")

        except Exception as e:
            logging.error(f"Error processing folder {root}: {str(e)}")


input_folder = '/Users/triveous/Dev/Scripts/conversions/dummy-data'
output_folder = '/Users/triveous/Dev/Scripts/image-compression/output'

logging.info(f"Starting processing for input folder: {input_folder}")
try:
    process_images_in_structure(input_folder, output_folder, new_width=700, new_height=700, quality=100)
except Exception as e:
    logging.error(f"Unexpected error during processing: {str(e)}")
logging.info(f"Finished processing for input folder: {input_folder}")

