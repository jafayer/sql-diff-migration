from __future__ import annotations

import json
import subprocess
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

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


def _commit_schema(repo: Path, sql_text: str, message: str) -> str:
    schema = repo / "schema.sql"
    schema.write_text(sql_text, encoding="utf-8")
    _run(repo, "add", "schema.sql")
    _run(repo, "commit", "-m", message)
    return _run(repo, "rev-parse", "HEAD")


@pytest.fixture
def postgres_db_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url(driver=None)


def test_apply_executes_transactional_ddl_against_postgres(tmp_path, capsys, postgres_db_url):
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
            "--db-url",
            postgres_db_url,
            "apply",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["applied_commits"] == [first, second]

    with psycopg.connect(postgres_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'people'
                ORDER BY ordinal_position
                """
            )
            cols = [row[0] for row in cur.fetchall()]

    assert cols == ["name", "id"]


def test_apply_rolls_back_failing_commit_in_postgres(tmp_path, capsys, postgres_db_url):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    first = _commit_schema(repo, "CREATE TABLE child (parent_id INT);\n", "init child")
    second = _commit_schema(
        repo,
        (
            "CREATE TABLE child (parent_id INT, "
            "CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent(id));\n"
        ),
        "add invalid fk",
    )

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "--db-url",
            postgres_db_url,
            "apply",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is False
    assert payload["failed_commit"] == second
    assert payload["applied_commits"] == [first]
    assert "ddl execution failed" in (payload["error"] or "").lower()

    code = main(["--repo", str(repo), "--schema-file", "schema.sql", "status"])
    assert code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["last_applied_commit"] == first

    with psycopg.connect(postgres_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE t.relname = 'child' AND c.conname = 'fk_child_parent'
                """
            )
            fk_count = cur.fetchone()[0]

    assert fk_count == 0
