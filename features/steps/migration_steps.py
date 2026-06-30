from __future__ import annotations

import json
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import shutil

from behave import given, then, when

from sql_diff_migrate.cli import main


def _run(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _run_cli_json(context, command_args: list[str]) -> dict:
    buffer = StringIO()
    with redirect_stdout(buffer):
        exit_code = main(
            [
                "--repo",
                str(context.repo),
                "--schema-file",
                context.schema_file,
                *command_args,
            ]
        )
    assert exit_code == 0
    return json.loads(buffer.getvalue())


@given("a temporary git repo with schema file {schema_file}")
def step_given_temp_repo(context, schema_file):
    context.repo = Path(context.config.userdata.get("tmp_repo", context.config.base_dir)) / ".behave_tmp_repo"
    if context.repo.exists():
        shutil.rmtree(context.repo)
    context.repo.mkdir(parents=True, exist_ok=True)

    _run(context.repo, "init")
    _run(context.repo, "config", "user.name", "BDD User")
    _run(context.repo, "config", "user.email", "bdd@example.com")
    context.schema_file = schema_file
    context.commits = {}


@given("commit {name} with SQL:")
def step_given_commit_with_sql(context, name):
    schema = context.repo / context.schema_file
    schema.write_text(context.text.strip() + "\n", encoding="utf-8")
    _run(context.repo, "add", context.schema_file)
    _run(context.repo, "commit", "-m", name)
    context.commits[name] = _run(context.repo, "rev-parse", "HEAD")


@when("I run plan from commit {name} to HEAD")
def step_when_run_plan(context, name):
    from_commit = context.commits[name]
    context.plan_payload = _run_cli_json(
        context,
        [
            "plan",
            "--from-commit",
            from_commit,
            "--to-commit",
            "HEAD",
        ],
    )


@then("the plan should include DDL {ddl}")
def step_then_plan_contains_ddl(context, ddl):
    ddls = []
    for commit in context.plan_payload["commits"]:
        ddls.extend(commit["ddl"])
    assert ddl in ddls


@when("I run apply to HEAD")
def step_when_run_apply(context):
    context.apply_payload = _run_cli_json(context, ["apply", "--to-commit", "HEAD"])


@then("apply should fail at commit {name}")
def step_then_apply_fails_at(context, name):
    assert context.apply_payload["success"] is False
    assert context.apply_payload["failed_commit"] == context.commits[name]


@when("I register override skip for commit {name} with reason {reason}")
def step_when_register_skip_override(context, name, reason):
    payload = _run_cli_json(
        context,
        [
            "override",
            context.commits[name],
            "--action",
            "skip",
            "--reason",
            reason,
        ],
    )
    assert payload["ok"] is True


@when(
    "I register override superseded_by for commit {name} with replacement {replacement_name} and reason {reason}"
)
def step_when_register_superseded_override(context, name, replacement_name, reason):
    payload = _run_cli_json(
        context,
        [
            "override",
            context.commits[name],
            "--action",
            "superseded_by",
            "--replacement-commit",
            context.commits[replacement_name],
            "--reason",
            reason,
        ],
    )
    assert payload["ok"] is True


@then("apply should succeed")
def step_then_apply_succeeds(context):
    assert context.apply_payload["success"] is True
    assert context.apply_payload["failed_commit"] is None


@then("status should show last applied commit {name}")
def step_then_status_last_applied(context, name):
    payload = _run_cli_json(context, ["status"])
    assert payload["last_applied_commit"] == context.commits[name]
