import json
import subprocess
from pathlib import Path

from sql_diff_migrate.cli import main


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


def test_plan_from_temp_git_repo_outputs_add_column_ddl(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    _ = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "plan",
            "--from-commit",
            first,
            "--to-commit",
            "HEAD",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "plan"
    assert len(payload["commits"]) == 1
    assert "ALTER TABLE people ADD COLUMN id INT;" in payload["commits"][0]["ddl"]
