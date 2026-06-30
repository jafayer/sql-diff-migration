from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ddl_executor import DDLExecutor
from .git_ops import get_commit_info, get_head_commit, list_commits, read_file_at_commit, read_file_at_parent
from .schema_diff import diff_tables, render_ddl
from .store import MigrationStore


@dataclass(frozen=True)
class ScanCommitResult:
    commit_hash: str
    before_exists: bool
    after_exists: bool
    author: str
    subject: str


@dataclass(frozen=True)
class PlanCommitResult:
    commit_hash: str
    operations: list[dict[str, str | float | None]]
    ddl: list[str]


@dataclass(frozen=True)
class ScanResult:
    mode: str
    from_commit: str | None
    to_commit: str
    commits: list[ScanCommitResult]


@dataclass(frozen=True)
class PlanResult:
    mode: str
    from_commit: str | None
    to_commit: str
    commits: list[PlanCommitResult]


@dataclass(frozen=True)
class ApplyResult:
    mode: str
    from_commit: str | None
    to_commit: str
    success: bool
    applied_commits: list[str]
    skipped_commits: list[dict[str, str | None]]
    failed_commit: str | None
    error: str | None


def _resolve_from_commit(store: MigrationStore, from_commit: str | None) -> str | None:
    if from_commit:
        return from_commit
    return store.get_progress().last_applied_commit


def _resolve_to_commit(repo_path: Path, to_commit: str | None) -> str:
    return to_commit if to_commit else get_head_commit(repo_path)


def run_scan(
    store: MigrationStore,
    repo_path: Path,
    schema_file: Path,
    from_commit: str | None,
    to_commit: str | None,
) -> ScanResult:
    resolved_from = _resolve_from_commit(store, from_commit)
    resolved_to = _resolve_to_commit(repo_path, to_commit)

    commits = list_commits(repo_path, resolved_from, resolved_to)
    scan_rows: list[ScanCommitResult] = []
    for commit in commits:
        before = read_file_at_parent(repo_path, commit, schema_file)
        after = read_file_at_commit(repo_path, commit, schema_file)
        info = get_commit_info(repo_path, commit)
        scan_rows.append(
            ScanCommitResult(
                commit_hash=commit,
                before_exists=before is not None,
                after_exists=after is not None,
                author=f"{info.author_name} <{info.author_email}>",
                subject=info.subject,
            )
        )

    return ScanResult(
        mode="scan",
        from_commit=resolved_from,
        to_commit=resolved_to,
        commits=scan_rows,
    )


def run_plan(
    store: MigrationStore,
    repo_path: Path,
    schema_file: Path,
    from_commit: str | None,
    to_commit: str | None,
) -> PlanResult:
    resolved_from = _resolve_from_commit(store, from_commit)
    resolved_to = _resolve_to_commit(repo_path, to_commit)

    commit_hashes = list_commits(repo_path, resolved_from, resolved_to)
    commit_set = set(commit_hashes)
    rows: list[PlanCommitResult] = []

    for commit in commit_hashes:
        before_sql = read_file_at_parent(repo_path, commit, schema_file) or ""
        after_sql = read_file_at_commit(repo_path, commit, schema_file) or ""
        ops = diff_tables(before_sql, after_sql)
        ddls = render_ddl(ops)
        rows.append(
            PlanCommitResult(
                commit_hash=commit,
                operations=[
                    {
                        "op": op.op,
                        "table": op.table,
                        "column": op.column,
                        "old_column": op.old_column,
                        "old_data_type": op.old_data_type,
                        "data_type": op.data_type,
                        "safety": op.safety,
                        "index_name": op.index_name,
                        "index_sql": op.index_sql,
                        "constraint_name": op.constraint_name,
                        "constraint_columns": op.constraint_columns,
                        "constraint_ref_table": op.constraint_ref_table,
                        "constraint_ref_columns": op.constraint_ref_columns,
                        "confidence": op.confidence,
                    }
                    for op in ops
                ],
                ddl=ddls,
            )
        )

    return PlanResult(
        mode="plan",
        from_commit=resolved_from,
        to_commit=resolved_to,
        commits=rows,
    )


