-- database/02_rls_policies.sql

-- =========================================================
-- Enable Row-Level Security
-- =========================================================

ALTER TABLE employees ENABLE ROW LEVEL SECURITY;

-- =========================================================
-- IT policy
-- =========================================================

DROP POLICY IF EXISTS employees_it_policy ON employees;

CREATE POLICY employees_it_policy
ON employees
FOR SELECT
TO it_user
USING (department = 'IT');

-- =========================================================
-- HR policy
-- =========================================================

DROP POLICY IF EXISTS employees_hr_policy ON employees;

CREATE POLICY employees_hr_policy
ON employees
FOR SELECT
TO hr_user
USING (department = 'HR');

-- =========================================================
-- Finance policy
-- =========================================================

DROP POLICY IF EXISTS employees_finance_policy ON employees;

CREATE POLICY employees_finance_policy
ON employees
FOR SELECT
TO finance_user
USING (department = 'Finance');
