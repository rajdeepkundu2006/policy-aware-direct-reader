-- database/03_policy_extraction.sql

-- Extract the RLS policies defined by PostgreSQL for employees.
-- The policy expression is reconstructed using pg_get_expr().
-- Role OIDs are converted to PostgreSQL role names.

SELECT
    p.polname,
    p.polcmd,
    r.rolname AS role_name,
    pg_get_expr(p.polqual, p.polrelid) AS using_expr
FROM pg_policy AS p
JOIN LATERAL unnest(p.polroles) AS policy_role(role_oid)
    ON TRUE
JOIN pg_roles AS r
    ON r.oid = policy_role.role_oid
WHERE p.polrelid = 'employees'::regclass
ORDER BY p.polname;
