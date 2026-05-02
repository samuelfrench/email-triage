"""Gmail label management."""
from typing import Optional

from config import LOW_PRIORITY_LABEL


class LabelManager:
    """Manages Gmail labels for email triage."""

    def __init__(self, service):
        """
        Initialize LabelManager.

        Args:
            service: Authenticated Gmail API service
        """
        self.service = service
        self._label_cache: dict[str, str] = {}  # name -> id mapping

    def get_or_create_label(self, label_name: str = LOW_PRIORITY_LABEL) -> str:
        """
        Get or create a Gmail label.

        Args:
            label_name: Name of the label

        Returns:
            Label ID
        """
        # Check cache first
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        # List existing labels
        results = self.service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])

        for label in labels:
            if label["name"] == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]

        # Create if not exists
        label_body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        created = self.service.users().labels().create(
            userId="me", body=label_body
        ).execute()

        self._label_cache[label_name] = created["id"]
        print(f"Created label: {label_name}")
        return created["id"]

    def add_label_to_message(self, message_id: str, label_name: str = LOW_PRIORITY_LABEL) -> None:
        """
        Add a label to a message.

        Args:
            message_id: Gmail message ID
            label_name: Name of label to add
        """
        label_id = self.get_or_create_label(label_name)
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]}
        ).execute()

    def remove_label_from_message(self, message_id: str, label_name: str = LOW_PRIORITY_LABEL) -> None:
        """
        Remove a label from a message.

        Args:
            message_id: Gmail message ID
            label_name: Name of label to remove
        """
        label_id = self.get_or_create_label(label_name)
        self.service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": [label_id]}
        ).execute()

    def get_label_id(self, label_name: str) -> Optional[str]:
        """
        Get label ID by name, returns None if not found.

        Args:
            label_name: Name of the label

        Returns:
            Label ID or None
        """
        if label_name in self._label_cache:
            return self._label_cache[label_name]

        results = self.service.users().labels().list(userId="me").execute()
        for label in results.get("labels", []):
            if label["name"] == label_name:
                self._label_cache[label_name] = label["id"]
                return label["id"]

        return None
