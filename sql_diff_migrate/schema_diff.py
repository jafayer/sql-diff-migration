from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .compiler import compile_ir_to_ddl
from .ir import MigrationIR


@dataclass(frozen=True)
class ColumnDef:
    name: str
    data_type: str


@dataclass(frozen=True)
class TableDef:
    name: str
    columns: dict[str, ColumnDef]


@dataclass(frozen=True)
class IndexDef:
    name: str
    sql: str


@dataclass(frozen=True)
class UniqueConstraintDef:
    table: str
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ForeignKeyConstraintDef:
    table: str
    name: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class DiffOp:
    op: str
    table: str
    column: str | None = None
    data_type: str | None = None
    old_column: str | None = None
    old_data_type: str | None = None
    confidence: float | None = None
    table_columns: list[ColumnDef] | None = None
    safety: str | None = None
    index_name: str | None = None
    index_sql: str | None = None
    constraint_name: str | None = None
    constraint_columns: tuple[str, ...] | None = None
    constraint_ref_table: str | None = None
    constraint_ref_columns: tuple[str, ...] | None = None


_INTEGER_ORDER = ["SMALLINT", "INT", "INTEGER", "BIGINT"]


def _normalize_type(data_type: str) -> str:
    return " ".join(data_type.upper().split())


def _classify_type_change(old_type: str, new_type: str) -> str:
    old_norm = _normalize_type(old_type)
    new_norm = _normalize_type(new_type)

    if old_norm == new_norm:
        return "safe"

    if old_norm in _INTEGER_ORDER and new_norm in _INTEGER_ORDER:
        return "safe" if _INTEGER_ORDER.index(new_norm) >= _INTEGER_ORDER.index(old_norm) else "unsafe"

    if new_norm == "TEXT":
        return "safe"

    if old_norm.startswith("VARCHAR") and new_norm.startswith("VARCHAR"):
        return "safe"

    if old_norm.startswith("VARCHAR") and new_norm == "TEXT":
        return "safe"

    if old_norm == "TEXT" and new_norm.startswith("VARCHAR"):
        return "unsafe"

    if old_norm == "TEXT" and new_norm in _INTEGER_ORDER:
        return "unsafe"

    return "unsafe"


def parse_schema_tables(sql_text: str) -> dict[str, TableDef]:
    tables: dict[str, TableDef] = {}
    if not sql_text.strip():
        return tables

    expressions = sqlglot.parse(sql_text, read="postgres")
    for expression in expressions:
        if isinstance(expression, exp.Create) and expression.kind == "TABLE":
            table_expr = expression.this
            if not isinstance(table_expr, exp.Schema):
                continue
            table_name = table_expr.this.sql(dialect="postgres")

            columns: dict[str, ColumnDef] = {}
            for col in table_expr.expressions:
                if isinstance(col, exp.ColumnDef):
                    col_name = col.this.sql(dialect="postgres")
                    kind = col.args.get("kind")
                    data_type = kind.sql(dialect="postgres") if kind is not None else "TEXT"
                    columns[col_name] = ColumnDef(name=col_name, data_type=data_type)

            tables[table_name] = TableDef(name=table_name, columns=columns)

    return tables


def parse_schema_indexes(sql_text: str) -> dict[str, IndexDef]:
    indexes: dict[str, IndexDef] = {}
    if not sql_text.strip():
        return indexes

    expressions = sqlglot.parse(sql_text, read="postgres")
    for expression in expressions:
        if isinstance(expression, exp.Create) and expression.kind == "INDEX":
            index_expr = expression.this
            if not isinstance(index_expr, exp.Index):
                continue

            index_name_expr = index_expr.this
            index_name = index_name_expr.sql(dialect="postgres")
            index_sql = expression.sql(dialect="postgres")
            indexes[index_name] = IndexDef(name=index_name, sql=index_sql)

    return indexes


def parse_schema_unique_constraints(sql_text: str) -> dict[tuple[str, str], UniqueConstraintDef]:
    constraints: dict[tuple[str, str], UniqueConstraintDef] = {}
    if not sql_text.strip():
        return constraints

    expressions = sqlglot.parse(sql_text, read="postgres")
    for expression in expressions:
        if not (isinstance(expression, exp.Create) and expression.kind == "TABLE"):
            continue

        table_expr = expression.this
        if not isinstance(table_expr, exp.Schema):
            continue
        table_name = table_expr.this.sql(dialect="postgres")

        for item in table_expr.expressions:
            if not isinstance(item, exp.Constraint):
                continue

            constraint_name = item.this.sql(dialect="postgres")
            unique_expr = next(
                (sub for sub in item.expressions if isinstance(sub, exp.UniqueColumnConstraint)),
                None,
            )
            if unique_expr is None:
                continue

            cols_expr = unique_expr.this
            if not isinstance(cols_expr, exp.Schema):
                continue
            columns = tuple(col.sql(dialect="postgres") for col in cols_expr.expressions)
            key = (table_name, constraint_name)
            constraints[key] = UniqueConstraintDef(
                table=table_name,
                name=constraint_name,
                columns=columns,
            )

    return constraints


