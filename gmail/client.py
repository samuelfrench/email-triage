"""Gmail API client for reading and managing emails."""
import base64
from dataclasses import dataclass
from typing import Optional, Iterator
from email.utils import parseaddr

from .auth import get_gmail_service
from .labels import LabelManager


@dataclass
class EmailMessage:
    """Represents a Gmail message with relevant fields for triage."""
    message_id: str
    thread_id: str
    sender: str
    sender_email: str
    to: list[str]
    subject: str
    snippet: str
    label_ids: list[str]
    has_unsubscribe: bool
    received_at: str  # ISO format timestamp

    @property
    def is_self_sent(self) -> bool:
        """Check if this email was sent to self."""
        return self.sender_email.lower() in [t.lower() for t in self.to]


class GmailClient:
    """Client for reading and managing Gmail messages."""

    def __init__(self, service=None):
        """
        Initialize GmailClient.

        Args:
            service: Optional Gmail API service. If None, creates one.
        """
        self.service = service or get_gmail_service()
        self.label_manager = LabelManager(self.service)

    def get_inbox_messages(
        self,
        max_results: int = 100,
        include_read: bool = False,
        page_token: Optional[str] = None
    ) -> tuple[list[EmailMessage], Optional[str]]:
        """
        Get messages from inbox.

        Args:
            max_results: Maximum number of messages to return
            include_read: If True, include read messages. If False, only unread.
            page_token: Token for pagination

        Returns:
            Tuple of (list of EmailMessage, next page token or None)
        """
        query = "in:inbox"
        if not include_read:
            query += " is:unread"

        params = {
            "userId": "me",
            "q": query,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token

        results = self.service.users().messages().list(**params).execute()
        messages = results.get("messages", [])
        next_token = results.get("nextPageToken")

        message_ids = [msg["id"] for msg in messages]
        email_messages = self._get_messages_batch(message_ids)

        return email_messages, next_token

    def list_message_ids(
        self,
        query: str,
        max_results_per_page: int = 500,
    ) -> Iterator[str]:
        """Stream all message IDs matching a Gmail search query."""
        page_token = None
        while True:
            params = {
                "userId": "me",
                "q": query,
                "maxResults": max_results_per_page,
            }
            if page_token:
                params["pageToken"] = page_token
            results = self.service.users().messages().list(**params).execute()
            for msg in results.get("messages", []):
                yield msg["id"]
            page_token = results.get("nextPageToken")
            if not page_token:
                break

    def _get_messages_batch(
        self,
        message_ids: list[str],
        batch_size: int = 10,
        max_retries: int = 5,
    ) -> list[EmailMessage]:
        """Fetch metadata for many messages using batched HTTP requests.

        Robust to two failure modes:
        - Per-message HTTP errors (429/500/503) → retried individually with backoff.
        - Whole-batch BatchError ("Response not in multipart/mixed format.") which the
          google client occasionally raises → the whole chunk is retried, with
          exponential backoff and a fall-through to sequential fetches if it keeps
          failing.
        """
        if not message_ids:
            return []

        import time
        from googleapiclient.errors import BatchError, HttpError

        results: dict[str, dict] = {}

        def fetch_chunk(chunk: list[str]) -> list[str]:
            """Fetch one chunk; return list of message_ids that failed with retryable errors.

            Raises BatchError if the entire batch HTTP request fails.
            """
            retryable: list[str] = []

            def make_callback(mid):
                def cb(request_id, response, exception):
                    if exception is None:
                        results[mid] = response
                    elif isinstance(exception, HttpError) and exception.resp.status in (429, 500, 503):
                        retryable.append(mid)
                    else:
                        print(f"Error fetching message {mid}: {exception}")
                return cb

            batch = self.service.new_batch_http_request()
            for mid in chunk:
                req = self.service.users().messages().get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "List-Unsubscribe", "Date"],
                )
                batch.add(req, callback=make_callback(mid))
            batch.execute()
            return retryable

        def fetch_sequential(chunk: list[str]) -> None:
            """Last-resort fallback: fetch one message at a time."""
            for mid in chunk:
                if mid in results:
                    continue
                try:
                    msg = self.service.users().messages().get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["From", "To", "Subject", "List-Unsubscribe", "Date"],
                    ).execute()
                    results[mid] = msg
                except HttpError as e:
                    print(f"Error fetching message {mid} (sequential): {e}")

        for chunk_start in range(0, len(message_ids), batch_size):
            chunk = message_ids[chunk_start:chunk_start + batch_size]
            attempt = 0
            backoff = 1.0
            pending = chunk
            batch_failed = False
            while pending and attempt < max_retries:
                try:
                    pending = fetch_chunk(pending)
                except BatchError as e:
                    print(f"Batch failed ({e}); retrying chunk in {backoff:.1f}s")
                    batch_failed = True
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    attempt += 1
                    continue
                if pending:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    attempt += 1
            if pending or batch_failed:
                # Either still have retryable per-message failures, or every batch
                # attempt blew up — fall through to sequential fetches for remaining IDs.
                missing = [mid for mid in chunk if mid not in results]
                if missing:
                    print(f"Falling back to sequential fetch for {len(missing)} messages")
                    fetch_sequential(missing)

        emails: list[EmailMessage] = []
        for mid in message_ids:
            if mid in results:
                parsed = self._parse_message_payload(results[mid])
                if parsed:
                    emails.append(parsed)
        return emails

    def iter_inbox_messages(
        self,
        include_read: bool = False,
        batch_size: int = 500,
    ) -> Iterator[EmailMessage]:
        """
        Iterate through all inbox messages.

        Args:
            include_read: If True, include read messages
            batch_size: Number of message IDs per list page (Gmail caps at 500)

        Yields:
            EmailMessage objects
        """
        page_token = None
        while True:
            messages, page_token = self.get_inbox_messages(
                max_results=batch_size,
                include_read=include_read,
                page_token=page_token
            )
            for msg in messages:
                yield msg
            if not page_token:
                break

    def _get_message_details(self, message_id: str) -> Optional[EmailMessage]:
        """
        Get full message details.

        Args:
            message_id: Gmail message ID

        Returns:
            EmailMessage or None if error
        """
        try:
            msg = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "List-Unsubscribe", "Date"]
            ).execute()
            return self._parse_message_payload(msg)
        except Exception as e:
            print(f"Error fetching message {message_id}: {e}")
            return None

    def _parse_message_payload(self, msg: dict) -> Optional[EmailMessage]:
        """Parse a Gmail messages.get response into an EmailMessage."""
        try:
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

            sender_name, sender_email = parseaddr(headers.get("From", ""))
            if not sender_email:
                sender_email = headers.get("From", "unknown@unknown.com")

            to_raw = headers.get("To", "")
            to_list = [parseaddr(addr)[1] or addr for addr in to_raw.split(",")]

            return EmailMessage(
                message_id=msg["id"],
                thread_id=msg["threadId"],
                sender=headers.get("From", ""),
                sender_email=sender_email,
                to=to_list,
                subject=headers.get("Subject", "(no subject)"),
                snippet=msg.get("snippet", ""),
                label_ids=msg.get("labelIds", []),
                has_unsubscribe="List-Unsubscribe" in headers,
                received_at=headers.get("Date", ""),
            )
        except Exception as e:
            print(f"Error parsing message {msg.get('id', '?')}: {e}")
            return None

    def add_label(self, message_id: str, label_name: str) -> None:
        """Add a label to a message."""
        self.label_manager.add_label_to_message(message_id, label_name)

    def remove_label(self, message_id: str, label_name: str) -> None:
        """Remove a label from a message."""
        self.label_manager.remove_label_from_message(message_id, label_name)

    def get_message_labels(self, message_id: str) -> list[str]:
        """Get current labels for a message."""
        msg = _retry_transient(lambda: self.service.users().messages().get(
            userId="me",
            id=message_id,
            format="minimal"
        ).execute())
        return msg.get("labelIds", [])

    def mark_as_read(self, message_id: str) -> None:
        """Remove the UNREAD system label."""
        _retry_transient(lambda: self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute())

    def mark_as_unread(self, message_id: str) -> None:
        """Add the UNREAD system label back."""
        _retry_transient(lambda: self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["UNREAD"]}
        ).execute())


def _retry_transient(fn, max_retries: int = 4, base_backoff: float = 1.0):
    """Run a Gmail API call, retrying on transient connection/SSL/rate errors.

    Catches ssl.SSLError, ConnectionError, OSError, BrokenPipeError, and
    HTTP 429/500/503 responses. Other errors bubble up unchanged.
    """
    import socket
    import ssl
    import time
    from googleapiclient.errors import HttpError

    backoff = base_backoff
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status not in (429, 500, 503) or attempt == max_retries:
                raise
        except (ssl.SSLError, ConnectionError, BrokenPipeError, socket.timeout, OSError) as e:
            if attempt == max_retries:
                raise
        time.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
    return None  # unreachable
