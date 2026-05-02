"""Gmail OAuth2 authentication."""
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import CLIENT_SECRET_FILE, TOKEN_FILE, GMAIL_SCOPES


def get_credentials() -> Credentials:
    """
    Get valid Gmail API credentials.

    On first run, opens a browser for OAuth consent.
    Subsequent runs use the stored refresh token.

    Returns:
        Valid Credentials object

    Raises:
        FileNotFoundError: If client_secret.json is missing
        Exception: If authentication fails
    """
    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            # Run OAuth flow
            if not CLIENT_SECRET_FILE.exists():
                print(f"Error: {CLIENT_SECRET_FILE} not found.")
                print("\nTo set up Gmail API access:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a new project (or select existing)")
                print("3. Enable the Gmail API")
                print("4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID")
                print("5. Select 'Desktop app' as application type")
                print("6. Download the JSON and save as:")
                print(f"   {CLIENT_SECRET_FILE}")
                sys.exit(1)

            print("Opening browser for authentication...")
            print("Please sign in with your Google account and grant access.\n")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Credentials saved to {TOKEN_FILE}")

    return creds


def get_gmail_service():
    """
    Get an authenticated Gmail API service instance.

    Returns:
        Gmail API service resource
    """
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds)


def verify_auth() -> bool:
    """
    Verify that authentication is working.

    Returns:
        True if authenticated successfully
    """
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        print(f"Authenticated as: {profile['emailAddress']}")
        print(f"Total messages: {profile.get('messagesTotal', 'N/A')}")
        return True
    except Exception as e:
        print(f"Authentication failed: {e}")
        return False
