"""Gmail API integration."""
from .auth import get_credentials, get_gmail_service
from .client import GmailClient
from .labels import LabelManager

__all__ = ["get_credentials", "get_gmail_service", "GmailClient", "LabelManager"]
