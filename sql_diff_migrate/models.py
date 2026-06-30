from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MigrationProgress:
    last_applied_commit: str | None


@dataclass(frozen=True)
class OverrideRecord:
    commit_hash: str
    action: str
    replacement_commit: str | None
    reason: str
    created_at: str


ALLOWED_OVERRIDE_ACTIONS = {"superseded_by", "skip"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
