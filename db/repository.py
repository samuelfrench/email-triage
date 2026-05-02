"""Database repository for triage tracking."""
import sqlite3
import json
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from config import DATABASE_PATH
from .models import TriageAction, TriageRun


class Repository:
    """SQLite repository for tracking triage actions."""

    def __init__(self, db_path: str = None):
        """
        Initialize repository.

        Args:
            db_path: Path to SQLite database. Defaults to config value.
        """
        self.db_path = db_path or str(DATABASE_PATH)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS triage_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    emails_processed INTEGER DEFAULT 0,
                    high_priority INTEGER DEFAULT 0,
                    low_priority INTEGER DEFAULT 0,
                    uncertain INTEGER DEFAULT 0,
                    ai_calls INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running'
                );

                CREATE TABLE IF NOT EXISTS triage_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    label_name TEXT NOT NULL,
                    original_labels TEXT,
                    classification_method TEXT,
                    classification_rule TEXT,
                    classification_reason TEXT,
                    confidence REAL DEFAULT 1.0,
                    sender TEXT,
                    subject TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    undone_at TIMESTAMP,
                    run_id INTEGER,
                    FOREIGN KEY (run_id) REFERENCES triage_runs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_actions_message_id ON triage_actions(message_id);
                CREATE INDEX IF NOT EXISTS idx_actions_undone ON triage_actions(undone_at);
                CREATE INDEX IF NOT EXISTS idx_actions_run_id ON triage_actions(run_id);
            """)

    # Triage Run operations

    def create_run(self) -> TriageRun:
        """Create a new triage run."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO triage_runs (status) VALUES ('running')"
            )
            run_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM triage_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return self._row_to_run(row)

    def update_run(self, run: TriageRun) -> None:
        """Update a triage run."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE triage_runs SET
                    completed_at = ?,
                    emails_processed = ?,
                    high_priority = ?,
                    low_priority = ?,
                    uncertain = ?,
                    ai_calls = ?,
                    errors = ?,
                    status = ?
                WHERE id = ?
            """, (
                run.completed_at.isoformat() if run.completed_at else None,
                run.emails_processed,
                run.high_priority,
                run.low_priority,
                run.uncertain,
                run.ai_calls,
                run.errors,
                run.status,
                run.id,
            ))

    def get_last_run(self) -> Optional[TriageRun]:
        """Get the most recent triage run."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM triage_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return self._row_to_run(row) if row else None

    def get_run_by_id(self, run_id: int) -> Optional[TriageRun]:
        """Get a triage run by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM triage_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return self._row_to_run(row) if row else None

    def get_all_runs(self, limit: int = 20) -> list[TriageRun]:
        """Get recent triage runs."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM triage_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_run(row) for row in rows]

    # Triage Action operations

    def record_action(
        self,
        message_id: str,
        thread_id: str,
        action_type: str,
        label_name: str,
        original_labels: list[str],
        classification_method: str,
        classification_rule: Optional[str],
        classification_reason: Optional[str],
        confidence: float,
        sender: str,
        subject: str,
        run_id: Optional[int] = None,
    ) -> TriageAction:
        """Record a triage action."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO triage_actions (
                    message_id, thread_id, action_type, label_name,
                    original_labels, classification_method, classification_rule,
                    classification_reason, confidence, sender, subject, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, thread_id, action_type, label_name,
                json.dumps(original_labels), classification_method,
                classification_rule, classification_reason, confidence,
                sender, subject, run_id,
            ))
            action_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM triage_actions WHERE id = ?", (action_id,)
            ).fetchone()
            return self._row_to_action(row)

    def get_action_by_message_id(self, message_id: str) -> Optional[TriageAction]:
        """Get the most recent action for a message."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM triage_actions WHERE message_id = ? AND undone_at IS NULL ORDER BY id DESC LIMIT 1",
                (message_id,)
            ).fetchone()
            return self._row_to_action(row) if row else None

    def get_actions_for_run(self, run_id: int) -> list[TriageAction]:
        """Get all actions for a triage run."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM triage_actions WHERE run_id = ? AND undone_at IS NULL",
                (run_id,)
            ).fetchall()
            return [self._row_to_action(row) for row in rows]

    def get_all_pending_actions(self) -> list[TriageAction]:
        """Get all actions that haven't been undone."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM triage_actions WHERE undone_at IS NULL ORDER BY id DESC"
            ).fetchall()
            return [self._row_to_action(row) for row in rows]

    def mark_action_undone(self, action_id: int) -> None:
        """Mark an action as undone."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE triage_actions SET undone_at = ? WHERE id = ?",
                (datetime.now().isoformat(), action_id)
            )

    def get_stats(self) -> dict:
        """Get overall statistics."""
        with self._get_connection() as conn:
            total_runs = conn.execute(
                "SELECT COUNT(*) FROM triage_runs"
            ).fetchone()[0]

            total_actions = conn.execute(
                "SELECT COUNT(*) FROM triage_actions WHERE undone_at IS NULL"
            ).fetchone()[0]

            by_method = conn.execute("""
                SELECT classification_method, COUNT(*) as count
                FROM triage_actions WHERE undone_at IS NULL
                GROUP BY classification_method
            """).fetchall()

            by_rule = conn.execute("""
                SELECT classification_rule, COUNT(*) as count
                FROM triage_actions WHERE undone_at IS NULL AND classification_method = 'rule'
                GROUP BY classification_rule
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()

            return {
                "total_runs": total_runs,
                "total_actions": total_actions,
                "by_method": {row[0]: row[1] for row in by_method},
                "top_rules": {row[0]: row[1] for row in by_rule},
            }

    # Helper methods

    def _row_to_run(self, row: sqlite3.Row) -> TriageRun:
        """Convert a database row to TriageRun."""
        return TriageRun(
            id=row["id"],
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            emails_processed=row["emails_processed"],
            high_priority=row["high_priority"],
            low_priority=row["low_priority"],
            uncertain=row["uncertain"],
            ai_calls=row["ai_calls"],
            errors=row["errors"],
            status=row["status"],
        )

    def _row_to_action(self, row: sqlite3.Row) -> TriageAction:
        """Convert a database row to TriageAction."""
        return TriageAction(
            id=row["id"],
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            action_type=row["action_type"],
            label_name=row["label_name"],
            original_labels=json.loads(row["original_labels"]) if row["original_labels"] else [],
            classification_method=row["classification_method"],
            classification_rule=row["classification_rule"],
            classification_reason=row["classification_reason"],
            confidence=row["confidence"],
            sender=row["sender"],
            subject=row["subject"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            undone_at=datetime.fromisoformat(row["undone_at"]) if row["undone_at"] else None,
            run_id=row["run_id"],
        )
