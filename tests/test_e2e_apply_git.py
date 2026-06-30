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


def test_apply_succeeds_for_create_then_add_column(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["failed_commit"] is None
    assert payload["applied_commits"] == [first, _run(repo, "rev-parse", "HEAD")]

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "status"])
    assert code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["last_applied_commit"] == _run(repo, "rev-parse", "HEAD")


def test_apply_initial_create_table_commit_succeeds(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first]
    assert payload["failed_commit"] is None


def test_apply_recovers_via_skip_override(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "override",
            first,
            "--action",
            "skip",
            "--reason",
            "bootstrap table handled externally",
        ]
    )
    assert code == 0
    _ = capsys.readouterr()

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [second]
    assert payload["skipped_commits"][0]["commit_hash"] == first
    assert payload["failed_commit"] is None

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "status"])
    assert code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["last_applied_commit"] == second


def test_apply_recovers_via_superseded_by_override(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")
    third = _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT, age INT);\n", "add age column")

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "override",
            first,
            "--action",
            "superseded_by",
            "--replacement-commit",
            second,
            "--reason",
            "replacement commit has final shape",
        ]
    )
    assert code == 0
    _ = capsys.readouterr()

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [second, third]
    assert payload["skipped_commits"][0]["commit_hash"] == first
    assert payload["skipped_commits"][0]["action"] == "superseded_by"


def test_apply_fails_if_superseded_by_replacement_not_in_range(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    _commit_schema(repo, "CREATE TABLE people (name TEXT, id INT);\n", "add id column")

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "override",
            first,
            "--action",
            "superseded_by",
            "--replacement-commit",
            "deadbeef",
            "--reason",
            "invalid replacement",
        ]
    )
    assert code == 0
    _ = capsys.readouterr()

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is False
    assert payload["failed_commit"] == first
    assert "replacement commit" in payload["error"].lower()


def test_apply_succeeds_for_safe_type_widening(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (age INT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (age BIGINT);\n", "widen age type")

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first, second]
    assert payload["failed_commit"] is None


def test_apply_blocks_unsafe_type_narrowing(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (age TEXT);\n", "init schema")
    second = _commit_schema(repo, "CREATE TABLE people (age INT);\n", "narrow age type")

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is False
    assert payload["failed_commit"] == second
    assert "unsafe type change" in payload["error"].lower()

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "status"])
    assert code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["last_applied_commit"] == first


def test_apply_succeeds_for_index_addition(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (name TEXT);\n", "init schema")
    second = _commit_schema(
        repo,
        "CREATE TABLE people (name TEXT);\nCREATE INDEX idx_people_name ON people(name);\n",
        "add people name index",
    )

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first, second]


def test_apply_succeeds_for_unique_constraint_addition(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE people (email TEXT);\n", "init schema")
    second = _commit_schema(
        repo,
        "CREATE TABLE people (email TEXT, CONSTRAINT uq_people_email UNIQUE (email));\n",
        "add unique email constraint",
    )

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first, second]


def test_apply_succeeds_for_foreign_key_constraint_addition(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(
        repo,
        "CREATE TABLE parent (id INT);\nCREATE TABLE child (parent_id INT);\n",
        "init parent and child",
    )
    second = _commit_schema(
        repo,
        "CREATE TABLE parent (id INT);\n"
        "CREATE TABLE child (parent_id INT, CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent(id));\n",
        "add child parent fk",
    )

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "apply"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first, second]
