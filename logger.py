import os
import json
import logging
from logtail import LogtailHandler


class ColoredFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = "\033[37m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(threadName)s::%(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
        logging.FATAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class LogTailFormatter(logging.Formatter):
    format = "%(processName)s %(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s"

    def format(self, record):
        formatter = logging.Formatter(self.format)
        return formatter.format(record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = ColoredFormatter()

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

file_handler = logging.FileHandler('quant-be.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

LOGTAIL_TOKEN = os.getenv('LOGTAIL_TOKEN')
if not LOGTAIL_TOKEN and os.path.exists('api.json'):
    LOGTAIL_TOKEN = json.load(open('api.json')).get('LOGTAIL', {}).get('TOKEN')

if LOGTAIL_TOKEN:
    logtail_handler = LogtailHandler(LOGTAIL_TOKEN)
    logtail_handler.setFormatter(formatter)
    logger.addHandler(logtail_handler)
else:
    logger.warning('LOGTAIL_TOKEN not set, logging locally.')
