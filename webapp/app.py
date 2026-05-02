"""Flask webapp for bulk email review.

Two-pane UI: senders on the left, messages on the right. Bulk actions
operate on selected message IDs. All actions are recorded in the same
SQLite repository as the CLI, so `python3 main.py undo last` works
across CLI and webapp runs.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request

from config import (
    LOW_PRIORITY_LABEL,
    REVIEWED_LABEL,
    USER_EMAIL,
    WEBAPP_HOST,
    WEBAPP_PORT,
)
from commands.senders import (
    SENDERS_CACHE,
    SenderGroup,
    _group_unread_by_sender,
    _load_cache,
    _normalize_sender,
    _save_cache,
)
from db.repository import Repository
from gmail.client import GmailClient


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    state = {
        "gmail": None,
        "repo": Repository(),
        "current_run_id": None,
        "refresh_lock": threading.Lock(),
        "refresh_status": {"running": False, "fetched": 0, "total": 0, "done_at": None, "error": None},
        "jobs": {},  # job_id -> dict of progress state
    }

    def get_gmail() -> GmailClient:
        if state["gmail"] is None:
            state["gmail"] = GmailClient()
        return state["gmail"]

    def get_run_id() -> int:
        if state["current_run_id"] is None:
            run = state["repo"].create_run()
            state["current_run_id"] = run.id
        return state["current_run_id"]

    def is_self_sent(sender_email: str) -> bool:
        return bool(USER_EMAIL) and sender_email.lower() == USER_EMAIL.strip().lower()

    @app.get("/")
    def index():
        return render_template("index.html", user_email=USER_EMAIL or "(not configured)")

    @app.get("/api/senders")
    def api_senders():
        cache = _load_cache()
        if not cache:
            return jsonify({
                "senders": [],
                "total_unread": 0,
                "total_senders": 0,
                "generated_at": None,
                "user_email": USER_EMAIL,
            })
        for s in cache["senders"]:
            s["is_self_sent"] = is_self_sent(s["email"])
        return jsonify({
            "senders": cache["senders"],
            "total_unread": cache.get("total_unread", 0),
            "total_senders": cache.get("total_senders", 0),
            "generated_at": cache.get("generated_at"),
            "user_email": USER_EMAIL,
        })

    @app.get("/api/sender/<path:sender_email>/messages")
    def api_sender_messages(sender_email: str):
        cache = _load_cache()
        if not cache:
            return jsonify({"error": "No cache available. Refresh first."}), 404

        target = _normalize_sender(sender_email)
        match = next((s for s in cache["senders"] if s["email"] == target), None)
        if not match:
            return jsonify({"error": f"Sender {sender_email!r} not in cache."}), 404

        gmail = get_gmail()
        messages = gmail._get_messages_batch(match["message_ids"])
        payload = [
            {
                "message_id": m.message_id,
                "thread_id": m.thread_id,
                "subject": m.subject,
                "snippet": m.snippet,
                "received_at": m.received_at,
                "label_ids": m.label_ids,
                "is_unread": "UNREAD" in m.label_ids,
            }
            for m in messages
        ]
        return jsonify({
            "sender": match["email"],
            "display": match.get("display", match["email"]),
            "is_self_sent": is_self_sent(match["email"]),
            "messages": payload,
        })

    @app.post("/api/refresh")
    def api_refresh():
        if state["refresh_status"]["running"]:
            return jsonify({"status": "already_running", **state["refresh_status"]})

        def run_refresh():
            state["refresh_status"] = {"running": True, "fetched": 0, "total": None, "done_at": None, "error": None}
            try:
                gmail = get_gmail()
                groups = []
                from collections import defaultdict
                acc: dict[str, dict] = defaultdict(lambda: {
                    "display": "", "count": 0, "sample_subjects": [], "message_ids": [],
                })
                fetched = 0
                for email in gmail.iter_inbox_messages(include_read=False):
                    sender = _normalize_sender(email.sender_email)
                    g = acc[sender]
                    if not g["display"]:
                        g["display"] = email.sender or sender
                    g["count"] += 1
                    g["message_ids"].append(email.message_id)
                    if len(g["sample_subjects"]) < 3 and email.subject:
                        g["sample_subjects"].append(email.subject)
                    fetched += 1
                    state["refresh_status"]["fetched"] = fetched

                ranked = sorted(acc.items(), key=lambda kv: kv[1]["count"], reverse=True)
                groups = [
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
                _save_cache(groups)
                state["refresh_status"]["done_at"] = datetime.now().isoformat()
            except Exception as e:
                state["refresh_status"]["error"] = str(e)
            finally:
                state["refresh_status"]["running"] = False

        threading.Thread(target=run_refresh, daemon=True).start()
        return jsonify({"status": "started"})

    @app.get("/api/refresh/status")
    def api_refresh_status():
        return jsonify(state["refresh_status"])

    @app.post("/api/actions/mark-read")
    def api_mark_read():
        return _start_bulk_job(request.get_json() or {}, action="mark_read")

    @app.post("/api/actions/mark-reviewed")
    def api_mark_reviewed():
        return _start_bulk_job(request.get_json() or {}, action="mark_reviewed")

    @app.post("/api/actions/apply-label")
    def api_apply_label():
        return _start_bulk_job(request.get_json() or {}, action="apply_label")

    @app.get("/api/jobs/<job_id>")
    def api_job_status(job_id: str):
        job = state["jobs"].get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify(job)

    def _start_bulk_job(payload: dict, action: str):
        message_ids = payload.get("message_ids") or []
        sender_email = payload.get("sender_email") or ""
        if not message_ids:
            return jsonify({"error": "No message_ids provided"}), 400

        if action == "apply_label":
            label_name = payload.get("label_name") or LOW_PRIORITY_LABEL
        elif action == "mark_reviewed":
            label_name = REVIEWED_LABEL
        else:
            label_name = "UNREAD"

        job_id = secrets.token_hex(8)
        run_id = get_run_id()
        state["jobs"][job_id] = {
            "job_id": job_id,
            "action": action,
            "label_name": label_name,
            "sender_email": sender_email,
            "total": len(message_ids),
            "done": 0,
            "succeeded": 0,
            "errors": [],
            "running": True,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "run_id": run_id,
            "current_message_id": None,
        }

        def worker():
            gmail = get_gmail()
            repo = state["repo"]
            job = state["jobs"][job_id]
            try:
                for mid in message_ids:
                    job["current_message_id"] = mid
                    try:
                        if action == "mark_read":
                            gmail.mark_as_read(mid)
                            repo.record_action(
                                message_id=mid, thread_id="", action_type="mark_read",
                                label_name="UNREAD", original_labels=["UNREAD"],
                                classification_method="webapp",
                                classification_rule="user_mark_read",
                                classification_reason=f"Webapp mark-read from {sender_email}",
                                confidence=1.0, sender=sender_email, subject="(webapp)",
                                run_id=run_id,
                            )
                        elif action == "mark_reviewed":
                            gmail.add_label(mid, REVIEWED_LABEL)
                            gmail.mark_as_read(mid)
                            repo.record_action(
                                message_id=mid, thread_id="", action_type="add_label",
                                label_name=REVIEWED_LABEL, original_labels=[],
                                classification_method="webapp",
                                classification_rule="user_mark_reviewed",
                                classification_reason=f"Webapp mark-reviewed from {sender_email}",
                                confidence=1.0, sender=sender_email, subject="(webapp)",
                                run_id=run_id,
                            )
                            repo.record_action(
                                message_id=mid, thread_id="", action_type="mark_read",
                                label_name="UNREAD", original_labels=["UNREAD"],
                                classification_method="webapp",
                                classification_rule="user_mark_reviewed",
                                classification_reason=f"Webapp mark-reviewed from {sender_email}",
                                confidence=1.0, sender=sender_email, subject="(webapp)",
                                run_id=run_id,
                            )
                        elif action == "apply_label":
                            gmail.add_label(mid, label_name)
                            repo.record_action(
                                message_id=mid, thread_id="", action_type="add_label",
                                label_name=label_name, original_labels=[],
                                classification_method="webapp",
                                classification_rule="user_apply_label",
                                classification_reason=f"Webapp apply-label {label_name} from {sender_email}",
                                confidence=1.0, sender=sender_email, subject="(webapp)",
                                run_id=run_id,
                            )
                        job["succeeded"] += 1
                    except Exception as e:
                        job["errors"].append({"message_id": mid, "error": str(e)})
                    finally:
                        job["done"] += 1
            finally:
                job["running"] = False
                job["finished_at"] = datetime.now().isoformat()
                job["current_message_id"] = None

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"job_id": job_id, "total": len(message_ids), "action": action, "run_id": run_id}), 202

    @app.post("/api/undo/run/<int:run_id>")
    def api_undo_run(run_id: int):
        from commands.undo import undo_run
        undone = undo_run(run_id, verbose=False)
        return jsonify({"undone": undone, "run_id": run_id})

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "user_email": USER_EMAIL or None})

    return app


def serve(host: Optional[str] = None, port: Optional[int] = None, debug: bool = False) -> None:
    app = create_app()
    h = host or WEBAPP_HOST
    p = port or WEBAPP_PORT
    print(f"\nemail-triage webapp")
    print(f"Open http://{h}:{p} in your browser\n")
    app.run(host=h, port=p, debug=debug)
