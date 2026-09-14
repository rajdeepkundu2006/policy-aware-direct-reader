"""Policy representation and evaluation."""


class UnsupportedPolicyError(Exception):
    """Raised when a PostgreSQL policy is outside the supported subset."""


def extract_policies(connection, table_name: str):
    """TODO: read supported RLS policies from pg_policy."""
    raise NotImplementedError


def evaluate_policy(row: dict, policy) -> bool:
    """TODO: evaluate a supported policy using SQL-compatible NULL semantics."""
    raise NotImplementedError
