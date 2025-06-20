import logging

def setup_logging(log_file='app.log'):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ],
        encoding='utf-8'
    )
    return logging.getLogger("AppLogger")

logger = setup_logging()