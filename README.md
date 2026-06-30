# sql-diff-migrate

Git diff-based SQL migration engine (Postgres-first, DDL-first).

## Current Status

Initial implementation is in place for:

- CLI command surface (`scan`, `plan`, `apply`, `status`, `override`)
- Commit-by-commit scan of canonical schema file from git history
- SQLGlot-based table/column diffing for dry-run planning
- Normalized migration IR layer and compiler-based DDL generation
- DDL rendering for table/column/index/constraint transitions (including unique/FK)
- Transactional DDL execution path for `apply` when a Postgres DSN is provided
- Local migration state tracking database
- Explicit operator override registration for immutable-history workflows

Advisory locking and richer constraint/index heuristics are the next implementation milestones.

## Feature Completeness Matrix

Use this matrix as the project benchmark for migration-engine progress. Status values:

- `Complete`: Implemented and covered by executable tests.
- `Partial`: Implemented in part, with known scope gaps.
- `Not Started`: Planned but not implemented.

| Capability Area | Status | Completeness | Evidence | Notes |
| --- | --- | --- | --- | --- |
| CLI workflow (`scan`, `plan`, `apply`, `status`, `override`) | Complete | 100% | `tests/test_cli.py`, `tests/test_e2e_plan_git.py`, `tests/test_e2e_apply_git.py` | Core command surface is operational. |
| Git commit traversal + schema file extraction | Complete | 100% | `tests/test_git_ops.py`, e2e tests | Includes root-commit parent handling. |
| Diff engine: table and column transitions | Complete | 100% | `tests/test_schema_diff.py`, BDD scenarios | Covers create/drop table, add/drop column, rename heuristic, type changes. |
| Diff engine: index transitions | Complete | 100% | `tests/test_schema_diff.py`, BDD index scenario | Create/drop index with deterministic ordering. |
| Diff engine: named unique constraints | Complete | 100% | `tests/test_schema_diff.py`, BDD unique scenario | Add/drop named table-level unique constraints. |
| Diff engine: named foreign key constraints | Complete | 100% | `tests/test_schema_diff.py`, `tests/test_e2e_apply_git.py`, BDD FK scenario | Add/drop named table-level FK constraints. |
| IR + compiler architecture for DDL emission | Complete | 100% | `sql_diff_migrate/ir.py`, `sql_diff_migrate/compiler.py`, compiler ordering test | Runtime DDL paths (`plan`/`apply`) route through IR -> compiler. |
| Apply safety guardrails (unsafe narrowing block) | Complete | 100% | `tests/test_e2e_apply_git.py`, BDD narrowing scenario | Blocks unsafe type narrowing before state advance. |
| Override-based recovery (`skip`, `superseded_by`) | Complete | 100% | `tests/test_cli.py`, `tests/test_e2e_apply_git.py`, BDD recovery scenario | Includes replacement-commit validity checks in apply range. |
| Transactional DDL execution (real DB execution) | Partial | 60% | `tests/test_pipeline_apply_transactional.py`, `sql_diff_migrate/ddl_executor.py` | Per-commit transaction/rollback path exists behind `--db-url`; replay-against-real-Postgres test suite still pending. |
| Advisory locking for concurrent runs | Not Started | 0% | N/A | Planned milestone to prevent concurrent apply conflicts. |
| Inline constraint normalization into shared IR | Not Started | 0% | N/A | Next architecture slice for generic constraint lowering. |

Current benchmark summary: **9 complete, 1 partial, 2 not started**.

## SQL DDL Completeness And Confidence

Absolute proof for handling "any arbitrary DDL commit" is not practical. Instead, treat completeness as a measured confidence score with hard gates.

### 1) Operation Coverage Matrix (What We Intend To Support)

Track each Postgres DDL family and whether it is:

- `Supported`: parsed to IR, compiled to executable DDL, and covered by tests.
- `Detected-Unsupported`: recognized and fails safely with explicit reason.
- `Unknown`: not yet classified.

