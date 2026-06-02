import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

    USE_LOCAL_API = os.getenv("USE_LOCAL_API", "True").lower() in ("true", "1", "yes")
    LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://127.0.0.1:8081")

    DOWNLOAD_PATH = "downloads/"

    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)

if not Config.BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN is not set in the environment variables.")