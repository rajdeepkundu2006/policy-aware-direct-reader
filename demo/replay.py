"""Run the real local reader against an archived PostgreSQL baseline."""
import hashlib
import json
from pathlib import Path
from reader.snapshot_reader import read_snapshot
from benchmark.benchmark import compare_results

DEMO_ROOT = Path(__file__).resolve().parent


def load_evidence():
    evidence = json.loads((DEMO_ROOT / 'evidence.json').read_text(encoding='utf-8'))
    snapshot = DEMO_ROOT / 'employees.bin'
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != evidence['snapshot_sha256']:
        raise ValueError('Bundled snapshot does not match the recorded evidence')
    return evidence


def replay_role(role):
    evidence = load_evidence()
    case = evidence['roles'][role]
    reader_rows = read_snapshot(str(DEMO_ROOT / 'employees.bin'), case['policy'])
    correctness = compare_results(case['postgres_rows'], reader_rows)
    return evidence, case, reader_rows, correctness
