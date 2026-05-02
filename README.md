# email-triage

A Gmail inbox triage CLI. Classifies unread email as high or low priority,
labels low-priority messages with a `LowPriority` Gmail label, and (optionally)
marks them as read. Also supports a sender-based bulk flow for cleaning up
inboxes that have piled up — list senders by unread count, pick the marketing
ones, mark them all as read in one shot.

Every action is recorded in a local SQLite DB and is fully reversible.

## Why

Gmail's built-in filters get you most of the way, but they require manual rule
setup and don't help when you already have thousands of unread emails. This
tool:

- Uses heuristic rules + (optional) Claude to classify what's worth reading.
- Groups remaining unread by sender so you can mark whole senders as read at
  once — the same workflow you'd do manually, but in seconds.
- Records every change so you can undo a run if the classification was wrong.

## Setup

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/email-triage.git
cd email-triage
pip install -r requirements.txt
```

Python 3.10+ recommended.

### 2. Create a Google Cloud project and enable the Gmail API

1. Go to https://console.cloud.google.com/ and create (or select) a project.
2. Enable the Gmail API:
   `APIs & Services` → `Library` → search "Gmail API" → `Enable`.
3. Configure the OAuth consent screen as **External**, **Testing** mode, and
   add your own Gmail address as a test user.
4. Create OAuth credentials:
   `APIs & Services` → `Credentials` → `Create Credentials` →
   `OAuth client ID` → application type **Desktop app**.
5. Download the JSON and save it as `credentials/client_secret.json`.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set USER_EMAIL. Optionally set ANTHROPIC_API_KEY.
```

### 4. Authenticate

```bash
python3 main.py auth
```

A browser will open for the OAuth consent flow. The token is saved to
`credentials/token.json` for future runs.

## Usage

### Classify and label low-priority emails

```bash
python3 main.py triage --dry-run            # preview
python3 main.py triage                      # apply LowPriority label
python3 main.py triage --mark-read          # also mark as read
python3 main.py triage --mark-read --limit 100   # cap how many to process
python3 main.py triage --all                # include already-read emails
```

The classifier uses rules first (List-Unsubscribe header, noreply senders,
Gmail's CATEGORY_PROMOTIONS, etc.). If a rule doesn't match and you have
`ANTHROPIC_API_KEY` set, it falls back to Claude. Without the API key, it
falls through to "uncertain" (no label applied).

### Webapp (recommended for cleanup at scale)

```bash
python3 main.py serve
# open http://127.0.0.1:8765
```

Two-pane review UI:

- **Left**: every sender with unread email, sorted by count, with sample subjects.
- **Right**: messages from the selected sender, with checkboxes and bulk actions.
- **Self-sent senders are flagged** with a warning and the auto mark-read
  buttons are disabled — these need to either be addressed or explicitly
  marked reviewed.

Actions:

- **Mark Read** — remove the `UNREAD` label.
- **Mark Reviewed (label + read)** — apply the `Triaged-Reviewed` label and
  mark as read. Use this for self-sent or anything you want to confirm you've
  actually looked at.
- **Apply LowPriority** — apply the rule-based `LowPriority` label without
  marking as read.

Every action goes through the same SQLite repository as the CLI, so
`python3 main.py undo last` reverses webapp actions too.

### Sender-based bulk cleanup (CLI)

For inboxes with thousands of unread, the rule-based pass won't catch
everything. Use the sender flow:

```bash
python3 main.py senders --limit 100         # group unread by sender, top 100
```

This prints something like:

```
[   1]  142  noreply@retailer.com
           • Last chance — 30% off ends tonight
           • New arrivals
           • ...
[   2]   89  notifications@some-saas.com
           • Your weekly summary
           • ...
```

Pick the senders you don't care about, then:

```bash
python3 main.py mark-sender-read --rank 1,2,5-10 --dry-run
python3 main.py mark-sender-read --rank 1,2,5-10
```

Or by email:

```bash
python3 main.py mark-sender-read noreply@retailer.com other@x.com
```

### Stats

```bash
python3 main.py stats                # overall totals
python3 main.py stats --run-id 5     # details for a specific run
```

### Undo

Every action is recorded in `data/triage.db` and reversible:

```bash
python3 main.py undo last                  # undo the most recent run
python3 main.py undo run 5                 # undo a specific run
python3 main.py undo message <message_id>  # undo a single message
python3 main.py undo all                   # undo every action ever recorded
```

### Configuration

```bash
python3 main.py config show
```

## How classification works

Rules are evaluated in order, first match wins:

1. **High priority**
   - Sent from your own address (calendar invites, notes-to-self)
   - Sender domain is in `WHITELIST_DOMAINS`
   - Subject/snippet contains keywords like "invoice", "interview", "deadline"
   - Single-recipient personal email with no unsubscribe header
2. **Low priority**
   - `List-Unsubscribe` header present
   - Sender matches `noreply@`, `newsletter@`, `notifications@`, etc.
   - Gmail categorized as Promotions / Social / Updates
   - Subject matches "X% off", "weekly digest", "sale ends", etc.
3. **Uncertain** → Claude (if `ANTHROPIC_API_KEY` is set), else no action.

Tweak the patterns in `config.py` to fit your inbox.

## Safety

- **Nothing is deleted or archived.** The tool only adds the `LowPriority`
  label and (optionally) removes the `UNREAD` system label.
- **Every action is recorded** in `data/triage.db` with the original label
  state, so any run can be undone end-to-end.
- **Dry-run mode** is supported on every action that mutates Gmail state.
- **Rate limits** are handled via batched requests + exponential backoff.

## Project layout

```
email-triage/
├── main.py                  # Click CLI entrypoint
├── config.py                # Env-driven configuration
├── classifier/
│   ├── rules.py             # Rule-based classifier
│   ├── patterns.py          # Sender/subject regex helpers
│   └── ai_classifier.py     # Claude-based fallback
├── commands/
│   ├── triage.py            # Triage flow (rule + AI + label)
│   ├── senders.py           # Sender grouping + bulk mark-read
│   ├── undo.py              # Reverse any recorded action
│   └── stats.py             # Run + action statistics
├── gmail/
│   ├── auth.py              # OAuth flow
│   ├── client.py            # Gmail API client (batched)
│   └── labels.py            # Label create/add/remove
├── db/
│   ├── repository.py        # SQLite repository
│   └── models.py            # TriageAction / TriageRun dataclasses
├── webapp/
│   ├── app.py               # Flask backend
│   ├── templates/index.html # Single-page UI
│   └── static/{app.js,style.css}
├── credentials/             # gitignored — OAuth secrets + token
├── data/                    # gitignored — SQLite DB + cache files
└── requirements.txt
```

## License

MIT — see [LICENSE](LICENSE).
