-- database/01_schema.sql

-- =========================================================
-- Employees table
-- =========================================================

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT,
    salary INTEGER
);

-- =========================================================
-- PostgreSQL roles
-- =========================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'it_user'
    ) THEN
        CREATE ROLE it_user;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'hr_user'
    ) THEN
        CREATE ROLE hr_user;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'finance_user'
    ) THEN
        CREATE ROLE finance_user;
    END IF;
END
$$;

-- =========================================================
-- Demonstration data
-- =========================================================

INSERT INTO employees (id, name, department, salary)
VALUES
    (1, 'Alice', 'HR',       50000),
    (2, 'Bob',   'IT',       70000),
    (3, 'Carol', 'HR',       55000),
    (4, 'David', 'Finance',  80000),
    (5, 'Eve',   'IT',       75000),
    (6, 'Frank', 'Finance',  72000),
    (7, 'Grace', 'HR',       62000),
    (8, 'Henry', 'IT',       68000),
    (9, 'Irene', 'Finance',  76000),
    (10, 'Jack', 'IT',       71000)
ON CONFLICT (id) DO NOTHING;

-- =========================================================
-- Permissions
-- =========================================================

GRANT SELECT ON employees TO it_user;
GRANT SELECT ON employees TO hr_user;
GRANT SELECT ON employees TO finance_user;

-- Existing installations also need nullable policy attributes for experiments.
ALTER TABLE employees ALTER COLUMN department DROP NOT NULL;
ALTER TABLE employees ALTER COLUMN salary DROP NOT NULL;
