"""Query semantics, strict decoding, and independent reader parity."""
import os
import struct
import pytest
from benchmark.benchmark import benchmark_role, SUPPORTED_ROLES, compare_results
from reader.parser import COPY_SIGNATURE, iter_binary_rows, iter_binary_tuples
from reader.query import QuerySpec, COLUMNS
from reader.snapshot_reader import PreparedReader, read_snapshot, read_snapshot_reference
from reader.policy import UnsupportedPolicyError


def snapshot(path):
    rows = [(7, 'Ålice', 'IT', 75000), (1, 'Denied', 'HR', 75000),
            (5, 'Bob', 'IT', None), (2, 'Ålice', 'IT', 70000),
            (3, 'Ålice', 'IT', 80000), (4, 'Bob', None, 75000)]
    data = COPY_SIGNATURE + struct.pack('!II', 0, 0)
    for row in rows:
        data += struct.pack('!h', 4)
        for index, value in enumerate(row):
            raw = None if value is None else struct.pack('!i', value) if index in (0, 3) else value.encode('utf-8')
            data += struct.pack('!i', -1 if raw is None else len(raw))
            if raw is not None:
                data += raw
    path.write_bytes(data + struct.pack('!h', -1))
    return path


POLICY = dict(type='comparison', column='department', operator='=', value='IT')


def test_order_projection_nulls_and_limit(tmp_path):
    path = snapshot(tmp_path / 'rows.bin')
    query = QuerySpec(('name', 'salary'), 70000, 75000, 'Ålice', 1)
    prepared = PreparedReader(POLICY, query)
    result = prepared.scan(path)
    assert result.rows == [{'name': 'Ålice', 'salary': 70000}]
    assert result.rows == read_snapshot_reference(path, POLICY, query)
    assert (result.scanned, result.denied, result.filtered, result.limited) == (6, 2, 2, 1)
    assert prepared.scan(path) == result
    assert read_snapshot(path, POLICY, QuerySpec(limit=0)) == []


@pytest.mark.parametrize('query', [QuerySpec(), QuerySpec(('salary',)), QuerySpec(exact_name="x' OR true --"),
                                  QuerySpec(minimum_salary=75000), QuerySpec(maximum_salary=70000),
                                  QuerySpec(('department', 'name'), limit=2)])
def test_reference_parity(tmp_path, query):
    path = snapshot(tmp_path / 'rows.bin')
    assert read_snapshot(path, POLICY, query) == read_snapshot_reference(path, POLICY, query)
    assert list(iter_binary_tuples(path)) == [tuple(row[c] for c in COLUMNS) for row in iter_binary_rows(path)]


@pytest.mark.parametrize('options', [dict(columns=()), dict(columns=('salary', 'salary')), dict(columns=('evil',)),
    dict(minimum_salary=10, maximum_salary=9), dict(limit=-1), dict(limit=True), dict(minimum_salary=True),
    dict(minimum_salary=2147483648), dict(exact_name='bad\x00name')])
def test_invalid_queries(options):
    with pytest.raises(ValueError):
        QuerySpec(**options)


def test_all_truncations_and_trailing_data_rejected(tmp_path):
    path = snapshot(tmp_path / 'rows.bin')
    complete = path.read_bytes()
    for length in range(len(complete)):
        path.write_bytes(complete[:length])
        for decoder in (iter_binary_rows, iter_binary_tuples):
            with pytest.raises(ValueError):
                list(decoder(path))
    path.write_bytes(complete + b'junk')
    with pytest.raises(ValueError):
        read_snapshot(path, POLICY, QuerySpec(limit=0))
    # A limit never hides corruption in later records.
    path.write_bytes(complete[:-1])
    with pytest.raises(ValueError):
        read_snapshot(path, POLICY, QuerySpec(limit=1))


def test_whole_policy_validated_even_with_limit_zero(tmp_path):
    path = snapshot(tmp_path / 'rows.bin')
    policy = dict(type='logical', operator='OR', left=dict(type='constant', value=True), right=dict(type='unknown'))
    with pytest.raises(UnsupportedPolicyError):
        read_snapshot(path, policy, QuerySpec(limit=0))


def test_projection_duplicates_are_compared():
    assert not compare_results([{'department': 'IT'}], [{'department': 'IT'}, {'department': 'IT'}]).results_match


@pytest.mark.skipif(not os.getenv('PGPASSWORD') or os.getenv('PGPASSWORD') == 'change_me', reason='No PostgreSQL credentials')
@pytest.mark.parametrize('role', SUPPORTED_ROLES)
@pytest.mark.parametrize('query', [QuerySpec(('salary', 'name'), minimum_salary=70000, maximum_salary=80000, limit=7),
    QuerySpec(('department',), limit=3), QuerySpec(exact_name='Bob'), QuerySpec(exact_name="x' OR true --"),
    QuerySpec(exact_name='No such employee'), QuerySpec(limit=0)])
def test_live_query_parity(role, query, tmp_path):
    result = benchmark_role(role, query=query, snapshot_path=tmp_path / 'export.bin', warmup_runs=0, measured_runs=1)
    assert result['postgres_rows'] == result['reader_rows']
    assert result['reference_match'] and result['correctness'].results_match
    assert result['rows_scanned'] == sum(result[k] for k in ('rows_returned', 'rows_denied', 'rows_filtered', 'rows_limited'))


@pytest.mark.parametrize('kind', ['null_id', 'extension', 'invalid_utf8', 'invalid_integer', 'negative_length', 'flags'])
def test_decoder_edge_formats(tmp_path, kind):
    path = snapshot(tmp_path / 'rows.bin')
    data = path.read_bytes()
    valid = kind in ('null_id', 'extension')
    if kind == 'null_id':
        data = data[:21] + struct.pack('!i', -1) + data[29:]
    elif kind == 'extension':
        data = data[:15] + struct.pack('!I', 3) + b'ext' + data[19:]
    elif kind == 'invalid_utf8':
        data = data[:33] + b'\xff' + data[34:]
    elif kind == 'invalid_integer':
        data = data[:21] + struct.pack('!i', 3) + data[25:]
    elif kind == 'negative_length':
        data = data[:29] + struct.pack('!i', -2) + data[33:]
    else:
        data = data[:11] + struct.pack('!I', 1) + data[15:]
    path.write_bytes(data)
    if valid:
        assert list(iter_binary_tuples(path)) == [tuple(row[c] for c in COLUMNS) for row in iter_binary_rows(path)]
    else:
        for decoder in (iter_binary_rows, iter_binary_tuples):
            with pytest.raises(ValueError):
                list(decoder(path))
