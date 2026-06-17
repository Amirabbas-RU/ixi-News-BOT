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

class ColoredFormatter(logging.Formatter):
    COLORS = {
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        msg = super().format(record)
        if color:
            return f"{color}{msg}{self.RESET}"
        return msg

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter("%(asctime)s - %(levelname)s - %(message)s"))

if not logger.handlers:  
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

logger.propagate = False

def green(text: str) -> str:
    return f"\033[32m{text}\033[0m"
