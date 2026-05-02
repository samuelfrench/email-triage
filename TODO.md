# email-triage TODO

Project: Gmail inbox triage CLI + Flask webapp
Repo: https://github.com/samuelfrench/email-triage (public, MIT)

## Current state (2026-05-02)

- 2,506 unread inbox messages remaining (down from 3,615).
- 1,094 `[clawd-bot] Hourly Status Report` self-sent reports labeled
  `Triaged-Reviewed` + read in run_id 7 (reversible: `python3 main.py undo run 7`).
- Top remaining sender is still self at 1,221 — non-clawd personal self-sent
  emails that must NOT be bulk-actioned.
- 1,414 actions recorded in `data/triage.db`, all reversible via `python3 main.py undo`.
- Webapp + CLI both functional.

## Open

- [ ] Continue sender-grouped cleanup of remaining unread (top non-self targets
      include marketing senders from `noreply@myarborhub.com`, `linkedin.com`,
      `google.com`, etc. — see webapp for current ranks).
- [ ] Manually review the 1,221 non-clawd self-sent emails — these are mixed
      personal mail; cannot be bulk-reviewed safely.
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
