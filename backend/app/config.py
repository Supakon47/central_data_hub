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


def env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# Google Sheets is deliberately opt-in.  Credentials are only read by the
# command-line sync worker, never from a browser request.
GOOGLE_SHEETS_ENABLED = env_flag("GOOGLE_SHEETS_ENABLED")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

# Local administrator access. Keep these in .env (which is gitignored), never
# in source control. The password value is a one-way PBKDF2 hash.
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "").strip()
ADMIN_SESSION_TTL_SECONDS = int(os.getenv("ADMIN_SESSION_TTL_SECONDS", "28800"))
