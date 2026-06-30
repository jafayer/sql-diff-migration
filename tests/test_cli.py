from pathlib import Path

from sql_diff_migrate.cli import main


def test_override_then_status(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    schema = repo / "schema.sql"
    schema.write_text("CREATE TABLE people (name TEXT);\n", encoding="utf-8")

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "override",
            "abc123",
            "--action",
            "superseded_by",
            "--replacement-commit",
            "def456",
            "--reason",
            "repair migration",
        ]
    )
    assert code == 0

    code = main(
        [
            "--repo",
            str(repo),
            "--schema-file",
            "schema.sql",
            "status",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "abc123" in out
    assert "def456" in out
