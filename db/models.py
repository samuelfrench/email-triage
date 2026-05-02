"""Data models for triage tracking."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json


@dataclass
class TriageAction:
    """Represents a single triage action on an email."""
    id: Optional[int]
    message_id: str
    thread_id: str
    action_type: str  # 'add_label' | 'remove_label'
    label_name: str
    original_labels: list[str]
    classification_method: str  # 'rule' | 'ai'
    classification_rule: Optional[str]
    classification_reason: Optional[str]
    confidence: float
    sender: str
    subject: str
    created_at: datetime
    undone_at: Optional[datetime]
    run_id: Optional[int]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "action_type": self.action_type,
            "label_name": self.label_name,
            "original_labels": self.original_labels,
            "classification_method": self.classification_method,
            "classification_rule": self.classification_rule,
            "classification_reason": self.classification_reason,
            "confidence": self.confidence,
            "sender": self.sender,
            "subject": self.subject,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "undone_at": self.undone_at.isoformat() if self.undone_at else None,
            "run_id": self.run_id,
        }


@dataclass
class TriageRun:
    """Represents a single triage execution run."""
    id: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]
    emails_processed: int
    high_priority: int
    low_priority: int
    uncertain: int
    ai_calls: int
    errors: int
    status: str  # 'running' | 'completed' | 'failed'

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "emails_processed": self.emails_processed,
            "high_priority": self.high_priority,
            "low_priority": self.low_priority,
            "uncertain": self.uncertain,
            "ai_calls": self.ai_calls,
            "errors": self.errors,
            "status": self.status,
        }
