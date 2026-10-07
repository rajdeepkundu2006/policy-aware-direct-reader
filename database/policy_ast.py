"""Parse the restricted SQL grammar and compose PostgreSQL SELECT policies."""
import re
import psycopg

class PolicyParseError(ValueError):
    pass

SUPPORTED_COLUMNS = {'id', 'name', 'department', 'salary'}
SUPPORTED_OPERATORS = {'=', '<', '<=', '>', '>='}
ROLES = ('it_user', 'hr_user', 'finance_user')
TOKEN = re.compile(r"\s*(?:(?P<string>'(?:''|[^'])*')|(?P<number>-?\d+)|(?P<cast>::)|(?P<op><=|>=|=|<|>)|(?P<paren>[()])|(?P<word>[A-Za-z_][A-Za-z_0-9]*))")

def logical(operator, left, right):
    return dict(type='logical', operator=operator, left=left, right=right)

def constant(value):
    return dict(type='constant', value=value)

def parse_policy_expression(expression: str) -> dict:
    tokens = []
    remaining = expression.strip()
    while remaining:
        match = TOKEN.match(remaining)
        if not match:
            raise PolicyParseError('Unsupported token in policy expression')
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        remaining = remaining[match.end():]
    position = 0

    def peek(value=None):
        return position < len(tokens) and (value is None or tokens[position][1].upper() == value)

    def take():
        nonlocal position
        if not peek():
            raise PolicyParseError('Incomplete policy expression')
        result = tokens[position]
        position += 1
        return result

    def atom():
        if peek('('):
            take()
            result = disjunction()
            if not peek(')'):
                raise PolicyParseError('Unbalanced policy parentheses')
            take()
            return result
        kind, column = take()
        if kind == 'word' and column.lower() in {'true', 'false'}:
            return constant(column.lower() == 'true')
        if kind != 'word' or column not in SUPPORTED_COLUMNS:
            raise PolicyParseError('Unsupported policy column or function')
        kind, operator = take()
        if kind != 'op' or operator not in SUPPORTED_OPERATORS:
            raise PolicyParseError('Unsupported comparison operator')
        kind, value = take()
        if kind == 'string' and column in {'name', 'department'}:
            value = value[1:-1].replace("''", "'")
            cast_type = 'text'
        elif kind == 'number' and column in {'id', 'salary'}:
            value = int(value)
            cast_type = 'integer'
        elif kind == 'word' and value.upper() == 'NULL':
            value = None
            cast_type = 'text' if column in {'name', 'department'} else 'integer'
        else:
            raise PolicyParseError('Policy literal does not match column type')
        if peek('::'):
            take()
            if take()[1].lower() != cast_type:
                raise PolicyParseError('Unsupported policy cast')
        if column in {'name', 'department'} and operator != '=':
            raise PolicyParseError('Text ranges require collation support; only equality is supported')
        return dict(type='comparison', column=column, operator=operator, value=value)

    def conjunction():
        result = atom()
        while peek('AND'):
            take()
            result = logical('AND', result, atom())
        return result

    def disjunction():
        result = conjunction()
        while peek('OR'):
            take()
            result = logical('OR', result, conjunction())
        return result

    result = disjunction()
    if position != len(tokens):
        raise PolicyParseError('Unexpected trailing policy tokens')
    return result

def build_policy_map(policy_rows: list[dict]) -> dict:
    grouped = {}
    for row in policy_rows:
        role = row.get('role_name')
        if not role:
            raise PolicyParseError('Policy row is missing role_name')
        if row.get('polcmd', 'r') not in {'r', '*'}:
            continue
        expression = row.get('using_expr')
        if not expression:
            raise PolicyParseError(f'Policy for {role} is missing using_expr')
        grouped.setdefault(role, [[], []])[0 if row.get('permissive', True) else 1].append(parse_policy_expression(expression))
    result = {}
    for role, (permissive, restrictive) in grouped.items():
        combined = permissive[0] if permissive else constant(False)
        for policy in permissive[1:]:
            combined = logical('OR', combined, policy)
        for policy in restrictive:
            combined = logical('AND', combined, policy)
        result[role] = combined
    return result

def extract_policies_from_connection(connection) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("""SELECT a.attname, format_type(a.atttypid, a.atttypmod),
                                 COALESCE(c.collisdeterministic, true)
                          FROM pg_attribute a LEFT JOIN pg_collation c ON c.oid=a.attcollation
                          WHERE a.attrelid='public.employees'::regclass
                            AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""")
        schema = cursor.fetchall()
        if [(r[0], r[1]) for r in schema] != [('id', 'integer'), ('name', 'text'), ('department', 'text'), ('salary', 'integer')]:
            raise PolicyParseError('Snapshot reader requires the exact four-column employees schema')
        if not all(r[2] for r in schema):
            raise PolicyParseError('Nondeterministic text collations are unsupported')
        cursor.execute('SHOW server_encoding')
        if cursor.fetchone()[0] != 'UTF8':
            raise PolicyParseError('Snapshot reader requires UTF8 server encoding')
        cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.employees'::regclass")
        if not cursor.fetchone()[0]:
            raise PolicyParseError('RLS must be enabled on public.employees')
        cursor.execute("""
            SELECT target.rolname, p.polcmd, p.polpermissive,
                   COALESCE(pg_get_expr(p.polqual, p.polrelid), 'true')
            FROM pg_policy p CROSS JOIN pg_roles target
            WHERE p.polrelid = 'public.employees'::regclass
              AND target.rolname = ANY(%s)
              AND p.polcmd IN ('r', '*')
              AND EXISTS (SELECT 1 FROM unnest(p.polroles) AS assigned(oid)
                          WHERE CASE WHEN assigned.oid = 0 THEN true
                                ELSE pg_has_role(target.oid, assigned.oid, 'USAGE') END)
            ORDER BY target.rolname, p.polname
        """, (list(ROLES),))
        rows = [dict(role_name=r[0], polcmd=r[1], permissive=r[2], using_expr=r[3]) for r in cursor.fetchall()]
        cursor.execute("""SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)
                          AND (rolsuper OR rolbypassrls OR oid =
                              (SELECT relowner FROM pg_class WHERE oid='public.employees'::regclass))""", (list(ROLES),))
        if cursor.fetchone():
            raise PolicyParseError('Demo roles must not own employees or bypass RLS')
    policies = build_policy_map(rows)
    return {role: policies.get(role, constant(False)) for role in ROLES}

def extract_policies_from_database(host='localhost', port=5432, database='direct_reader_db', user='postgres', password=None):
    with psycopg.connect(host=host, port=port, dbname=database, user=user, password=password) as connection:
        return extract_policies_from_connection(connection)
