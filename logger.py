import logging
import os
from datetime import datetime
from set_path import base_path 

#---------------------------------<< config logger >>---------------------------------
log_dir = os.path.join(base_path, "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"{datetime.now():%Y-%m-%d}.log")

logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

if not logger.handlers:  
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

logger.propagate = False
