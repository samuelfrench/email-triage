"""Claude AI-based email classifier for uncertain cases."""
import json
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, AI_MODEL
from gmail.client import EmailMessage
from .rules import Priority, ClassificationResult


SYSTEM_PROMPT = """You are an email triage assistant helping to prioritize emails.

Classify emails as either HIGH or LOW priority based on these criteria:

HIGH PRIORITY - Keep prominently visible:
- Business inquiries, job opportunities, partnership requests
- Financial matters (invoices, payments, contracts)
- Personal communications from real people
- Urgent matters requiring action
- Important account notifications (security alerts, verification)
- Replies to conversations the user initiated

LOW PRIORITY - Can be reviewed later:
- Marketing emails and promotions
- Newsletters and digests
- Automated notifications (commits, CI builds, service updates)
- Social media notifications
- Retail promotions and sales
- Mass emails and mailing lists

Respond with ONLY valid JSON in this exact format:
{"priority": "high" or "low", "confidence": 0.0-1.0, "reason": "brief 1-sentence explanation"}

Be conservative: when truly uncertain, lean toward HIGH priority to avoid hiding important emails."""


class AIClassifier:
    """Uses Claude to classify emails that don't match clear rule patterns."""

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize AI classifier.

        Args:
            api_key: Anthropic API key. Defaults to config value.
            model: Model to use. Defaults to config value.
        """
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.model = model or AI_MODEL

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Add it to .env file or pass directly."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def classify(self, email: EmailMessage) -> ClassificationResult:
        """
        Classify an email using Claude.

        Args:
            email: EmailMessage to classify

        Returns:
            ClassificationResult with priority and reasoning
        """
        # Prepare email summary for classification
        email_text = f"""Sender: {email.sender}
Subject: {email.subject}
Preview: {email.snippet[:300]}
Has unsubscribe link: {email.has_unsubscribe}
Gmail categories: {', '.join(email.label_ids) if email.label_ids else 'none'}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": email_text}
                ],
            )

            # Parse response
            response_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            priority = Priority.HIGH if result["priority"] == "high" else Priority.LOW

            return ClassificationResult(
                priority=priority,
                method="ai",
                rule_name=None,
                confidence=result.get("confidence", 0.7),
                reason=result.get("reason", "AI classification"),
            )

        except json.JSONDecodeError as e:
            # If AI response isn't valid JSON, default to HIGH (conservative)
            return ClassificationResult(
                priority=Priority.HIGH,
                method="ai",
                rule_name="ai_parse_error",
                confidence=0.5,
                reason=f"AI response parse error, defaulting to high priority: {e}",
            )

        except anthropic.APIError as e:
            # On API error, default to HIGH (conservative)
            return ClassificationResult(
                priority=Priority.HIGH,
                method="ai",
                rule_name="ai_api_error",
                confidence=0.5,
                reason=f"AI API error, defaulting to high priority: {e}",
            )

    def is_available(self) -> bool:
        """Check if AI classification is available."""
        return bool(self.api_key)
