from __future__ import annotations

import argparse

from .commands import cmd_apply, cmd_override, cmd_plan, cmd_scan, cmd_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-diff-migrate",
        description="Git diff-based SQL migration engine (Postgres-first, DDL-first).",
    )

    parser.add_argument(
        "--repo",
        default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--schema-file",
        required=True,
        help="Path to canonical schema file, relative to --repo or absolute",
    )
    parser.add_argument(
        "--state-db",
        default=None,
        help="Path to local migration state database (default: .sql_diff_migrate/state.db)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Postgres DSN for transactional DDL execution during apply",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan commit range for SQL schema changes")
    _add_commit_range_args(scan)
    scan.set_defaults(func=cmd_scan)

    plan = subparsers.add_parser("plan", help="Generate dry-run migration plan")
    _add_commit_range_args(plan)
    plan.set_defaults(func=cmd_plan)

    apply = subparsers.add_parser("apply", help="Apply migrations in commit order")
    _add_commit_range_args(apply)
    apply.set_defaults(func=cmd_apply)

    status = subparsers.add_parser("status", help="Show migration state and overrides")
    status.set_defaults(func=cmd_status)

    override = subparsers.add_parser(
        "override",
        help="Register explicit operator override for failed commit handling",
    )
    override.add_argument("commit_hash", help="Commit hash being overridden")
    override.add_argument(
        "--action",
        required=True,
        choices=["superseded_by", "skip"],
        help="Override action",
    )
    override.add_argument(
        "--replacement-commit",
        default=None,
        help="Replacement commit hash (required for action=superseded_by)",
    )
    override.add_argument("--reason", required=True, help="Audit reason for override")
    override.set_defaults(func=cmd_override)

    return parser


def _add_commit_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--from-commit",
        default=None,
        help="Start commit (defaults to tracked last-applied commit)",
    )
    parser.add_argument(
        "--to-commit",
        default="HEAD",
        help="End commit to process (default: HEAD)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
