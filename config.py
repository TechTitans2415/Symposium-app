import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = os.environ.get("GOOGLE_DISCOVERY_URL")

SECRET_KEY = os.environ.get("SECRET_KEY")

ADMIN_ID = os.environ.get("ADMIN_ID")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

MAIL_ID = os.environ.get("MAIL_ID")
MAIL_APP_PASSWORD = os.environ.get("MAIL_APP_PASSWORD")
