import json
import logging
import os

from logtail import LogtailHandler


class ColoredFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = "\033[37m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    log_format = "%(threadName)s::%(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s"

    FORMATS = {
        logging.DEBUG: grey + log_format + reset,
        logging.INFO: grey + log_format + reset,
        logging.WARNING: yellow + log_format + reset,
        logging.ERROR: red + log_format + reset,
        logging.CRITICAL: bold_red + log_format + reset,
        logging.FATAL: bold_red + log_format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class LogTailFormatter(logging.Formatter):
    log_format = "%(processName)s %(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s"

    def format(self, record):
        formatter = logging.Formatter(self.log_format)
        return formatter.format(record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
colored_formatter = ColoredFormatter()
plain_formatter = logging.Formatter("%(threadName)s::%(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s")

console_handler = logging.StreamHandler()
#console_handler.setFormatter(colored_formatter)
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

file_handler = logging.FileHandler('quant-be.log')
file_handler.setFormatter(plain_formatter)
file_handler.setLevel(logging.WARNING)
logger.addHandler(file_handler)

LOGTAIL_TOKEN = os.getenv('LOGTAIL_TOKEN')
if not LOGTAIL_TOKEN and os.path.exists('api.json'):
    LOGTAIL_TOKEN = json.load(open('api.json')).get('LOGTAIL', {}).get('TOKEN')

if LOGTAIL_TOKEN:
    logtail_handler = LogtailHandler(LOGTAIL_TOKEN)
    logtail_handler.setFormatter(colored_formatter)
    logger.addHandler(logtail_handler)


class NotificationHandler(logging.Handler):
    def emit(self, record):
        from quantapi.models import Notification
        if record.levelno <= logging.WARNING:
            return
        n = Notification.objects.create(
            message=record.getMessage(),
            severity=record.levelname,
            notification_type=Notification.Type.LOG,
        )
        n.send()

logger.addHandler(NotificationHandler())