from __future__ import annotations

import json
from argparse import Namespace
from contextlib import suppress
from dataclasses import asdict

from .config import resolve_runtime_config
from .ddl_executor import PostgresDDLExecutor
from .models import ALLOWED_OVERRIDE_ACTIONS
from .pipeline import run_apply, run_plan, run_scan
from .store import MigrationStore


def _bootstrap_store(args: Namespace) -> MigrationStore:
    cfg = resolve_runtime_config(
        repo_path=args.repo,
        schema_file=args.schema_file,
        state_db_path=args.state_db,
        db_url=args.db_url,
    )

    if not cfg.repo_path.exists():
        raise SystemExit(f"Repository path does not exist: {cfg.repo_path}")
    if not cfg.schema_file.exists():
        raise SystemExit(f"Schema file does not exist: {cfg.schema_file}")

    store = MigrationStore(cfg.state_db_path)
    store.ensure_schema()
    return store


def cmd_scan(args: Namespace) -> int:
    store = _bootstrap_store(args)
    cfg = resolve_runtime_config(
        repo_path=args.repo,
        schema_file=args.schema_file,
        state_db_path=args.state_db,
        db_url=args.db_url,
    )
    result = run_scan(
        store=store,
        repo_path=cfg.repo_path,
        schema_file=cfg.schema_file,
        from_commit=args.from_commit,
        to_commit=args.to_commit,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0


def cmd_plan(args: Namespace) -> int:
    store = _bootstrap_store(args)
    cfg = resolve_runtime_config(
        repo_path=args.repo,
        schema_file=args.schema_file,
        state_db_path=args.state_db,
    )
    result = run_plan(
        store=store,
        repo_path=cfg.repo_path,
        schema_file=cfg.schema_file,
        from_commit=args.from_commit,
        to_commit=args.to_commit,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0


def cmd_apply(args: Namespace) -> int:
    store = _bootstrap_store(args)
    cfg = resolve_runtime_config(
        repo_path=args.repo,
        schema_file=args.schema_file,
        state_db_path=args.state_db,
        db_url=args.db_url,
    )
    executor = PostgresDDLExecutor(cfg.db_url) if cfg.db_url else None
    result = run_apply(
        store=store,
        repo_path=cfg.repo_path,
        schema_file=cfg.schema_file,
        from_commit=args.from_commit,
        to_commit=args.to_commit,
        ddl_executor=executor,
    )
    if executor:
        with suppress(Exception):
            executor.close()
    print(json.dumps(asdict(result), indent=2))
    return 0


def cmd_status(args: Namespace) -> int:
    store = _bootstrap_store(args)
    progress = store.get_progress()
    overrides = store.list_overrides()

    payload = {
        "last_applied_commit": progress.last_applied_commit,
        "overrides": [
            {
                "commit_hash": o.commit_hash,
                "action": o.action,
                "replacement_commit": o.replacement_commit,
                "reason": o.reason,
                "created_at": o.created_at,
            }
            for o in overrides
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_override(args: Namespace) -> int:
    store = _bootstrap_store(args)

    if args.action not in ALLOWED_OVERRIDE_ACTIONS:
        allowed = ", ".join(sorted(ALLOWED_OVERRIDE_ACTIONS))
        raise SystemExit(f"Invalid action '{args.action}'. Allowed values: {allowed}")

    if args.action == "superseded_by" and not args.replacement_commit:
        raise SystemExit("--replacement-commit is required when action is 'superseded_by'")

    if args.action == "skip" and args.replacement_commit:
        raise SystemExit("--replacement-commit cannot be provided when action is 'skip'")

    store.upsert_override(
        commit_hash=args.commit_hash,
        action=args.action,
        reason=args.reason,
        replacement_commit=args.replacement_commit,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "commit_hash": args.commit_hash,
                "action": args.action,
                "replacement_commit": args.replacement_commit,
            },
            indent=2,
        )
    )
    return 0
