-- Reference query for extracting PostgreSQL RLS policy definitions.
-- The Python implementation will use a parameterized version of this query.

SELECT
    polname,
    polcmd,
    polroles,
    pg_get_expr(polqual, polrelid) AS using_expr
FROM pg_policy
WHERE polrelid = 'employees'::regclass;
