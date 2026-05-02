"""Stats command - display triage statistics."""
import click

from db.repository import Repository


def show_stats():
    """Display overall triage statistics."""
    repo = Repository()

    stats = repo.get_stats()
    runs = repo.get_all_runs(limit=10)

    click.echo("\n" + "=" * 60)
    click.echo("Email Triage Statistics")
    click.echo("=" * 60 + "\n")

    click.echo(f"Total triage runs: {stats['total_runs']}")
    click.echo(f"Total emails labeled: {stats['total_actions']}")

    if stats["by_method"]:
        click.echo("\nClassification methods:")
        for method, count in stats["by_method"].items():
            click.echo(f"  {method}: {count}")

    if stats["top_rules"]:
        click.echo("\nTop rules triggered:")
        for rule, count in stats["top_rules"].items():
            click.echo(f"  {rule}: {count}")

    if runs:
        click.echo("\nRecent runs:")
        click.echo("-" * 60)
        click.echo(f"{'ID':<6} {'Date':<20} {'Processed':<10} {'Low':<6} {'High':<6} {'AI':<4}")
        click.echo("-" * 60)

        for run in runs:
            date_str = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "N/A"
            click.echo(
                f"{run.id:<6} {date_str:<20} {run.emails_processed:<10} "
                f"{run.low_priority:<6} {run.high_priority:<6} {run.ai_calls:<4}"
            )

    click.echo()


def show_run_details(run_id: int):
    """Display details for a specific triage run."""
    repo = Repository()

    run = repo.get_run_by_id(run_id)
    if not run:
        click.echo(f"Run {run_id} not found.")
        return

    actions = repo.get_actions_for_run(run_id)

    click.echo("\n" + "=" * 60)
    click.echo(f"Triage Run #{run.id}")
    click.echo("=" * 60 + "\n")

    click.echo(f"Started: {run.started_at}")
    click.echo(f"Completed: {run.completed_at}")
    click.echo(f"Status: {run.status}")
    click.echo(f"\nProcessed: {run.emails_processed}")
    click.echo(f"  High priority: {run.high_priority}")
    click.echo(f"  Low priority: {run.low_priority}")
    click.echo(f"  Uncertain: {run.uncertain}")
    click.echo(f"  AI calls: {run.ai_calls}")
    click.echo(f"  Errors: {run.errors}")

    if actions:
        click.echo(f"\nActions ({len(actions)} emails labeled):")
        click.echo("-" * 60)

        for action in actions[:20]:  # Limit to 20
            status = "UNDONE" if action.undone_at else "active"
            click.echo(f"\n  [{status}] {action.subject[:50]}")
            click.echo(f"    From: {action.sender[:40]}")
            click.echo(f"    Method: {action.classification_method}")
            if action.classification_rule:
                click.echo(f"    Rule: {action.classification_rule}")
            if action.classification_reason:
                click.echo(f"    Reason: {action.classification_reason}")

        if len(actions) > 20:
            click.echo(f"\n  ... and {len(actions) - 20} more")

    click.echo()