def parse_schema_foreign_key_constraints(sql_text: str) -> dict[tuple[str, str], ForeignKeyConstraintDef]:
    constraints: dict[tuple[str, str], ForeignKeyConstraintDef] = {}
    if not sql_text.strip():
        return constraints

    expressions = sqlglot.parse(sql_text, read="postgres")
    for expression in expressions:
        if not (isinstance(expression, exp.Create) and expression.kind == "TABLE"):
            continue

        table_expr = expression.this
        if not isinstance(table_expr, exp.Schema):
            continue
        table_name = table_expr.this.sql(dialect="postgres")

        for item in table_expr.expressions:
            if not isinstance(item, exp.Constraint):
                continue

            constraint_name = item.this.sql(dialect="postgres")
            fk_expr = next((sub for sub in item.expressions if isinstance(sub, exp.ForeignKey)), None)
            if fk_expr is None:
                continue

            local_columns = tuple(col.sql(dialect="postgres") for col in fk_expr.expressions)
            reference = fk_expr.args.get("reference")
            if not isinstance(reference, exp.Reference):
                continue
            ref_schema = reference.this
            if not isinstance(ref_schema, exp.Schema):
                continue

            ref_table_expr = ref_schema.this
            if not isinstance(ref_table_expr, exp.Table):
                continue
            ref_table = ref_table_expr.sql(dialect="postgres")
            ref_columns = tuple(col.sql(dialect="postgres") for col in ref_schema.expressions)

            key = (table_name, constraint_name)
            constraints[key] = ForeignKeyConstraintDef(
                table=table_name,
                name=constraint_name,
                columns=local_columns,
                ref_table=ref_table,
                ref_columns=ref_columns,
            )

    return constraints


def diff_tables(before_sql: str, after_sql: str) -> list[DiffOp]:
    before_tables = parse_schema_tables(before_sql)
    after_tables = parse_schema_tables(after_sql)
    before_indexes = parse_schema_indexes(before_sql)
    after_indexes = parse_schema_indexes(after_sql)
    before_unique = parse_schema_unique_constraints(before_sql)
    after_unique = parse_schema_unique_constraints(after_sql)
    before_fk = parse_schema_foreign_key_constraints(before_sql)
    after_fk = parse_schema_foreign_key_constraints(after_sql)

    ops: list[DiffOp] = []

    for table_name in sorted(before_tables.keys() - after_tables.keys()):
        ops.append(DiffOp(op="drop_table", table=table_name))

    for table_name in sorted(after_tables.keys() - before_tables.keys()):
        table_columns = list(after_tables[table_name].columns.values())
        ops.append(
            DiffOp(
                op="create_table",
                table=table_name,
                table_columns=table_columns,
            )
        )

    for table_name in sorted(before_tables.keys() & after_tables.keys()):
        before_cols = before_tables[table_name].columns
        after_cols = after_tables[table_name].columns

        dropped = sorted(before_cols.keys() - after_cols.keys())
        added = sorted(after_cols.keys() - before_cols.keys())

        # Balanced rename heuristic: 1 drop + 1 add of same type in same table.
        if len(dropped) == 1 and len(added) == 1:
            old_name = dropped[0]
            new_name = added[0]
            if before_cols[old_name].data_type == after_cols[new_name].data_type:
                ops.append(
                    DiffOp(
                        op="rename_column",
                        table=table_name,
                        column=new_name,
                        old_column=old_name,
                        data_type=after_cols[new_name].data_type,
                        confidence=0.75,
                    )
                )
                dropped = []
                added = []

        for col in dropped:
            ops.append(
                DiffOp(
                    op="drop_column",
                    table=table_name,
                    column=col,
                    data_type=before_cols[col].data_type,
                )
            )

        for col in added:
            ops.append(
                DiffOp(
                    op="add_column",
                    table=table_name,
                    column=col,
                    data_type=after_cols[col].data_type,
                )
            )

        for col in sorted(before_cols.keys() & after_cols.keys()):
            old_type = before_cols[col].data_type
            new_type = after_cols[col].data_type
            if _normalize_type(old_type) != _normalize_type(new_type):
                ops.append(
                    DiffOp(
                        op="alter_column_type",
                        table=table_name,
                        column=col,
                        old_data_type=old_type,
                        data_type=new_type,
                        safety=_classify_type_change(old_type, new_type),
                    )
                )

    for index_name in sorted(before_indexes.keys() - after_indexes.keys()):
        ops.append(
            DiffOp(
                op="drop_index",
                table="",
                index_name=index_name,
            )
        )

    for index_name in sorted(after_indexes.keys() - before_indexes.keys()):
        ops.append(
            DiffOp(
                op="create_index",
                table="",
                index_name=index_name,
                index_sql=after_indexes[index_name].sql,
            )
        )

    for key in sorted(before_unique.keys() - after_unique.keys()):
        c = before_unique[key]
        ops.append(
            DiffOp(
                op="drop_unique_constraint",
                table=c.table,
                constraint_name=c.name,
                constraint_columns=c.columns,
            )
        )

    for key in sorted(after_unique.keys() - before_unique.keys()):
        c = after_unique[key]
        ops.append(
            DiffOp(
                op="add_unique_constraint",
                table=c.table,
                constraint_name=c.name,
                constraint_columns=c.columns,
            )
        )

    for key in sorted(before_fk.keys() - after_fk.keys()):
        c = before_fk[key]
        ops.append(
            DiffOp(
                op="drop_foreign_key_constraint",
                table=c.table,
                constraint_name=c.name,
                constraint_columns=c.columns,
                constraint_ref_table=c.ref_table,
                constraint_ref_columns=c.ref_columns,
            )
        )

    for key in sorted(after_fk.keys() - before_fk.keys()):
        c = after_fk[key]
        ops.append(
            DiffOp(
                op="add_foreign_key_constraint",
                table=c.table,
                constraint_name=c.name,
                constraint_columns=c.columns,
                constraint_ref_table=c.ref_table,
                constraint_ref_columns=c.ref_columns,
            )
        )

    return ops


def render_ddl(ops: list[DiffOp]) -> list[str]:
    ir_ops = [MigrationIR.from_diff_op(op) for op in ops]
    return compile_ir_to_ddl(ir_ops)
