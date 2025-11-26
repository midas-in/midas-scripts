# logger_util.py
import logging
import os

def get_logger(name="dicom_logger", log_file="conversion.log"):
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if logger already configured
    if not logger.handlers:
        file_handler = logging.FileHandler(os.path.join(log_dir, log_file))
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger
