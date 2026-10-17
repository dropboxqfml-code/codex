import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

from .models import Decision, ImageRecord
from .privacy import local_path

MIN_SQLITE_VERSION = (3, 50, 2)  # CVE-2025-6965: older SQLite expr.c is affected.


class ReviewStore:
    """Store only a keyed review identifier and a non-default decision, locally."""

    def __init__(self, path: Path):
        if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
            raise ValueError(
                "SQLite 3.50.2 이상이 필요합니다(CVE-2025-6965). "
                "최신 검증된 실행 파일을 사용하세요."
            )
        path = local_path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(path, timeout=10)
        try:
            if os.name != "nt":
                path.chmod(0o600)
            self.connection.execute("PRAGMA secure_delete=ON")
            self.connection.execute("PRAGMA trusted_schema=OFF")
            self.connection.execute("PRAGMA journal_mode=DELETE")
            if hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"):
                self.connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
            columns = {r[1] for r in self.connection.execute("PRAGMA table_info(reviews)")}
            key_path = local_path(path.with_name(path.name + ".key"))
            if columns == {"review_id", "decision"} and not key_path.exists():
                raise ValueError("선택 기록 키가 없습니다. DB와 .key 파일을 함께 복원하세요")
            try:
                descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
            self.key = key_path.read_bytes()
            if len(self.key) != 32:
                raise ValueError("선택 기록 키가 손상되었습니다")
            legacy = []
            if {"path", "sha256", "decision"} <= columns:
                legacy = self.connection.execute(
                    "SELECT path, sha256, decision FROM reviews"
                ).fetchall()
                self.connection.execute("BEGIN IMMEDIATE")
                with self.connection:
                    self.connection.execute("DROP TABLE reviews")
                    self.create_table()
                    for old_path, checksum, decision in legacy:
                        if decision in {Decision.KEEP.value, Decision.DELETE.value}:
                            self.connection.execute(
                                "INSERT OR REPLACE INTO reviews VALUES (?, ?)",
                                (self.identifier(old_path, checksum), decision),
                            )
                # Rewrite the old DB; secure_delete also covers deleted cells.
                # This is not a promise of forensic erasure on SSDs/backups.
                self.connection.execute("VACUUM")
            elif columns and columns != {"review_id", "decision"}:
                raise ValueError("알 수 없는 선택 기록 DB 형식입니다")
            else:
                self.create_table()
            self.connection.execute("PRAGMA user_version=2")
            self.connection.commit()
        except Exception:
            self.connection.close()
            raise

    def create_table(self):
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('keep', 'delete'))
            )"""
        )

    def identifier(self, path: str, checksum: str) -> str:
        value = os.fsencode(os.path.normcase(path)) + b"\0" + checksum.encode("ascii")
        return hmac.new(self.key, value, hashlib.sha256).hexdigest()

    def get(self, record: ImageRecord) -> Decision:
        row = self.connection.execute(
            "SELECT decision FROM reviews WHERE review_id=?",
            (self.identifier(str(record.path), record.sha256),),
        ).fetchone()
        return Decision(row[0]) if row else Decision.HOLD

    def set(self, record: ImageRecord, decision: Decision) -> None:
        identifier = self.identifier(str(record.path), record.sha256)
        with self.connection:
            if decision == Decision.HOLD:
                self.connection.execute("DELETE FROM reviews WHERE review_id=?", (identifier,))
            else:
                self.connection.execute(
                    "INSERT OR REPLACE INTO reviews(review_id, decision) VALUES (?, ?)",
                    (identifier, decision.value),
                )

    def clear(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM reviews")
        self.connection.execute("VACUUM")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
