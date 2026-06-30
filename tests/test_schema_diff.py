from sql_diff_migrate.compiler import compile_ir_to_ddl
from sql_diff_migrate.ir import MigrationIR
from sql_diff_migrate.schema_diff import diff_tables, render_ddl


def test_add_column_generates_alter_add():
    before = "CREATE TABLE people (name TEXT);"
    after = "CREATE TABLE people (name TEXT, id INT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "add_column" and op.column == "id" for op in ops)
    assert "ALTER TABLE people ADD COLUMN id INT;" in ddl


def test_balanced_rename_heuristic_generates_rename_ddl():
    before = "CREATE TABLE people (name TEXT);"
    after = "CREATE TABLE people (full_name TEXT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert len(ops) == 1
    assert ops[0].op == "rename_column"
    assert ops[0].old_column == "name"
    assert ops[0].column == "full_name"
    assert "ALTER TABLE people RENAME COLUMN name TO full_name;" in ddl


def test_create_table_renders_executable_ddl():
    before = ""
    after = "CREATE TABLE people (id INT, name TEXT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "create_table" and op.table == "people" for op in ops)
    assert "CREATE TABLE people (id INT, name TEXT);" in ddl


def test_widening_type_change_is_safe_and_renders_alter_type():
    before = "CREATE TABLE people (age INT);"
    after = "CREATE TABLE people (age BIGINT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    type_ops = [op for op in ops if op.op == "alter_column_type"]
    assert len(type_ops) == 1
    assert type_ops[0].safety == "safe"
    assert "ALTER TABLE people ALTER COLUMN age TYPE BIGINT;" in ddl


def test_narrowing_type_change_is_unsafe():
    before = "CREATE TABLE people (age TEXT);"
    after = "CREATE TABLE people (age INT);"

    ops = diff_tables(before, after)

    type_ops = [op for op in ops if op.op == "alter_column_type"]
    assert len(type_ops) == 1
    assert type_ops[0].safety == "unsafe"


def test_create_index_renders_executable_ddl():
    before = "CREATE TABLE people (name TEXT);"
    after = "CREATE TABLE people (name TEXT); CREATE INDEX idx_people_name ON people(name);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "create_index" and op.index_name == "idx_people_name" for op in ops)
    assert "CREATE INDEX idx_people_name ON people(name);" in ddl


def test_drop_index_renders_executable_ddl():
    before = "CREATE TABLE people (name TEXT); CREATE INDEX idx_people_name ON people(name);"
    after = "CREATE TABLE people (name TEXT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "drop_index" and op.index_name == "idx_people_name" for op in ops)
    assert "DROP INDEX IF EXISTS idx_people_name;" in ddl


def test_create_table_and_index_are_rendered_in_dependency_order():
    before = ""
    after = "CREATE TABLE people (name TEXT); CREATE INDEX idx_people_name ON people(name);"

    ddl = render_ddl(diff_tables(before, after))

    assert ddl.index("CREATE TABLE people (name TEXT);") < ddl.index(
        "CREATE INDEX idx_people_name ON people(name);"
    )


def test_add_unique_constraint_renders_alter_table_add_constraint():
    before = "CREATE TABLE people (email TEXT);"
    after = (
        "CREATE TABLE people (email TEXT, "
        "CONSTRAINT uq_people_email UNIQUE (email));"
    )

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "add_unique_constraint" and op.constraint_name == "uq_people_email" for op in ops)
    assert "ALTER TABLE people ADD CONSTRAINT uq_people_email UNIQUE (email);" in ddl


def test_drop_unique_constraint_renders_alter_table_drop_constraint():
    before = (
        "CREATE TABLE people (email TEXT, "
        "CONSTRAINT uq_people_email UNIQUE (email));"
    )
    after = "CREATE TABLE people (email TEXT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "drop_unique_constraint" and op.constraint_name == "uq_people_email" for op in ops)
    assert "ALTER TABLE people DROP CONSTRAINT uq_people_email;" in ddl


def test_add_foreign_key_constraint_renders_alter_table_add_constraint():
    before = "CREATE TABLE parent (id INT); CREATE TABLE child (parent_id INT);"
    after = (
        "CREATE TABLE parent (id INT); "
        "CREATE TABLE child (parent_id INT, "
        "CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent(id));"
    )

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "add_foreign_key_constraint" and op.constraint_name == "fk_child_parent" for op in ops)
    assert (
        "ALTER TABLE child ADD CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) "
        "REFERENCES parent (id);"
    ) in ddl


def test_drop_foreign_key_constraint_renders_alter_table_drop_constraint():
    before = (
        "CREATE TABLE parent (id INT); "
        "CREATE TABLE child (parent_id INT, "
        "CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent(id));"
    )
    after = "CREATE TABLE parent (id INT); CREATE TABLE child (parent_id INT);"

    ops = diff_tables(before, after)
    ddl = render_ddl(ops)

    assert any(op.op == "drop_foreign_key_constraint" and op.constraint_name == "fk_child_parent" for op in ops)
    assert "ALTER TABLE child DROP CONSTRAINT fk_child_parent;" in ddl


def test_ir_compiler_orders_create_table_before_foreign_key_add():
    ir_ops = [
        MigrationIR(
            kind="add_foreign_key_constraint",
            table="child",
            constraint_name="fk_child_parent",
            constraint_columns=("parent_id",),
            constraint_ref_table="parent",
            constraint_ref_columns=("id",),
        ),
        MigrationIR(
            kind="create_table",
            table="parent",
            table_columns=(("id", "INT"),),
        ),
        MigrationIR(
            kind="create_table",
            table="child",
            table_columns=(("parent_id", "INT"),),
        ),
    ]

    ddl = compile_ir_to_ddl(ir_ops)

    assert ddl.index("CREATE TABLE parent (id INT);") < ddl.index(
        "ALTER TABLE child ADD CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent (id);"
    )
    assert ddl.index("CREATE TABLE child (parent_id INT);") < ddl.index(
        "ALTER TABLE child ADD CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent (id);"
    )
