import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("DEV_ACCESS_TOKEN")
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "true").lower() == "true"
ENABLE_EXPONENTIAL_BACKOFF = os.getenv("ENABLE_EXPONENTIAL_BACKOFF", "false").lower() == "true"
