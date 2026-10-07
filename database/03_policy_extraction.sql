-- Inspect explicit policy assignments, including PUBLIC and command/composition.
-- Runtime extraction in policy_ast.py additionally resolves inherited privileges.
SELECT p.polname, p.polcmd, p.polpermissive,
       CASE WHEN assigned.role_oid = 0 THEN 'PUBLIC' ELSE r.rolname END AS role_name,
       COALESCE(pg_get_expr(p.polqual, p.polrelid), 'true') AS using_expr
FROM pg_policy p
CROSS JOIN LATERAL unnest(p.polroles) AS assigned(role_oid)
LEFT JOIN pg_roles r ON r.oid = assigned.role_oid
WHERE p.polrelid = 'public.employees'::regclass
ORDER BY p.polname;
