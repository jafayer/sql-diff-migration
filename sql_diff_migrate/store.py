from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import MigrationProgress, OverrideRecord


class MigrationStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_progress (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_applied_commit TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_overrides (
                    commit_hash TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    replacement_commit TEXT,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO migration_progress (id, last_applied_commit)
                VALUES (1, NULL)
                ON CONFLICT(id) DO NOTHING
                """
            )
            conn.commit()

    def get_progress(self) -> MigrationProgress:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT last_applied_commit FROM migration_progress WHERE id = 1"
            ).fetchone()
        return MigrationProgress(last_applied_commit=row[0] if row else None)

    def update_last_applied_commit(self, commit_hash: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE migration_progress
                SET last_applied_commit = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (commit_hash,),
            )
            conn.commit()

    def upsert_override(
        self,
        commit_hash: str,
        action: str,
        reason: str,
        replacement_commit: str | None,
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO migration_overrides (commit_hash, action, replacement_commit, reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(commit_hash) DO UPDATE SET
                    action = excluded.action,
                    replacement_commit = excluded.replacement_commit,
                    reason = excluded.reason,
                    created_at = CURRENT_TIMESTAMP
                """,
                (commit_hash, action, replacement_commit, reason),
            )
            conn.commit()

    def list_overrides(self) -> list[OverrideRecord]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT commit_hash, action, replacement_commit, reason, created_at
                FROM migration_overrides
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            OverrideRecord(
                commit_hash=row[0],
                action=row[1],
                replacement_commit=row[2],
                reason=row[3],
                created_at=row[4],
            )
            for row in rows
        ]
