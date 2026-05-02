"""Sender-grouped review commands.

Workflow:
1. `senders` — group all unread emails by sender, print top N, save cache.
2. `mark-sender-read` — given sender emails (or list-numbers from the cache),
   bulk-mark every unread message from those senders as read. All actions
   are recorded so `undo last` reverses them.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import click

from config import DATA_DIR
from db.repository import Repository
from gmail.client import EmailMessage, GmailClient


SENDERS_CACHE = Path(DATA_DIR) / "senders_cache.json"


@dataclass
class SenderGroup:
    rank: int
    email: str
    display: str
    count: int
    sample_subjects: list[str]
    message_ids: list[str]


def _normalize_sender(addr: str) -> str:
    return (addr or "unknown@unknown.com").strip().lower()


def _group_unread_by_sender(gmail: GmailClient, progress: bool = True) -> list[SenderGroup]:
    """Stream unread inbox, group by sender_email, return groups sorted by count desc."""
    groups: dict[str, dict] = defaultdict(lambda: {
        "display": "",
        "count": 0,
        "sample_subjects": [],
        "message_ids": [],
    })

    fetched = 0
    last_print = 0
    for email in gmail.iter_inbox_messages(include_read=False):
        sender = _normalize_sender(email.sender_email)
        g = groups[sender]
        if not g["display"]:
            g["display"] = email.sender or sender
        g["count"] += 1
        g["message_ids"].append(email.message_id)
        if len(g["sample_subjects"]) < 3 and email.subject:
            g["sample_subjects"].append(email.subject)
        fetched += 1
        if progress and fetched - last_print >= 100:
            click.echo(f"  ... fetched {fetched} emails", err=True)
            last_print = fetched

    if progress:
        click.echo(f"  ... fetched {fetched} emails total", err=True)

    ranked = sorted(groups.items(), key=lambda kv: kv[1]["count"], reverse=True)
    return [
        SenderGroup(
            rank=i,
            email=email,
            display=data["display"],
            count=data["count"],
            sample_subjects=data["sample_subjects"],
            message_ids=data["message_ids"],
        )
        for i, (email, data) in enumerate(ranked, start=1)
    ]


def _save_cache(senders: list[SenderGroup]) -> None:
    SENDERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_unread": sum(s.count for s in senders),
        "total_senders": len(senders),
        "senders": [asdict(s) for s in senders],
    }
    SENDERS_CACHE.write_text(json.dumps(payload, indent=2))


def _load_cache() -> Optional[dict]:
    if not SENDERS_CACHE.exists():
        return None
    try:
        return json.loads(SENDERS_CACHE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_senders(
    limit: int = 100,
    min_count: int = 1,
    refresh: bool = False,
) -> list[SenderGroup]:
    """Print top unread senders. Reuses the cache unless --refresh is passed."""
    cache = None if refresh else _load_cache()

    if cache:
        click.echo(f"Loaded cache from {SENDERS_CACHE} (generated {cache['generated_at']})")
        click.echo(f"  {cache['total_unread']} unread emails across {cache['total_senders']} senders")
        senders = [SenderGroup(**s) for s in cache["senders"]]
    else:
        click.echo("Fetching unread inbox (batched)...")
        gmail = GmailClient()
        senders = _group_unread_by_sender(gmail, progress=True)
        _save_cache(senders)
        click.echo(f"Cached {len(senders)} senders to {SENDERS_CACHE}")

    filtered = [s for s in senders if s.count >= min_count]
    shown = filtered[:limit]

    click.echo()
    click.echo(f"Top {len(shown)} senders by unread count (min={min_count}):")
    click.echo("=" * 70)
    for s in shown:
        click.echo(f"[{s.rank:>4}] {s.count:>4}  {s.email}")
        for subj in s.sample_subjects:
            click.echo(f"           • {subj[:80]}")
    click.echo("=" * 70)
    click.echo(f"Showing {len(shown)} of {len(filtered)} matching senders ({len(senders)} total)")
    click.echo()
    click.echo("Next: pick the senders you want to bulk-mark as read, then run:")
    click.echo("  python3 main.py mark-sender-read sender@example.com other@x.com ...")
    click.echo("  python3 main.py mark-sender-read --rank 1,3,5-8")
    click.echo("Add --dry-run to preview, or run without to apply.")

    return shown


_RANK_RE = re.compile(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*")


def _parse_rank_spec(spec: str) -> list[int]:
    ranks: set[int] = set()
    for part in spec.split(","):
        if not part.strip():
            continue
        m = _RANK_RE.fullmatch(part)
        if not m:
            raise click.BadParameter(f"Invalid rank spec: {part!r} (use numbers like '1,3,5-8')")
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if end < start:
            start, end = end, start
        ranks.update(range(start, end + 1))
    return sorted(ranks)


def mark_sender_read(
    sender_emails: Iterable[str] = (),
    ranks: Iterable[int] = (),
    dry_run: bool = False,
    yes: bool = False,
    allow_self_sent: bool = False,
) -> dict:
    """Mark all unread inbox messages from the given senders as read."""
    from config import USER_EMAIL

    cache = _load_cache()
    if not cache:
        raise click.ClickException(
            "No senders cache found. Run `python3 main.py senders` first to generate it."
        )

    by_email: dict[str, dict] = {s["email"]: s for s in cache["senders"]}
    by_rank: dict[int, dict] = {s["rank"]: s for s in cache["senders"]}

    selected: dict[str, dict] = {}
    user = (USER_EMAIL or "").strip().lower()

    for raw in sender_emails:
        key = _normalize_sender(raw)
        if key not in by_email:
            click.echo(f"  warning: {raw!r} not found in cache, skipping", err=True)
            continue
        selected[key] = by_email[key]

    for rank in ranks:
        if rank not in by_rank:
            click.echo(f"  warning: rank {rank} not in cache, skipping", err=True)
            continue
        s = by_rank[rank]
        selected[s["email"]] = s

    if not selected:
        raise click.ClickException("No valid senders selected.")

    if user and user in selected and not allow_self_sent:
        raise click.ClickException(
            f"Refusing to bulk-mark self-sent emails ({user}) as read. "
            f"These need to be either addressed or explicitly marked as reviewed. "
            f"Use the webapp (`python3 main.py serve`) to review them, "
            f"or pass --allow-self-sent to override."
        )

    total = sum(s["count"] for s in selected.values())
    click.echo()
    click.echo(f"Will mark {total} emails as read across {len(selected)} senders:")
    for s in sorted(selected.values(), key=lambda x: -x["count"]):
        click.echo(f"  {s['count']:>4}  {s['email']}")
    click.echo()

    if dry_run:
        click.echo("[DRY RUN] no changes made")
        return {"total": total, "senders": len(selected), "dry_run": True}

    if not yes and not click.confirm(f"Mark {total} emails as read?", default=False):
        click.echo("Cancelled.")
        return {"total": 0, "senders": 0, "cancelled": True}

    gmail = GmailClient()
    repo = Repository()
    run = repo.create_run()

    marked = 0
    errors = 0
    for s in selected.values():
        sender_email = s["email"]
        for mid in s["message_ids"]:
            try:
                gmail.mark_as_read(mid)
                repo.record_action(
                    message_id=mid,
                    thread_id="",
                    action_type="mark_read",
                    label_name="UNREAD",
                    original_labels=["UNREAD"],
                    classification_method="sender_bulk",
                    classification_rule="bulk_mark_sender_read",
                    classification_reason=f"Bulk-marked from sender {sender_email}",
                    confidence=1.0,
                    sender=sender_email,
                    subject="(bulk)",
                    run_id=run.id,
                )
                marked += 1
                if marked % 50 == 0:
                    click.echo(f"  ... marked {marked}/{total}", err=True)
            except Exception as e:
                errors += 1
                click.echo(f"  error marking {mid}: {e}", err=True)

    run.completed_at = datetime.now()
    run.emails_processed = marked
    run.low_priority = marked
    run.errors = errors
    run.status = "completed"
    repo.update_run(run)

    click.echo()
    click.echo(f"Marked {marked} emails as read (errors: {errors})")
    click.echo(f"Run ID: {run.id} (use `python3 main.py undo run {run.id}` to reverse)")

    return {"total": marked, "senders": len(selected), "errors": errors, "run_id": run.id}
