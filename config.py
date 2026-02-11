import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    
    DOWNLOAD_PATH = "downloads/"

    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH)

if not Config.BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN is not set in the environment variables.")