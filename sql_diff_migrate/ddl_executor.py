from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class DDLExecutor(Protocol):
    def begin(self) -> None: ...

    def execute(self, ddl: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass
class PostgresDDLExecutor:
    dsn: str

    def __post_init__(self) -> None:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - import branch depends on environment
            raise RuntimeError(
                "Postgres execution requires psycopg. Install with: uv add 'psycopg[binary]'"
            ) from exc

        self._psycopg = psycopg
        self._conn = psycopg.connect(self.dsn)

    def begin(self) -> None:
        self._conn.execute("BEGIN")

    def execute(self, ddl: str) -> None:
        self._conn.execute(ddl)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