| DDL Family | Current State | Required Evidence To Mark Supported |
| --- | --- | --- |
| `CREATE/DROP TABLE` | Supported | unit + e2e + BDD + ordering check |
| `ADD/DROP/RENAME COLUMN` | Supported | unit + e2e + BDD |
| `ALTER COLUMN TYPE` | Supported (with safety classification) | unit safety tests + apply failure/allow e2e |
| `CREATE/DROP INDEX` | Supported | unit + BDD + dependency ordering |
| `ADD/DROP UNIQUE CONSTRAINT` | Supported (named table-level) | unit + BDD |
| `ADD/DROP FOREIGN KEY CONSTRAINT` | Supported (named table-level) | unit + e2e + BDD |
| Inline constraints (`col UNIQUE`, `col REFERENCES`) | Not yet supported via normalized lowering | parser + IR normalization + compiler + tests |
| Check constraints / defaults / generated columns | Unknown | parser + IR + compiler + tests |
| Sequences / identity / enum / extension DDL | Unknown | parser + IR + compiler + tests |
| Triggers / functions / views / matviews | Unknown | parser + IR + compiler + tests |

### 2) Commit Replay Gate (Can We Survive Real Histories)

For every target repository history window, run:

1. `plan` on each commit pair in range.
2. Ensure each diff falls into `Supported` or `Detected-Unsupported` (never silent unknown).
3. If `Supported`, generated DDL must parse and execute in an isolated Postgres test database.
4. Compare resulting schema against expected schema snapshot for that commit.

Success metric for the window:

- `supported_commit_rate = supported_commits / total_commits`
- `safe_failure_rate = detected_unsupported_commits / total_commits`
- `unknown_rate = unknown_commits / total_commits` (target must be `0%`)

### 3) Fuzz + Corpus Gate (Can We Generalize)

Use two automated sources:

- Corpus: real-world Postgres DDL files/commit histories.
- Fuzz: SQLGlot-generated or grammar-based random DDL transitions.

Minimum release gate recommendation:

- `unknown_rate == 0%` on corpus
- `safe_failure_rate` allowed, but every case must include deterministic, actionable reason
- `>= 99%` stable replay success for commits classified as `Supported`

### 4) Practical Definition Of "Ready For Arbitrary DDL"

Treat the engine as production-ready for arbitrary DDL only when all are true:

1. No unknown classifications in replay/corpus runs.
2. Unsupported features fail safely and explicitly (no partial silent plans).
3. Supported features consistently replay to expected schema state.
4. Operation coverage matrix is complete for the DDL families required by your org.

## Design Constraints (v1)

- Postgres-first
- DDL-first
- One canonical schema SQL file
- Stop on first failing commit
- Continue only with explicit operator override

## CLI

All commands require a canonical schema path:

```bash
uv run sql-diff-migrate --schema-file schema.sql <command>
```

Examples:

```bash
# Show migration status + overrides
uv run sql-diff-migrate --repo . --schema-file schema.sql status

# Register failed-commit override by replacement commit
uv run sql-diff-migrate --repo . --schema-file schema.sql override abc123 \
	--action superseded_by \
	--replacement-commit def456 \
	--reason "repair migration"

# Placeholder scan/plan/apply pipeline hooks
uv run sql-diff-migrate --repo . --schema-file schema.sql scan --from-commit HEAD~5 --to-commit HEAD
uv run sql-diff-migrate --repo . --schema-file schema.sql plan --from-commit HEAD~5 --to-commit HEAD
uv run sql-diff-migrate --repo . --schema-file schema.sql apply --from-commit HEAD~5 --to-commit HEAD

# Execute apply with real transactional DDL against Postgres
uv run sql-diff-migrate \
	--repo . \
	--schema-file schema.sql \
	--db-url postgresql://user:pass@localhost:5432/appdb \
	apply --from-commit HEAD~5 --to-commit HEAD
```

## State Database

Default location:

`./.sql_diff_migrate/state.db`

Tables:

- `migration_progress`: tracked last-applied commit hash
- `migration_overrides`: audited override decisions (`superseded_by` or `skip`)

## Test-First Workflow

Requirements are captured from executable tests in [REQUIREMENTS.md](REQUIREMENTS.md).

Run unit and e2e tests:

```bash
uv run pytest -q
```

Run BDD scenarios:

```bash
uv run behave -q
```

Expected development loop:

1. Update BDD and unit/e2e tests first.
2. Run tests and observe failure (red).
3. Implement minimum behavior to pass (green).
4. Refactor safely with tests guarding behavior.
