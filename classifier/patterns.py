"""Regex patterns for email classification."""
import re
from typing import Pattern

from config import (
    LOW_PRIORITY_SENDER_PATTERNS,
    LOW_PRIORITY_SUBJECT_PATTERNS,
    HIGH_PRIORITY_KEYWORDS,
)


def compile_patterns(patterns: list[str]) -> list[Pattern]:
    """Compile a list of regex patterns."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Compiled patterns
LOW_PRIORITY_SENDER_RE = compile_patterns(LOW_PRIORITY_SENDER_PATTERNS)
LOW_PRIORITY_SUBJECT_RE = compile_patterns(LOW_PRIORITY_SUBJECT_PATTERNS)
HIGH_PRIORITY_KEYWORDS_RE = compile_patterns([rf"\b{kw}\b" for kw in HIGH_PRIORITY_KEYWORDS])

# Additional patterns for automated notifications
AUTOMATED_NOTIFICATION_PATTERNS = compile_patterns([
    r"github\.com",
    r"gitlab\.com",
    r"bitbucket\.org",
    r"jira",
    r"confluence",
    r"slack",
    r"trello",
    r"asana",
    r"notion\.so",
    r"linear\.app",
    r"circleci",
    r"travis-ci",
    r"jenkins",
    r"vercel",
    r"netlify",
    r"heroku",
    r"aws\.amazon\.com",
    r"cloud\.google\.com",
    r"azure\.microsoft\.com",
])

# Marketing / promotional patterns
MARKETING_SUBJECT_PATTERNS = compile_patterns([
    r"free shipping",
    r"act now",
    r"limited offer",
    r"exclusive deal",
    r"save \d+%",
    r"flash sale",
    r"clearance",
    r"buy one get one",
    r"bogo",
    r"reward points",
    r"your \w+ is waiting",
    r"we miss you",
    r"come back",
])


def matches_any(text: str, patterns: list[Pattern]) -> tuple[bool, str | None]:
    """
    Check if text matches any of the patterns.

    Args:
        text: Text to check
        patterns: List of compiled regex patterns

    Returns:
        Tuple of (matched, pattern_string or None)
    """
    for pattern in patterns:
        if pattern.search(text):
            return True, pattern.pattern
    return False, None


def is_low_priority_sender(sender_email: str) -> tuple[bool, str | None]:
    """Check if sender matches low priority patterns."""
    return matches_any(sender_email, LOW_PRIORITY_SENDER_RE)


def is_low_priority_subject(subject: str) -> tuple[bool, str | None]:
    """Check if subject matches low priority patterns."""
    matched, pattern = matches_any(subject, LOW_PRIORITY_SUBJECT_RE)
    if matched:
        return True, pattern
    return matches_any(subject, MARKETING_SUBJECT_PATTERNS)


def is_automated_notification(sender_email: str) -> tuple[bool, str | None]:
    """Check if sender is from an automated notification service."""
    return matches_any(sender_email, AUTOMATED_NOTIFICATION_PATTERNS)


def has_high_priority_keywords(subject: str, snippet: str) -> tuple[bool, str | None]:
    """Check if email contains high priority keywords."""
    text = f"{subject} {snippet}"
    return matches_any(text, HIGH_PRIORITY_KEYWORDS_RE)
