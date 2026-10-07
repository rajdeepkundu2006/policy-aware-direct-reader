"""Optimized snapshot execution and an independent reference reader."""
from dataclasses import dataclass
from reader.parser import iter_binary_rows, iter_binary_tuples
from reader.policy import compile_policy, evaluate_policy, validate_policy
from reader.query import COLUMNS, QuerySpec


@dataclass
class ScanResult:
    rows: list[dict]
    scanned: int
    denied: int
    filtered: int
    limited: int


class PreparedReader:
    """One validated policy/query plan, reusable across timed scans."""
    def __init__(self, policy, query=None):
        self.query = query or QuerySpec()
        self.authorized = compile_policy(policy)
        self.matches = compile_policy(self.query.policy())
        self.indexes = tuple(COLUMNS.index(c) for c in self.query.columns)

    def scan(self, snapshot_path):
        rows = []
        scanned = denied = filtered = 0
        authorized, matches = self.authorized, self.matches
        for row in iter_binary_tuples(snapshot_path):
            scanned += 1
            if not authorized(row):
                denied += 1
            elif not matches(row):
                filtered += 1
            else:
                rows.append(row)
        rows.sort(key=lambda row: (row[0] is None, row[0]))
        eligible = len(rows)
        if self.query.limit is not None:
            rows = rows[:self.query.limit]
        output = [dict(zip(self.query.columns, (row[i] for i in self.indexes))) for row in rows]
        return ScanResult(output, scanned, denied, filtered, eligible - len(output))


def read_snapshot(snapshot_path: str, policy: dict, query: QuerySpec | None = None) -> list[dict]:
    return PreparedReader(policy, query).scan(snapshot_path).rows


def read_snapshot_reference(snapshot_path: str, policy: dict, query: QuerySpec | None = None) -> list[dict]:
    """Original decoder and recursive evaluator retained for verification."""
    query = query or QuerySpec()
    validate_policy(policy)
    condition = query.policy()
    rows = [row for row in iter_binary_rows(snapshot_path)
            if evaluate_policy(row, policy) and evaluate_policy(row, condition)]
    rows.sort(key=lambda row: (row['id'] is None, row['id']))
    if query.limit is not None:
        rows = rows[:query.limit]
    return [{column: row[column] for column in query.columns} for row in rows]
