"""Configuration management for email-triage."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist
CREDENTIALS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Gmail OAuth
CLIENT_SECRET_FILE = CREDENTIALS_DIR / "client_secret.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

# Database
DATABASE_PATH = DATA_DIR / "triage.db"

# User config
USER_EMAIL = os.getenv("USER_EMAIL", "")
WHITELIST_DOMAINS = [
    d.strip()
    for d in os.getenv("WHITELIST_DOMAINS", "").split(",")
    if d.strip()
]

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-6")

# Labels
LOW_PRIORITY_LABEL = os.getenv("LOW_PRIORITY_LABEL", "LowPriority")
REVIEWED_LABEL = os.getenv("REVIEWED_LABEL", "Triaged-Reviewed")

# Webapp
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "127.0.0.1")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8765"))

# High priority keywords in subject/body
HIGH_PRIORITY_KEYWORDS = [
    "invoice", "payment", "contract", "proposal", "urgent",
    "deadline", "meeting", "call", "interview", "offer"
]

# Low priority sender patterns
LOW_PRIORITY_SENDER_PATTERNS = [
    r"noreply@",
    r"no-reply@",
    r"newsletter@",
    r"notifications@",
    r"marketing@",
    r"promo@",
    r"updates@",
    r"digest@",
    r"mailer-daemon@",
]

# Low priority subject patterns
LOW_PRIORITY_SUBJECT_PATTERNS = [
    r"\d+%\s*(off|discount)",
    r"unsubscribe",
    r"weekly digest",
    r"daily digest",
    r"newsletter",
    r"sale ends",
    r"limited time",
    r"don't miss",
]
