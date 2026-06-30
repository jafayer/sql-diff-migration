import subprocess
from pathlib import Path

from sql_diff_migrate.pipeline import run_apply
from sql_diff_migrate.store import MigrationStore


class FakeTransactionalExecutor:
    def __init__(self, fail_on_contains: str | None = None) -> None:
        self.fail_on_contains = fail_on_contains
        self.events: list[str] = []

    def begin(self) -> None:
        self.events.append("begin")

    def execute(self, ddl: str) -> None:
        self.events.append(f"execute:{ddl}")
        if self.fail_on_contains and self.fail_on_contains in ddl:
            raise RuntimeError("synthetic ddl failure")

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


def _run(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo(repo: Path) -> None:
    _run(repo, "init")
    _run(repo, "config", "user.name", "Test User")
    _run(repo, "config", "user.email", "test@example.com")


def _commit_schema(repo: Path, sql: str, message: str) -> str:
    schema = repo / "schema.sql"
    schema.write_text(sql, encoding="utf-8")
    _run(repo, "add", "schema.sql")
    _run(repo, "commit", "-m", message)
    return _run(repo, "rev-parse", "HEAD")


def test_run_apply_executes_each_commit_in_transaction(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    store = MigrationStore(tmp_path / "state" / "state.db")
    store.ensure_schema()
    executor = FakeTransactionalExecutor()

    result = run_apply(
        store=store,
        repo_path=repo,
        schema_file=repo / "schema.sql",
        from_commit=None,
        to_commit=None,
        ddl_executor=executor,
    )

    assert result.success is True
    assert result.applied_commits == [first, second]
    assert executor.events == [
        "begin",
        "execute:CREATE TABLE people (name TEXT);",
        "commit",
        "begin",
        "execute:ALTER TABLE people ADD COLUMN id INT;",
        "commit",
    ]


def test_run_apply_rolls_back_failed_commit_transaction(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    store = MigrationStore(tmp_path / "state" / "state.db")
    store.ensure_schema()
    executor = FakeTransactionalExecutor(fail_on_contains="ADD COLUMN")

    result = run_apply(
        store=store,
        repo_path=repo,
        schema_file=repo / "schema.sql",
        from_commit=None,
        to_commit=None,
        ddl_executor=executor,
    )

    assert result.success is False
    assert result.failed_commit == second
    assert result.applied_commits == [first]
    assert "ddl execution failed" in (result.error or "").lower()
    assert store.get_progress().last_applied_commit == first
    assert executor.events == [
        "begin",
        "execute:CREATE TABLE people (name TEXT);",
        "commit",
        "begin",
        "execute:ALTER TABLE people ADD COLUMN id INT;",
        "rollback",
    ]
