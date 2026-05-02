"""Email classification logic."""
from .rules import RuleClassifier, Priority, ClassificationResult
from .ai_classifier import AIClassifier

__all__ = ["RuleClassifier", "AIClassifier", "Priority", "ClassificationResult"]
