import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(threadName)s::%(asctime)s %(levelname)s %(filename)s:%(lineno)d >> %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

file_handler = logging.FileHandler('quant-be.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

