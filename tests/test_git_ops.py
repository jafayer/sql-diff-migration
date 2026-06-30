from pathlib import Path
import subprocess

from sql_diff_migrate.git_ops import read_file_at_parent


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


def test_read_file_at_parent_returns_none_for_initial_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    schema = repo / "schema.sql"
    schema.write_text("CREATE TABLE people (name TEXT);\n", encoding="utf-8")
    _run(repo, "add", "schema.sql")
    _run(repo, "commit", "-m", "init schema")
    head = _run(repo, "rev-parse", "HEAD")

    content = read_file_at_parent(repo, head, schema)

    assert content is None
