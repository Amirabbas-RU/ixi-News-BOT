import logging
import os
import queue
import threading
from datetime import datetime
from set_path import base_path 

#---------------------------------<< config logger >>---------------------------------
log_dir = os.path.join(base_path, "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"{datetime.now():%Y-%m-%d}.log")

logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

# CRITICAL for freeze-resistance: when a handler fails (e.g. dead console /
# broken stderr), logging's default behavior is to print the error traceback
# to sys.stderr — which can itself deadlock on Windows with a closed console.
# Disable it: a handler error must never cascade into a process hang.
logging.raiseExceptions = False

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


class AsyncConsoleHandler(logging.Handler):
    """Console handler that can NEVER block the bot.

    On Windows a console write can block forever (RDP disconnect, service,
    scheduled task, pipe with no reader). We enqueue messages and let a
    dedicated daemon thread write them; if the console stalls, only that
    thread stalls — the bot keeps running. Bounded queue drops old lines
    instead of growing forever.
    """

    def __init__(self, max_queue=500):
        super().__init__()
        self._q = queue.Queue(maxsize=max_queue)
        t = threading.Thread(target=self._writer, daemon=True)
        t.start()

    def emit(self, record):
        try:
            self._q.put_nowait(self.format(record))
        except Exception:
            pass  # queue full / dead — drop console line, never block

    def _writer(self):
        import sys
        while True:
            try:
                msg = self._q.get()
                sys.stdout.write(msg + "\n")
                sys.stdout.flush()
            except Exception:
                # console unusable — drop and continue, file handler unaffected
                try:
                    while True:
                        self._q.get_nowait()
                except Exception:
                    pass

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)

console_handler = AsyncConsoleHandler()
console_handler.setFormatter(ColoredFormatter("%(asctime)s - %(levelname)s - %(message)s"))

if not logger.handlers:  
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

logger.propagate = False

def green(text: str) -> str:
    return f"\033[32m{text}\033[0m"
