#!/usr/bin/env python3
"""
Email Triage CLI - Intelligent email prioritization for Gmail.

Classifies emails as high or low priority and labels low-priority
emails for easier inbox management. All actions are reversible.
"""
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import click

from config import USER_EMAIL, ANTHROPIC_API_KEY, LOW_PRIORITY_LABEL


def _ensure_user_email_set(ctx):
    """Skip-friendly check that USER_EMAIL is configured before any Gmail action."""
    if ctx.invoked_subcommand in (None, "config"):
        return
    if "--help" in sys.argv or "-h" in sys.argv:
        return
    if not USER_EMAIL:
        click.echo(
            "USER_EMAIL is not set. Copy .env.example to .env and set USER_EMAIL "
            "to your Gmail address.",
            err=True,
        )
        sys.exit(2)


@click.group()
@click.version_option(version="1.0.0")
@click.pass_context
def cli(ctx):
    """Email Triage - Intelligent email prioritization for Gmail.

    Classifies emails and labels low-priority ones for easier inbox management.
    All actions are tracked and can be undone.
    """
    _ensure_user_email_set(ctx)


@cli.command()
def auth():
    """Authenticate with Gmail API.

    On first run, opens a browser for OAuth consent.
    Credentials are stored for subsequent runs.
    """
    from gmail.auth import verify_auth

    click.echo("Verifying Gmail authentication...")
    if verify_auth():
        click.echo("\nAuthentication successful!")
    else:
        click.echo("\nAuthentication failed. Check the error above.", err=True)
        sys.exit(1)


@cli.command()
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them")
@click.option("--all", "include_read", is_flag=True, help="Include read emails (default: unread only)")
@click.option("--limit", type=int, help="Maximum number of emails to process")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--mark-read", "mark_read", is_flag=True, help="Also mark low-priority emails as read")
def triage(dry_run: bool, include_read: bool, limit: int, verbose: bool, mark_read: bool):
    """Classify and label low-priority emails.

    By default, only processes unread emails in your inbox.
    Low-priority emails get the 'LowPriority' label added.

    Examples:
        email-triage triage                # Process unread inbox
        email-triage triage --dry-run      # Preview without changes
        email-triage triage --all          # Include read emails
        email-triage triage --limit 10     # Process max 10 emails
        email-triage triage --mark-read    # Also mark low-priority as read
    """
    from commands.triage import run_triage

    click.echo(f"User: {USER_EMAIL}")
    click.echo(f"Label: {LOW_PRIORITY_LABEL}")
    click.echo(f"AI enabled: {'Yes' if ANTHROPIC_API_KEY else 'No (rule-based only)'}")
    if mark_read:
        click.echo(f"Mark-read: ON (low-priority emails will be marked as read)")
    click.echo()

    run_triage(
        dry_run=dry_run,
        include_read=include_read,
        limit=limit,
        verbose=verbose,
        mark_read=mark_read,
    )


@cli.group()
def undo():
    """Undo triage actions.

    Reverse label changes made by previous triage runs.
    """
    pass


@undo.command("last")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
def undo_last(verbose: bool):
    """Undo the most recent triage run."""
    from commands.undo import undo_last_run

    undo_last_run(verbose=verbose)


@undo.command("run")
@click.argument("run_id", type=int)
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
def undo_run_cmd(run_id: int, verbose: bool):
    """Undo a specific triage run by ID."""
    from commands.undo import undo_run

    undo_run(run_id, verbose=verbose)


@undo.command("all")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
def undo_all_cmd(verbose: bool):
    """Undo ALL triage actions ever recorded.

    This will remove LowPriority labels from all emails that
    were previously labeled by this tool.
    """
    from commands.undo import undo_all

    undo_all(verbose=verbose)


@undo.command("message")
@click.argument("message_id")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
def undo_message_cmd(message_id: str, verbose: bool):
    """Undo triage for a specific email by message ID."""
    from commands.undo import undo_message

    undo_message(message_id, verbose=verbose)


