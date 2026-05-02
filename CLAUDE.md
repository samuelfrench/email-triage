# email-triage — project notes for Claude

Read [TODO.md](TODO.md) at the start of every session.

## Quick orientation

- CLI entry: `main.py` (Click). Subcommands: `auth`, `triage`, `senders`,
  `mark-sender-read`, `serve` (webapp), `undo`, `stats`, `config show`.
- Webapp at `webapp/` (Flask). Single-page UI under `webapp/templates/index.html` +
  `webapp/static/{app.js,style.css}`. Run via `python3 main.py serve`
  (default http://127.0.0.1:8765).
- Persistent state: `data/triage.db` (SQLite), `data/senders_cache.json`,
  `data/webapp.log`. **All gitignored.**
- Secrets: `credentials/client_secret.json` + `credentials/token.json` and `.env`.
  **All gitignored.**

## Public on GitHub

- Repo: https://github.com/samuelfrench/email-triage (MIT, public).
- Anything committed will be publicly visible — re-run the PII audit before each push:
  `git diff --cached | grep -iE "samfrench|@gmail.com|sk-ant-|GOCSPX-|gho_|api03-|409984785198"`
  must return empty.

## Conventions

- Memory: `~/.claude/projects/-home-sam-claude-workspace-email-triage/memory/` —
  see `MEMORY.md` for index. Update `gmail-api.md` whenever a new Gmail-API
  gotcha is discovered.
- All Gmail mutations must record an action via `Repository.record_action`
  so `undo last` works.
- Bulk actions in the webapp must call `remove_message_ids_from_cache(succeeded_ids)`
  on completion — otherwise the senders list shows stale counts.
- httplib2 is not thread-safe — every Gmail API call from the webapp must go
  through `gmail_call(fn)` (holds the global lock). Don't bypass.
- Self-sent emails are never auto-marked-read; only the webapp's explicit
  "Mark Reviewed" action (which applies the `Triaged-Reviewed` label) is
  allowed against them.
