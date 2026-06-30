from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    repo_path: Path
    schema_file: Path
    state_db_path: Path
    db_url: str | None


def resolve_runtime_config(
    repo_path: str,
    schema_file: str,
    state_db_path: str | None,
    db_url: str | None = None,
) -> RuntimeConfig:
    repo = Path(repo_path).expanduser().resolve()
    schema = Path(schema_file)

    if not schema.is_absolute():
        schema = (repo / schema).resolve()

    if state_db_path:
        state_db = Path(state_db_path).expanduser().resolve()
    else:
        state_db = (repo / ".sql_diff_migrate" / "state.db").resolve()

    resolved_db_url = db_url if db_url else os.environ.get("SQL_DIFF_MIGRATE_DB_URL")

    return RuntimeConfig(
        repo_path=repo,
        schema_file=schema,
        state_db_path=state_db,
        db_url=resolved_db_url,
    )
