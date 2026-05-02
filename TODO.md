# email-triage TODO

Project: Gmail inbox triage CLI + Flask webapp
Repo: https://github.com/samuelfrench/email-triage (public, MIT)

## Current state (2026-05-01)

- 3,615 unread inbox messages remaining (started at 3,707).
- 92 jobalerts-noreply@linkedin.com cleared via webapp mark-read.
- 320 actions recorded in `data/triage.db`, all reversible via `python3 main.py undo last`.
- Webapp + CLI both functional. Latest commit: `23cbe02`.

## Open

- [ ] Continue sender-grouped cleanup of remaining unread (top targets: messages-noreply@linkedin.com (57), updates-noreply@linkedin.com (39), notifications-noreply@linkedin.com (31), then other marketing senders).
- [ ] Decide on the 2,276 self-sent `[clawd-bot] Hourly Status Report` emails — webapp's "Mark Reviewed" applies the `Triaged-Reviewed` label so they're explicitly addressed.
- [ ] After cleanup, run `python3 main.py triage --mark-read` once for ongoing rule-based triage.

## Backlog (nice-to-have)

- [ ] Persistent job history (currently in-memory only; lost on webapp restart).
- [ ] Per-message preview pane (currently subject + snippet only).
- [ ] Auto-cleanup task: cron / systemd unit that re-runs `triage --mark-read` daily.
- [ ] Add a "filter senders by domain" affordance in the webapp.
- [ ] Replace global Gmail-API lock with per-thread `GmailClient` if concurrency becomes a bottleneck.

## Done this session

- Built CLI: `triage`, `senders`, `mark-sender-read`, `serve`, `undo`, `stats`.
- Built Flask webapp: two-pane review UI, self-sent guard, bulk actions with progress bar.
- Batched Gmail fetches with retry on rate limits + BatchError + SSL/connection errors.
- Thread-safe webapp (httplib2 lock).
- Live cache decrement on action success (no more stale counts).
- Debug log infrastructure (`data/webapp.log` + `/api/debug/logs` + frontend Debug panel).
- Published to public GitHub with PII / credential scrub.