@cli.command()
@click.option("--host", default=None, help="Override the bind host (default: WEBAPP_HOST or 127.0.0.1)")
@click.option("--port", type=int, default=None, help="Override the bind port (default: WEBAPP_PORT or 8765)")
@click.option("--debug", is_flag=True, help="Run Flask in debug mode (auto-reload)")
def serve(host: str, port: int, debug: bool):
    """Launch the bulk-review webapp on localhost.

    Open the printed URL in your browser. Two-pane UI:
    senders on the left, messages on the right.
    Self-sent senders are flagged and protected from auto mark-read.
    """
    from webapp.app import serve as serve_app
    serve_app(host=host, port=port, debug=debug)


@cli.command()
@click.option("--limit", type=int, default=100, show_default=True, help="Max senders to print")
@click.option("--min", "min_count", type=int, default=1, show_default=True, help="Only show senders with at least this many unread")
@click.option("--refresh", is_flag=True, help="Re-fetch from Gmail (ignore cached results)")
def senders(limit: int, min_count: int, refresh: bool):
    """Group unread inbox by sender, sorted by count.

    Saves a cache so `mark-sender-read` can act on the same data without re-fetching.
    """
    from commands.senders import list_senders
    list_senders(limit=limit, min_count=min_count, refresh=refresh)


@cli.command("mark-sender-read")
@click.argument("sender_emails", nargs=-1)
@click.option("--rank", "rank_spec", help="Pick by rank from `senders` output, e.g. '1,3,5-8'")
@click.option("--dry-run", is_flag=True, help="Preview without modifying anything")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt")
@click.option("--allow-self-sent", is_flag=True, help="Override the self-sent safety guard")
def mark_sender_read_cmd(sender_emails: tuple[str, ...], rank_spec: str, dry_run: bool, yes: bool, allow_self_sent: bool):
    """Mark all unread emails from the given senders as read.

    Senders can be specified as email addresses or by rank from the latest
    `senders` listing. All actions are recorded and reversible via
    `python3 main.py undo last`.

    Examples:
        python3 main.py mark-sender-read noreply@x.com other@y.com
        python3 main.py mark-sender-read --rank 1,3,5-8
        python3 main.py mark-sender-read --rank 1-20 --dry-run
    """
    from commands.senders import mark_sender_read, _parse_rank_spec
    ranks = _parse_rank_spec(rank_spec) if rank_spec else []
    if not sender_emails and not ranks:
        raise click.UsageError("Provide at least one sender email or use --rank.")
    mark_sender_read(
        sender_emails=sender_emails,
        ranks=ranks,
        dry_run=dry_run,
        yes=yes,
        allow_self_sent=allow_self_sent,
    )


@cli.command()
@click.option("--run-id", type=int, help="Show details for a specific run")
def stats(run_id: int):
    """Show triage statistics.

    Displays overall statistics and recent triage runs.
    Use --run-id to see details for a specific run.
    """
    from commands.stats import show_stats, show_run_details

    if run_id:
        show_run_details(run_id)
    else:
        show_stats()


@cli.group()
def config():
    """View and manage configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    from config import (
        USER_EMAIL, WHITELIST_DOMAINS, LOW_PRIORITY_LABEL,
        CLIENT_SECRET_FILE, TOKEN_FILE, DATABASE_PATH, ANTHROPIC_API_KEY,
        HIGH_PRIORITY_KEYWORDS
    )

    click.echo("\nEmail Triage Configuration")
    click.echo("=" * 40)
    click.echo(f"\nUser email: {USER_EMAIL}")
    click.echo(f"Low priority label: {LOW_PRIORITY_LABEL}")
    click.echo(f"\nWhitelist domains: {', '.join(WHITELIST_DOMAINS) or '(none)'}")
    click.echo(f"High priority keywords: {', '.join(HIGH_PRIORITY_KEYWORDS[:5])}...")
    click.echo(f"\nCredentials file: {CLIENT_SECRET_FILE}")
    click.echo(f"Token file: {TOKEN_FILE}")
    click.echo(f"Database: {DATABASE_PATH}")
    click.echo(f"AI enabled: {'Yes' if ANTHROPIC_API_KEY else 'No'}")
    click.echo()


if __name__ == "__main__":
    cli()
