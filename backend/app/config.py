from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/data_hub.db")
APP_ENV = os.getenv("APP_ENV", "development")
APP_NAME = os.getenv("APP_NAME", "Central Data Hub")
PAGE_SIZE_DEFAULT = int(os.getenv("PAGE_SIZE_DEFAULT", "25"))
PAGE_SIZE_MAX = int(os.getenv("PAGE_SIZE_MAX", "100"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"