def run_apply(
    store: MigrationStore,
    repo_path: Path,
    schema_file: Path,
    from_commit: str | None,
    to_commit: str | None,
    ddl_executor: DDLExecutor | None = None,
) -> ApplyResult:
    resolved_from = _resolve_from_commit(store, from_commit)
    resolved_to = _resolve_to_commit(repo_path, to_commit)
    commit_hashes = list_commits(repo_path, resolved_from, resolved_to)
    commit_set = set(commit_hashes)

    overrides = {override.commit_hash: override for override in store.list_overrides()}
    applied_commits: list[str] = []
    skipped_commits: list[dict[str, str | None]] = []

    for commit in commit_hashes:
        override = overrides.get(commit)
        if override and override.action in {"skip", "superseded_by"}:
            if override.action == "superseded_by":
                replacement = override.replacement_commit
                if not replacement or replacement == commit or replacement not in commit_set:
                    return ApplyResult(
                        mode="apply",
                        from_commit=resolved_from,
                        to_commit=resolved_to,
                        success=False,
                        applied_commits=applied_commits,
                        skipped_commits=skipped_commits,
                        failed_commit=commit,
                        error=(
                            "Invalid superseded_by override: replacement commit "
                            f"'{replacement}' is not valid in the apply range"
                        ),
                    )
            skipped_commits.append(
                {
                    "commit_hash": commit,
                    "action": override.action,
                    "replacement_commit": override.replacement_commit,
                }
            )
            store.update_last_applied_commit(commit)
            continue

        before_sql = read_file_at_parent(repo_path, commit, schema_file) or ""
        after_sql = read_file_at_commit(repo_path, commit, schema_file) or ""
        ops = diff_tables(before_sql, after_sql)
        ddls = render_ddl(ops)

        unsafe_type_changes = [
            op
            for op in ops
            if op.op == "alter_column_type" and op.safety == "unsafe"
        ]
        if unsafe_type_changes:
            first_unsafe = unsafe_type_changes[0]
            return ApplyResult(
                mode="apply",
                from_commit=resolved_from,
                to_commit=resolved_to,
                success=False,
                applied_commits=applied_commits,
                skipped_commits=skipped_commits,
                failed_commit=commit,
                error=(
                    "Unsafe type change detected at commit "
                    f"{commit}: {first_unsafe.table}.{first_unsafe.column} "
                    f"{first_unsafe.old_data_type} -> {first_unsafe.data_type}"
                ),
            )

        unsupported = [ddl for ddl in ddls if ddl.startswith("-- TODO")]
        if unsupported:
            return ApplyResult(
                mode="apply",
                from_commit=resolved_from,
                to_commit=resolved_to,
                success=False,
                applied_commits=applied_commits,
                skipped_commits=skipped_commits,
                failed_commit=commit,
                error=f"Unsupported DDL generated for commit {commit}: {unsupported[0]}",
            )

        if ddl_executor and ddls:
            try:
                ddl_executor.begin()
                for ddl in ddls:
                    ddl_executor.execute(ddl)
                ddl_executor.commit()
            except Exception as exc:
                try:
                    ddl_executor.rollback()
                except Exception:
                    pass
                return ApplyResult(
                    mode="apply",
                    from_commit=resolved_from,
                    to_commit=resolved_to,
                    success=False,
                    applied_commits=applied_commits,
                    skipped_commits=skipped_commits,
                    failed_commit=commit,
                    error=f"DDL execution failed at commit {commit}: {exc}",
                )

        store.update_last_applied_commit(commit)
        applied_commits.append(commit)

    return ApplyResult(
        mode="apply",
        from_commit=resolved_from,
        to_commit=resolved_to,
        success=True,
        applied_commits=applied_commits,
        skipped_commits=skipped_commits,
        failed_commit=None,
        error=None,
    )
