import logging
from os import getenv

def setup_logging(log_file='app.log', level=logging.DEBUG):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ],
        encoding='utf-8'
    )
    return logging.getLogger("AppLogger")

logger = setup_logging(log_file=getenv('LOG_FILE', 'app.log'), level=logging.DEBUG if getenv('LOG_LEVEL') == 'DEBUG' else logging.INFO)