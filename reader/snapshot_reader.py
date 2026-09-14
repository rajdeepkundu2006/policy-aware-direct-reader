"""Direct snapshot reader."""

from reader.parser import iter_binary_rows
from reader.policy import evaluate_policy


def read_snapshot(snapshot_path: str, policy: dict) -> list[dict]:
    """Read a frozen PostgreSQL binary snapshot and apply a policy."""

    results = []

    for row in iter_binary_rows(snapshot_path):
        if evaluate_policy(row, policy):
            results.append(row)

    return results