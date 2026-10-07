"""Refresh the bundled synthetic demo from actual PostgreSQL measurements."""
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark.benchmark import get_connection, benchmark_role, result_record, SUPPORTED_ROLES


def capture():
    demo=ROOT/'demo'
    demo.mkdir(exist_ok=True)
    roles={}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cur.execute('LOCK TABLE public.employees IN SHARE MODE')
            cur.execute('SELECT e.id,e.name FROM public.employees e LEFT JOIN public.reader_generated_ids g USING(id) WHERE g.id IS NULL ORDER BY e.id')
            originals=cur.fetchall()
            if originals != list(enumerate(['Alice','Bob','Carol','David','Eve','Frank','Grace','Henry','Irene','Jack'],1)):
                raise RuntimeError('Capture only the known synthetic demonstration dataset; original rows have changed.')
            cur.execute('SELECT count(*), count(*) FILTER (WHERE g.id IS NOT NULL), count(*) FILTER (WHERE e.department IS NULL), count(*) FILTER (WHERE e.salary IS NULL) FROM public.employees e LEFT JOIN public.reader_generated_ids g USING(id)')
            total,generated,null_department,null_salary=cur.fetchone()
        for role in SUPPORTED_ROLES:
            r=benchmark_role(role,connection=conn,snapshot_path=demo/'employees.bin',warmup_runs=3,measured_runs=10)
            if not r['correctness'].results_match:
                raise RuntimeError('Do not capture a failed comparison')
            roles[role]=dict(policy=r['policy'],postgres_rows=r['postgres_rows'],
                             measurement=result_record(r),postgres_samples_ms=r['postgres_stats'].samples_ms,
                             reader_samples_ms=r['reader_stats'].samples_ms)
    with (ROOT/'results'/'benchmark_results.csv').open(encoding='utf-8') as file:
        suite=list(csv.DictReader(file))
    for row in suite:
        for key,value in row.items():
            if value in {'True','False'}:
                row[key]=value=='True'
            else:
                try:
                    row[key]=float(value) if '.' in value or 'e' in value.lower() else int(value)
                except ValueError:
                    pass
    evidence=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),
                  summary=dict(total=total,generated=generated,original=len(originals),
                               null_department=null_department,null_salary=null_salary),
                  snapshot_sha256=hashlib.sha256((demo/'employees.bin').read_bytes()).hexdigest(),
                  roles=roles,suite=suite)
    (demo/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    preview=dict(evidence,roles={role:dict(case,postgres_rows=case['postgres_rows'][:12]) for role,case in roles.items()})
    payload=json.dumps(preview).replace('<','\\u003c')
    template=(ROOT/'scripts'/'demo_page.html').read_text(encoding='utf-8')
    (demo/'index.html').write_text(template.replace('__EVIDENCE__',payload),encoding='utf-8')
    print('Captured 3 roles and 27 cases; synthetic snapshot SHA256:',evidence['snapshot_sha256'])

if __name__=='__main__':
    capture()
