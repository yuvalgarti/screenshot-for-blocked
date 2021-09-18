import logging
import sys

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')
logFormat = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logFormat)
logger.addHandler(console_handler)
