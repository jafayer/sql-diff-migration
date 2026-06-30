# Test-Derived Requirements

This project uses test-first development. Requirements in this file are derived directly from executable tests.

## BDD Requirements

Source: [features/migration_planning.feature](features/migration_planning.feature)

1. Given a git repo with canonical schema file changes over commits, planning from commit A to commit B must produce commit-scoped migration DDL.
2. If a commit adds a column to an existing table, the plan must include `ALTER TABLE <table> ADD COLUMN <column> <type>;`.
3. If a commit performs exactly one drop-column plus one add-column of the same type in the same table, the plan should infer a rename and include `ALTER TABLE <table> RENAME COLUMN <old> TO <new>;`.

## Unit Requirements

Source: [tests/test_schema_diff.py](tests/test_schema_diff.py), [tests/test_git_ops.py](tests/test_git_ops.py)

1. Schema diffing must detect add-column operations and render valid Postgres DDL.
2. Balanced rename heuristic must emit `rename_column` operation with expected old/new names.
3. Reading schema from a parent commit for the initial commit must return `None` rather than raising.
4. Column type transitions must emit `alter_column_type` operations with safety classification.
5. Safe widening transitions (for example `INT -> BIGINT`) must render executable `ALTER COLUMN ... TYPE ...` DDL.
6. Unsafe narrowing transitions (for example `TEXT -> INT`) must be classified as unsafe.
7. Index transitions must emit `create_index`/`drop_index` operations and executable DDL.
8. Rendered DDL must preserve deterministic dependency order, including creating tables before their indexes.
9. Named unique-constraint transitions must emit `add_unique_constraint`/`drop_unique_constraint` operations and executable DDL.
10. Named table-level foreign key transitions must emit `add_foreign_key_constraint`/`drop_foreign_key_constraint` operations and executable DDL.
11. Apply with a DDL executor must execute each commit's generated DDL in a single transaction.
12. If any DDL statement fails inside a commit transaction, apply must roll back that commit transaction and stop at that commit.

## E2E Requirements

Source: [tests/test_e2e_plan_git.py](tests/test_e2e_plan_git.py)

1. A temporary git repository initialized in tests must support full plan generation path via CLI.
2. Planning from a known commit range must process only commits in range and emit expected DDL.
3. Apply must stop on unsupported commits, preserve last-applied state, and allow continuation only via explicit override.
4. `skip` override must allow rerun progression past failed commit while preserving audit data.
5. `superseded_by` override must require a valid replacement commit within the apply range; invalid replacements must fail fast.
6. Apply must block unsafe type narrowing commits and preserve last-applied progress at the previous successful commit.
7. Apply must allow safe widening type changes to proceed.
8. Apply must allow index-addition commits to proceed when preceding dependencies are satisfied.
9. Apply must allow named unique-constraint addition commits when migration ordering requirements are met.
10. Apply must allow named foreign-key-constraint addition commits when referenced tables are present in migration order.
11. Apply with transactional executor must commit successful commit transactions and update progress only after the transaction commit.
12. Apply with transactional executor must roll back failing commit transactions and preserve last-applied progress at the previous successful commit.
13. Apply with Postgres DSN must execute generated DDL against a real Postgres database and converge schema state for successful commits.
14. On real Postgres execution failure within a commit, apply must roll back that commit transaction, record failure at that commit, and leave prior committed state intact.

## BDD Requirements

Source: [features/migration_planning.feature](features/migration_planning.feature)

1. Planning from commit diffs must include index creation DDL when an index is introduced in a later commit.
2. Planning from commit diffs must include unique-constraint addition DDL when a named table-level unique constraint is introduced.
3. Planning from commit diffs must include foreign-key-constraint addition DDL when a named table-level foreign key is introduced.

## Process Rule (Red-Green-Refactor)

1. Add/adjust scenarios in BDD feature files and assertions in unit/e2e tests first.
2. Run tests and confirm failure (red) for new behavior.
3. Implement minimum code change to pass tests (green).
4. Refactor while preserving test behavior.