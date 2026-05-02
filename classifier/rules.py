"""Rule-based email classifier."""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from config import USER_EMAIL, WHITELIST_DOMAINS
from gmail.client import EmailMessage
from .patterns import (
    is_low_priority_sender,
    is_low_priority_subject,
    is_automated_notification,
    has_high_priority_keywords,
)


class Priority(Enum):
    """Email priority levels."""
    HIGH = auto()
    LOW = auto()
    UNCERTAIN = auto()


@dataclass
class ClassificationResult:
    """Result of email classification."""
    priority: Priority
    method: str  # 'rule' | 'ai'
    rule_name: Optional[str] = None
    confidence: float = 1.0
    reason: Optional[str] = None

    def __str__(self) -> str:
        parts = [f"{self.priority.name}"]
        if self.rule_name:
            parts.append(f"({self.rule_name})")
        if self.reason:
            parts.append(f": {self.reason}")
        return " ".join(parts)


class RuleClassifier:
    """Rule-based email classifier."""

    def __init__(
        self,
        user_email: str = None,
        whitelist_domains: list[str] = None,
    ):
        """
        Initialize rule classifier.

        Args:
            user_email: User's email address for self-sent detection
            whitelist_domains: Domains that are always high priority
        """
        self.user_email = (user_email or USER_EMAIL).lower()
        self.whitelist_domains = [d.lower() for d in (whitelist_domains or WHITELIST_DOMAINS)]

    def classify(self, email: EmailMessage) -> ClassificationResult:
        """
        Classify an email using rules.

        Args:
            email: EmailMessage to classify

        Returns:
            ClassificationResult with priority and reasoning
        """
        sender_email = email.sender_email.lower()
        sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""

        # === HIGH PRIORITY RULES ===

        # Rule 1: Self-sent emails
        if sender_email == self.user_email:
            return ClassificationResult(
                priority=Priority.HIGH,
                method="rule",
                rule_name="self_sent",
                reason="Email sent from your own address",
            )

        # Rule 2: Whitelisted business domains
        if sender_domain in self.whitelist_domains:
            return ClassificationResult(
                priority=Priority.HIGH,
                method="rule",
                rule_name="whitelist_domain",
                reason=f"Sender domain {sender_domain} is whitelisted",
            )

        # Rule 3: High priority keywords in subject/body
        has_keywords, keyword_pattern = has_high_priority_keywords(
            email.subject, email.snippet
        )
        if has_keywords:
            return ClassificationResult(
                priority=Priority.HIGH,
                method="rule",
                rule_name="high_priority_keyword",
                reason=f"Contains keyword pattern: {keyword_pattern}",
            )

        # Rule 4: Direct personal email (single recipient, no unsubscribe)
        if (
            len(email.to) == 1
            and not email.has_unsubscribe
            and "CATEGORY_PERSONAL" in email.label_ids
        ):
            return ClassificationResult(
                priority=Priority.HIGH,
                method="rule",
                rule_name="personal_direct",
                reason="Direct personal email without unsubscribe",
            )

        # === LOW PRIORITY RULES ===

        # Rule 5: Has List-Unsubscribe header (strong newsletter signal)
        if email.has_unsubscribe:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="has_unsubscribe",
                confidence=0.9,
                reason="Email has List-Unsubscribe header (newsletter/marketing)",
            )

        # Rule 6: Low priority sender patterns (noreply, newsletter, etc.)
        is_low_sender, sender_pattern = is_low_priority_sender(sender_email)
        if is_low_sender:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="low_priority_sender",
                confidence=0.85,
                reason=f"Sender matches pattern: {sender_pattern}",
            )

        # Rule 7: Automated notification services
        is_automated, auto_pattern = is_automated_notification(sender_email)
        if is_automated:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="automated_notification",
                confidence=0.8,
                reason=f"Automated notification from: {auto_pattern}",
            )

        # Rule 8: Gmail promotion/social categories (as supporting signal)
        if "CATEGORY_PROMOTIONS" in email.label_ids:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="gmail_promotions",
                confidence=0.75,
                reason="Gmail categorized as promotion",
            )

        if "CATEGORY_SOCIAL" in email.label_ids:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="gmail_social",
                confidence=0.7,
                reason="Gmail categorized as social",
            )

        # Rule 9: Low priority subject patterns
        is_low_subject, subject_pattern = is_low_priority_subject(email.subject)
        if is_low_subject:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="low_priority_subject",
                confidence=0.75,
                reason=f"Subject matches pattern: {subject_pattern}",
            )

        # Rule 10: Gmail updates category
        if "CATEGORY_UPDATES" in email.label_ids:
            return ClassificationResult(
                priority=Priority.LOW,
                method="rule",
                rule_name="gmail_updates",
                confidence=0.6,
                reason="Gmail categorized as updates",
            )

        # === UNCERTAIN ===
        # No clear rule matched
        return ClassificationResult(
            priority=Priority.UNCERTAIN,
            method="rule",
            rule_name="no_match",
            confidence=0.5,
            reason="No clear classification rule matched",
        )
