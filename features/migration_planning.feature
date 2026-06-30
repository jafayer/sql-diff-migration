Feature: Migration planning from git commit diffs
  In order to migrate database schemas safely
  As a maintainer
  I want git-driven SQL schema transitions converted into DDL plans

  Scenario: Adding a column in a later commit yields add-column DDL
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (name TEXT);
      """
    And commit add_id_column with SQL:
      """
      CREATE TABLE people (name TEXT, id INT);
      """
    When I run plan from commit init_schema to HEAD
    Then the plan should include DDL ALTER TABLE people ADD COLUMN id INT;

  Scenario: Drop and add same type in one commit is treated as rename
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (name TEXT);
      """
    And commit rename_name with SQL:
      """
      CREATE TABLE people (full_name TEXT);
      """
    When I run plan from commit init_schema to HEAD
    Then the plan should include DDL ALTER TABLE people RENAME COLUMN name TO full_name;

  Scenario: Apply succeeds for initial create table and follow-up column add
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (name TEXT);
      """
    And commit add_id_column with SQL:
      """
      CREATE TABLE people (name TEXT, id INT);
      """
    When I run apply to HEAD
    Then apply should succeed
    And status should show last applied commit add_id_column

  Scenario: Apply can recover after superseded_by override
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (name TEXT);
      """
    And commit add_id_column with SQL:
      """
      CREATE TABLE people (name TEXT, id INT);
      """
    And commit add_age_column with SQL:
      """
      CREATE TABLE people (name TEXT, id INT, age INT);
      """
    When I register override superseded_by for commit init_schema with replacement add_id_column and reason replacement commit has final shape
    And I run apply to HEAD
    Then apply should succeed
    And status should show last applied commit add_age_column

  Scenario: Apply blocks unsafe type narrowing
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (age TEXT);
      """
    And commit narrow_age_type with SQL:
      """
      CREATE TABLE people (age INT);
      """
    When I run apply to HEAD
    Then apply should fail at commit narrow_age_type
    And status should show last applied commit init_schema

  Scenario: Planning detects index creation
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (name TEXT);
      """
    And commit add_name_index with SQL:
      """
      CREATE TABLE people (name TEXT);
      CREATE INDEX idx_people_name ON people(name);
      """
    When I run plan from commit init_schema to HEAD
    Then the plan should include DDL CREATE INDEX idx_people_name ON people(name);

  Scenario: Planning detects unique constraint addition
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE people (email TEXT);
      """
    And commit add_unique_email with SQL:
      """
      CREATE TABLE people (email TEXT, CONSTRAINT uq_people_email UNIQUE (email));
      """
    When I run plan from commit init_schema to HEAD
    Then the plan should include DDL ALTER TABLE people ADD CONSTRAINT uq_people_email UNIQUE (email);

  Scenario: Planning detects foreign key constraint addition
    Given a temporary git repo with schema file schema.sql
    And commit init_schema with SQL:
      """
      CREATE TABLE parent (id INT);
      CREATE TABLE child (parent_id INT);
      """
    And commit add_child_parent_fk with SQL:
      """
      CREATE TABLE parent (id INT);
      CREATE TABLE child (parent_id INT, CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent(id));
      """
    When I run plan from commit init_schema to HEAD
    Then the plan should include DDL ALTER TABLE child ADD CONSTRAINT fk_child_parent FOREIGN KEY (parent_id) REFERENCES parent (id);
