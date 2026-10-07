"""Validated query requests shared by PostgreSQL and the snapshot reader."""
from dataclasses import dataclass, asdict
from psycopg import sql

COLUMNS = ('id', 'name', 'department', 'salary')


@dataclass(frozen=True)
class QuerySpec:
    columns: tuple[str, ...] = COLUMNS
    minimum_salary: int | None = None
    maximum_salary: int | None = None
    exact_name: str | None = None
    limit: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'columns', tuple(self.columns))
        if not self.columns or len(set(self.columns)) != len(self.columns) or any(c not in COLUMNS for c in self.columns):
            raise ValueError('Select at least one valid column, without duplicates.')
        for value in (self.minimum_salary, self.maximum_salary):
            if value is not None and (type(value) is not int or not -2147483648 <= value <= 2147483647):
                raise ValueError('Salary bounds must be PostgreSQL INTEGER values.')
        if self.minimum_salary is not None and self.maximum_salary is not None and self.minimum_salary > self.maximum_salary:
            raise ValueError('Minimum salary must not exceed maximum salary.')
        if self.exact_name is not None and (type(self.exact_name) is not str or '\x00' in self.exact_name):
            raise ValueError('Exact name must be text without a NUL character.')
        if self.limit is not None and (type(self.limit) is not int or not 0 <= self.limit <= 9223372036854775807):
            raise ValueError('Row limit must be a nonnegative PostgreSQL BIGINT.')

    def as_dict(self):
        return asdict(self)

    def conditions(self):
        return [(column, operator, value) for column, operator, value in (
            ('salary', '>=', self.minimum_salary), ('salary', '<=', self.maximum_salary),
            ('name', '=', self.exact_name)) if value is not None]

    def policy(self):
        result = {'type': 'constant', 'value': True}
        for column, operator, value in self.conditions():
            node = dict(type='comparison', column=column, operator=operator, value=value)
            result = dict(type='logical', operator='AND', left=result, right=node)
        return result

    def sql(self, *, literals=False):
        """Identifiers are allowlisted; all user values are bound parameters."""
        query = sql.SQL('SELECT {} FROM public.employees').format(sql.SQL(', ').join(map(sql.Identifier, self.columns)))
        clauses, params = [], []
        for column, operator, value in self.conditions():
            clauses.append(sql.SQL('{} {} {}').format(sql.Identifier(column), sql.SQL(operator),
                                                     sql.Literal(value) if literals else sql.Placeholder()))
            params.append(value)
        if clauses:
            query += sql.SQL(' WHERE ') + sql.SQL(' AND ').join(clauses)
        query += sql.SQL(' ORDER BY id')
        if self.limit is not None:
            query += sql.SQL(' LIMIT {}').format(sql.Literal(self.limit) if literals else sql.Placeholder())
            params.append(self.limit)
        return query, tuple(params)
