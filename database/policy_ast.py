"""Convert supported PostgreSQL RLS expressions into the canonical policy AST."""

import psycopg


class PolicyParseError(Exception):
    """Raised when a PostgreSQL policy expression is unsupported or invalid."""


SUPPORTED_COLUMNS = {"id", "name", "department", "salary"}
SUPPORTED_OPERATORS = {"=", "<", "<=", ">", ">="}


def parse_policy_expression(expression: str) -> dict:
    """Convert one supported PostgreSQL policy expression into the canonical AST."""

    expression = expression.strip()

    # Remove one pair of outer parentheses.
    if expression.startswith("(") and expression.endswith(")"):
        expression = expression[1:-1].strip()

    # Handle AND expressions.
    and_position = _find_logical_operator(expression, "AND")

    if and_position != -1:
        left_expression = expression[:and_position].strip()
        right_expression = expression[and_position + len("AND"):].strip()

        return {
            "type": "logical",
            "operator": "AND",
            "left": parse_policy_expression(left_expression),
            "right": parse_policy_expression(right_expression),
        }

    # Handle OR expressions.
    or_position = _find_logical_operator(expression, "OR")

    if or_position != -1:
        left_expression = expression[:or_position].strip()
        right_expression = expression[or_position + len("OR"):].strip()

        return {
            "type": "logical",
            "operator": "OR",
            "left": parse_policy_expression(left_expression),
            "right": parse_policy_expression(right_expression),
        }

    # Handle department equality.
    prefix = "department = '"
    suffix = "'::text"

    if expression.startswith(prefix) and expression.endswith(suffix):
        value = expression[len(prefix):-len(suffix)]

        if not value:
            raise PolicyParseError("Policy value cannot be empty")

        return {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": value,
        }

    # Handle salary comparisons.
    salary_operators = ["<=", ">=", "=", "<", ">"]

    for operator in salary_operators:
        prefix = f"salary {operator} "

        if expression.startswith(prefix):
            value_text = expression[len(prefix):].strip()

            try:
                value = int(value_text)
            except ValueError:
                raise PolicyParseError(
                    f"Invalid numeric value: {value_text}"
                )

            return {
                "type": "comparison",
                "column": "salary",
                "operator": operator,
                "value": value,
            }

    raise PolicyParseError(
        f"Unsupported policy expression: {expression}"
    )


def build_policy_map(policy_rows: list[dict]) -> dict:
    """Convert extracted PostgreSQL policy rows into a role-to-AST map."""

    policies = {}

    for row in policy_rows:
        role_name = row.get("role_name")
        using_expr = row.get("using_expr")

        if not role_name:
            raise PolicyParseError("Policy row is missing role_name")

        if not using_expr:
            raise PolicyParseError(
                f"Policy for role {role_name} is missing using_expr"
            )

        policies[role_name] = parse_policy_expression(using_expr)

    return policies


def extract_policies_from_database(
    host: str = "localhost",
    port: int = 5432,
    database: str = "direct_reader_db",
    user: str = "postgres",
    password: str | None = None,
) -> dict:
    """Extract PostgreSQL RLS policies and convert them into canonical ASTs."""

    query = """
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
    """

    connection_kwargs = {
        "host": host,
        "port": port,
        "dbname": database,
        "user": user,
    }

    if password is not None:
        connection_kwargs["password"] = password

    with psycopg.connect(**connection_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)

            policy_rows = [
                {
                    "role_name": row[2],
                    "using_expr": row[3],
                }
                for row in cursor.fetchall()
            ]

    return build_policy_map(policy_rows)


def _find_logical_operator(expression: str, operator: str) -> int:
    """Find a logical operator at the current expression level."""

    depth = 0
    i = 0

    while i < len(expression):
        character = expression[i]

        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1

        if depth == 0 and expression.startswith(operator, i):
            return i

        i += 1

    return -1