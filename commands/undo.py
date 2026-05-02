"""Undo command - reverse triage actions."""
from typing import Optional

import click

from config import LOW_PRIORITY_LABEL
from gmail.client import GmailClient
from db.repository import Repository


def undo_last_run(verbose: bool = False) -> int:
    """
    Undo all actions from the most recent triage run.

    Returns:
        Number of actions undone
    """
    repo = Repository()
    gmail = GmailClient()

    last_run = repo.get_last_run()
    if not last_run:
        click.echo("No triage runs found.")
        return 0

    return undo_run(last_run.id, verbose=verbose)


def undo_run(run_id: int, verbose: bool = False) -> int:
    """
    Undo all actions from a specific triage run.

    Args:
        run_id: ID of the triage run to undo
        verbose: If True, print detailed output

    Returns:
        Number of actions undone
    """
    repo = Repository()
    gmail = GmailClient()

    run = repo.get_run_by_id(run_id)
    if not run:
        click.echo(f"Run {run_id} not found.")
        return 0

    actions = repo.get_actions_for_run(run_id)
    if not actions:
        click.echo(f"No actions to undo for run {run_id}.")
        return 0

    click.echo(f"Undoing {len(actions)} actions from run {run_id}...")

    undone = 0
    errors = 0

    for action in actions:
        try:
            if action.action_type == "add_label":
                # Remove the label we added
                gmail.remove_label(action.message_id, action.label_name)
                if verbose:
                    click.echo(f"  Removed label from: {action.subject[:50]}")
            elif action.action_type == "remove_label":
                # Re-add the label we removed
                gmail.add_label(action.message_id, action.label_name)
                if verbose:
                    click.echo(f"  Restored label to: {action.subject[:50]}")
            elif action.action_type == "mark_read":
                # Mark as unread again
                gmail.mark_as_unread(action.message_id)
                if verbose:
                    click.echo(f"  Marked as unread: {action.subject[:50]}")

            repo.mark_action_undone(action.id)
            undone += 1

        except Exception as e:
            errors += 1
            if verbose:
                click.echo(f"  ERROR undoing {action.message_id}: {e}", err=True)

    click.echo(f"Undone: {undone} actions")
    if errors:
        click.echo(f"Errors: {errors}")

    return undone


def undo_all(verbose: bool = False) -> int:
    """
    Undo all triage actions ever recorded.

    Returns:
        Number of actions undone
    """
    repo = Repository()
    gmail = GmailClient()

    actions = repo.get_all_pending_actions()
    if not actions:
        click.echo("No actions to undo.")
        return 0

    if not click.confirm(f"This will undo {len(actions)} actions. Continue?"):
        click.echo("Cancelled.")
        return 0

    click.echo(f"Undoing {len(actions)} actions...")

    undone = 0
    errors = 0

    for action in actions:
        try:
            if action.action_type == "add_label":
                gmail.remove_label(action.message_id, action.label_name)
            elif action.action_type == "remove_label":
                gmail.add_label(action.message_id, action.label_name)
            elif action.action_type == "mark_read":
                gmail.mark_as_unread(action.message_id)

            repo.mark_action_undone(action.id)
            undone += 1

            if verbose:
                click.echo(f"  Undone: {action.subject[:50]}")

        except Exception as e:
            errors += 1
            if verbose:
                click.echo(f"  ERROR: {e}", err=True)

    click.echo(f"Undone: {undone} actions")
    if errors:
        click.echo(f"Errors: {errors}")

    return undone


def undo_message(message_id: str, verbose: bool = False) -> bool:
    """
    Undo triage for a specific message.

    Args:
        message_id: Gmail message ID
        verbose: If True, print detailed output

    Returns:
        True if action was undone
    """
    repo = Repository()
    gmail = GmailClient()

    action = repo.get_action_by_message_id(message_id)
    if not action:
        click.echo(f"No pending action found for message {message_id}.")
        return False

    try:
        if action.action_type == "add_label":
            gmail.remove_label(action.message_id, action.label_name)
        elif action.action_type == "remove_label":
            gmail.add_label(action.message_id, action.label_name)
        elif action.action_type == "mark_read":
            gmail.mark_as_unread(action.message_id)

        repo.mark_action_undone(action.id)

        click.echo(f"Undone action for: {action.subject[:50]}")
        return True

    except Exception as e:
        click.echo(f"Error undoing action: {e}", err=True)
        return False
