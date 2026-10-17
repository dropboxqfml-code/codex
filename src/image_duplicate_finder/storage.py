import sqlite3
from pathlib import Path

from .models import Decision, ImageRecord


class ReviewStore:
    """A connection belongs to the calling thread; no cross-thread connection sharing."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS reviews (
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('keep', 'hold', 'delete')),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (path, sha256)
            )"""
        )
        self.connection.commit()

    def get(self, record: ImageRecord) -> Decision:
        row = self.connection.execute(
            "SELECT decision FROM reviews WHERE path=? AND sha256=?",
            (str(record.path), record.sha256),
        ).fetchone()
        return Decision(row[0]) if row else Decision.HOLD

    def set(self, record: ImageRecord, decision: Decision) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO reviews(path, sha256, decision) VALUES (?, ?, ?)
                   ON CONFLICT(path, sha256) DO UPDATE SET
                   decision=excluded.decision, updated_at=CURRENT_TIMESTAMP""",
                (str(record.path), record.sha256, decision.value),
            )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
