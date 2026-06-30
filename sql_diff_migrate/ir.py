from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MigrationIR:
    kind: str
    table: str
    column: str | None = None
    data_type: str | None = None
    old_column: str | None = None
    old_data_type: str | None = None
    table_columns: tuple[tuple[str, str], ...] | None = None
    index_name: str | None = None
    index_sql: str | None = None
    constraint_name: str | None = None
    constraint_columns: tuple[str, ...] | None = None
    constraint_ref_table: str | None = None
    constraint_ref_columns: tuple[str, ...] | None = None

    @classmethod
    def from_diff_op(cls, op: Any) -> "MigrationIR":
        table_columns = None
        if getattr(op, "table_columns", None):
            table_columns = tuple((col.name, col.data_type) for col in op.table_columns)

        return cls(
            kind=op.op,
            table=op.table,
            column=op.column,
            data_type=op.data_type,
            old_column=op.old_column,
            old_data_type=op.old_data_type,
            table_columns=table_columns,
            index_name=op.index_name,
            index_sql=op.index_sql,
            constraint_name=op.constraint_name,
            constraint_columns=op.constraint_columns,
            constraint_ref_table=op.constraint_ref_table,
            constraint_ref_columns=op.constraint_ref_columns,
        )
