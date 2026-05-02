"""Triage command - main email classification logic."""
from datetime import datetime
from typing import Optional

import click

from config import LOW_PRIORITY_LABEL, ANTHROPIC_API_KEY
from gmail.client import GmailClient, EmailMessage
from classifier.rules import RuleClassifier, Priority, ClassificationResult
from classifier.ai_classifier import AIClassifier
from db.repository import Repository


def run_triage(
    dry_run: bool = False,
    include_read: bool = False,
    limit: Optional[int] = None,
    verbose: bool = False,
    mark_read: bool = False,
) -> dict:
    """
    Run the email triage process.

    Args:
        dry_run: If True, don't actually modify emails
        include_read: If True, also process read emails
        limit: Maximum number of emails to process
        verbose: If True, print detailed output
        mark_read: If True, also mark low-priority emails as read

    Returns:
        Dictionary with statistics
    """
    # Initialize components
    gmail = GmailClient()
    rule_classifier = RuleClassifier()
    ai_classifier = AIClassifier() if ANTHROPIC_API_KEY else None
    repo = Repository()

    # Create triage run record
    run = repo.create_run()

    stats = {
        "processed": 0,
        "high_priority": 0,
        "low_priority": 0,
        "uncertain": 0,
        "ai_calls": 0,
        "errors": 0,
        "skipped_already_labeled": 0,
        "marked_read": 0,
    }

    if verbose:
        mode = "DRY RUN" if dry_run else "LIVE"
        click.echo(f"\n{'='*60}")
        click.echo(f"Email Triage - {mode}")
        click.echo(f"{'='*60}\n")

    try:
        # Get inbox messages
        if verbose:
            click.echo("Fetching inbox messages...")

        count = 0
        for email in gmail.iter_inbox_messages(include_read=include_read):
            if limit and count >= limit:
                break

            count += 1
            stats["processed"] += 1

            try:
                result = process_email(
                    email=email,
                    gmail=gmail,
                    rule_classifier=rule_classifier,
                    ai_classifier=ai_classifier,
                    repo=repo,
                    run_id=run.id,
                    dry_run=dry_run,
                    verbose=verbose,
                    stats=stats,
                    mark_read=mark_read,
                )

                # Update stats based on result
                if result:
                    if result.priority == Priority.HIGH:
                        stats["high_priority"] += 1
                    elif result.priority == Priority.LOW:
                        stats["low_priority"] += 1
                    else:
                        stats["uncertain"] += 1

                    if result.method == "ai":
                        stats["ai_calls"] += 1

            except Exception as e:
                stats["errors"] += 1
                if verbose:
                    click.echo(f"  ERROR: {e}", err=True)

        # Update run record
        run.completed_at = datetime.now()
        run.emails_processed = stats["processed"]
        run.high_priority = stats["high_priority"]
        run.low_priority = stats["low_priority"]
        run.uncertain = stats["uncertain"]
        run.ai_calls = stats["ai_calls"]
        run.errors = stats["errors"]
        run.status = "completed"
        repo.update_run(run)

    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now()
        repo.update_run(run)
        raise

    # Print summary
    if verbose:
        click.echo(f"\n{'='*60}")
        click.echo("Summary")
        click.echo(f"{'='*60}")

    click.echo(f"Processed: {stats['processed']} emails")
    click.echo(f"  High priority: {stats['high_priority']}")
    click.echo(f"  Low priority: {stats['low_priority']} {'(labeled)' if not dry_run else '(would be labeled)'}")
    click.echo(f"  Uncertain: {stats['uncertain']}")
    click.echo(f"  AI calls: {stats['ai_calls']}")
    click.echo(f"  Errors: {stats['errors']}")
    click.echo(f"  Already labeled: {stats['skipped_already_labeled']}")
    if mark_read:
        click.echo(f"  Marked as read: {stats['marked_read']} {'' if not dry_run else '(would be marked)'}")

    if dry_run:
        click.echo("\n[DRY RUN - no changes made]")
    else:
        click.echo(f"\nRun ID: {run.id} (use 'undo --run-id {run.id}' to reverse)")

    return stats


def process_email(
    email: EmailMessage,
    gmail: GmailClient,
    rule_classifier: RuleClassifier,
    ai_classifier: Optional[AIClassifier],
    repo: Repository,
    run_id: int,
    dry_run: bool,
    verbose: bool,
    stats: dict,
    mark_read: bool = False,
) -> Optional[ClassificationResult]:
    """
    Process a single email.

    Returns:
        ClassificationResult or None if skipped
    """
    # Check if already has LowPriority label
    label_id = gmail.label_manager.get_label_id(LOW_PRIORITY_LABEL)
    if label_id and label_id in email.label_ids:
        stats["skipped_already_labeled"] += 1
        if verbose:
            click.echo(f"  SKIP: {email.subject[:50]} (already labeled)")
        return None

    # Classify with rules first
    result = rule_classifier.classify(email)

    # If uncertain and AI available, use AI
    if result.priority == Priority.UNCERTAIN and ai_classifier:
        result = ai_classifier.classify(email)

    # Print classification
    if verbose:
        priority_str = result.priority.name
        prefix = "  " if result.priority == Priority.HIGH else "  >> "
        click.echo(f"{prefix}[{priority_str}] {email.subject[:50]}")
        if result.reason:
            click.echo(f"       Reason: {result.reason}")

    # Apply label if low priority
    if result.priority == Priority.LOW:
        original_labels = email.label_ids.copy()
        was_unread = "UNREAD" in original_labels

        if not dry_run:
            gmail.add_label(email.message_id, LOW_PRIORITY_LABEL)

            repo.record_action(
                message_id=email.message_id,
                thread_id=email.thread_id,
                action_type="add_label",
                label_name=LOW_PRIORITY_LABEL,
                original_labels=original_labels,
                classification_method=result.method,
                classification_rule=result.rule_name,
                classification_reason=result.reason,
                confidence=result.confidence,
                sender=email.sender,
                subject=email.subject,
                run_id=run_id,
            )

        if mark_read and was_unread:
            stats["marked_read"] += 1
            if not dry_run:
                gmail.mark_as_read(email.message_id)
                repo.record_action(
                    message_id=email.message_id,
                    thread_id=email.thread_id,
                    action_type="mark_read",
                    label_name="UNREAD",
                    original_labels=original_labels,
                    classification_method=result.method,
                    classification_rule=result.rule_name,
                    classification_reason=result.reason,
                    confidence=result.confidence,
                    sender=email.sender,
                    subject=email.subject,
                    run_id=run_id,
                )

    return result
