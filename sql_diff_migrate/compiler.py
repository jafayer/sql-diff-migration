from __future__ import annotations

from .ir import MigrationIR


def compile_ir_to_ddl(ir_ops: list[MigrationIR]) -> list[str]:
    priority = {
        "create_table": 10,
        "add_column": 20,
        "rename_column": 30,
        "alter_column_type": 40,
        "add_unique_constraint": 45,
        "add_foreign_key_constraint": 47,
        "create_index": 50,
        "drop_index": 60,
        "drop_foreign_key_constraint": 62,
        "drop_unique_constraint": 65,
        "drop_column": 70,
        "drop_table": 80,
    }
    ordered_ops = sorted(
        ir_ops,
        key=lambda op: (
            priority.get(op.kind, 999),
            op.table,
            op.column or "",
            op.index_name or "",
            op.constraint_name or "",
        ),
    )

    ddls: list[str] = []
    for op in ordered_ops:
        if op.kind == "create_table":
            cols = op.table_columns or ()
            rendered_cols = ", ".join(f"{name} {data_type}" for name, data_type in cols)
            ddls.append(f"CREATE TABLE {op.table} ({rendered_cols});")
        elif op.kind == "drop_table":
            ddls.append(f"DROP TABLE IF EXISTS {op.table} CASCADE;")
        elif op.kind == "add_column" and op.column and op.data_type:
            ddls.append(f"ALTER TABLE {op.table} ADD COLUMN {op.column} {op.data_type};")
        elif op.kind == "drop_column" and op.column:
            ddls.append(f"ALTER TABLE {op.table} DROP COLUMN {op.column};")
        elif op.kind == "rename_column" and op.column and op.old_column:
            ddls.append(f"ALTER TABLE {op.table} RENAME COLUMN {op.old_column} TO {op.column};")
        elif op.kind == "alter_column_type" and op.column and op.data_type:
            ddls.append(f"ALTER TABLE {op.table} ALTER COLUMN {op.column} TYPE {op.data_type};")
        elif op.kind == "create_index" and op.index_sql:
            ddls.append(f"{op.index_sql};")
        elif op.kind == "drop_index" and op.index_name:
            ddls.append(f"DROP INDEX IF EXISTS {op.index_name};")
        elif op.kind == "add_unique_constraint" and op.constraint_name and op.constraint_columns:
            cols = ", ".join(op.constraint_columns)
            ddls.append(
                f"ALTER TABLE {op.table} ADD CONSTRAINT {op.constraint_name} UNIQUE ({cols});"
            )
        elif op.kind == "drop_unique_constraint" and op.constraint_name:
            ddls.append(f"ALTER TABLE {op.table} DROP CONSTRAINT {op.constraint_name};")
        elif (
            op.kind == "add_foreign_key_constraint"
            and op.constraint_name
            and op.constraint_columns
            and op.constraint_ref_table
            and op.constraint_ref_columns
        ):
            cols = ", ".join(op.constraint_columns)
            ref_cols = ", ".join(op.constraint_ref_columns)
            ddls.append(
                f"ALTER TABLE {op.table} ADD CONSTRAINT {op.constraint_name} "
                f"FOREIGN KEY ({cols}) REFERENCES {op.constraint_ref_table} ({ref_cols});"
            )
        elif op.kind == "drop_foreign_key_constraint" and op.constraint_name:
            ddls.append(f"ALTER TABLE {op.table} DROP CONSTRAINT {op.constraint_name};")
    return ddls
