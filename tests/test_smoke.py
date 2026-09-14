"""Tests for the direct snapshot reader."""

import struct

from reader.snapshot_reader import read_snapshot


COPY_SIGNATURE = b"PGCOPY\n\xff\r\n\x00"


def create_test_snapshot(path):
    rows = [
        (1, "Alice", "HR", 50000),
        (2, "Bob", "IT", 70000),
        (3, "Carol", "HR", 55000),
        (4, "David", "Finance", 80000),
        (5, "Eve", "IT", 75000),
    ]

    with open(path, "wb") as f:
        f.write(COPY_SIGNATURE)
        f.write(struct.pack("!I", 0))
        f.write(struct.pack("!I", 0))

        for row in rows:
            f.write(struct.pack("!h", 4))

            values = [
                struct.pack("!i", row[0]),
                row[1].encode("utf-8"),
                row[2].encode("utf-8"),
                struct.pack("!i", row[3]),
            ]

            for value in values:
                f.write(struct.pack("!i", len(value)))
                f.write(value)

        f.write(struct.pack("!h", -1))


def test_reader_filters_it_rows(tmp_path):
    snapshot = tmp_path / "employees.bin"
    create_test_snapshot(snapshot)

    policy = {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT",
    }

    rows = read_snapshot(str(snapshot), policy)

    assert rows == [
        {
            "id": 2,
            "name": "Bob",
            "department": "IT",
            "salary": 70000,
        },
        {
            "id": 5,
            "name": "Eve",
            "department": "IT",
            "salary": 75000,
        },
    ]


def test_reader_filters_salary(tmp_path):
    snapshot = tmp_path / "employees.bin"
    create_test_snapshot(snapshot)

    policy = {
        "type": "comparison",
        "column": "salary",
        "operator": ">=",
        "value": 70000,
    }

    rows = read_snapshot(str(snapshot), policy)

    assert len(rows) == 3
    assert [row["name"] for row in rows] == ["Bob", "David", "Eve"]


def test_reader_supports_and_policy(tmp_path):
    snapshot = tmp_path / "employees.bin"
    create_test_snapshot(snapshot)

    policy = {
        "type": "logical",
        "operator": "AND",
        "left": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "IT",
        },
        "right": {
            "type": "comparison",
            "column": "salary",
            "operator": ">=",
            "value": 70000,
        },
    }

    rows = read_snapshot(str(snapshot), policy)

    assert [row["name"] for row in rows] == ["Bob", "Eve"]


def test_null_value_is_not_allowed(tmp_path):
    snapshot = tmp_path / "employees.bin"

    with open(snapshot, "wb") as f:
        f.write(COPY_SIGNATURE)
        f.write(struct.pack("!I", 0))
        f.write(struct.pack("!I", 0))

        f.write(struct.pack("!h", 4))

        values = [
            struct.pack("!i", 1),
            b"Alice",
            None,
            struct.pack("!i", 50000),
        ]

        for value in values:
            if value is None:
                f.write(struct.pack("!i", -1))
            else:
                f.write(struct.pack("!i", len(value)))
                f.write(value)

        f.write(struct.pack("!h", -1))

    policy = {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT",
    }

    rows = read_snapshot(str(snapshot), policy)

    assert rows == []


def test_reader_supports_or_policy(tmp_path):
    snapshot = tmp_path / "employees.bin"
    create_test_snapshot(snapshot)

    policy = {
        "type": "logical",
        "operator": "OR",
        "left": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "HR",
        },
        "right": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "Finance",
        },
    }

    rows = read_snapshot(str(snapshot), policy)

    assert [row["name"] for row in rows] == [
        "Alice",
        "Carol",
        "David",
    ]


def test_unsupported_operator_is_rejected(tmp_path):
    snapshot = tmp_path / "employees.bin"
    create_test_snapshot(snapshot)

    policy = {
        "type": "comparison",
        "column": "department",
        "operator": "!=",
        "value": "IT",
    }

    from reader.policy import UnsupportedPolicyError

    try:
        read_snapshot(str(snapshot), policy)
        assert False
    except UnsupportedPolicyError:
        pass


def test_invalid_snapshot_is_rejected(tmp_path):
    snapshot = tmp_path / "invalid.bin"

    snapshot.write_bytes(b"not a postgres snapshot")

    policy = {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT",
    }

    try:
        read_snapshot(str(snapshot), policy)
        assert False
    except ValueError:
        pass