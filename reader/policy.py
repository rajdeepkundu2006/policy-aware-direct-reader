"""Policy representation and evaluation."""


class UnsupportedPolicyError(Exception):
    """Raised when a policy is outside the supported subset."""


SUPPORTED_COLUMNS = {"id", "name", "department", "salary"}
SUPPORTED_COMPARISON_OPERATORS = {"=", "<", "<=", ">", ">="}
SUPPORTED_LOGICAL_OPERATORS = {"AND", "OR"}


def compile_policy(policy):
    """Validate all branches once and bind tuple indexes and operators."""
    import operator
    from reader.query import COLUMNS
    validate_policy(policy)
    operations = {'=': operator.eq, '<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}
    def build(node):
        if node['type'] == 'constant':
            value = node['value']
            return lambda row: value
        if node['type'] == 'comparison':
            index, expected = COLUMNS.index(node['column']), node['value']
            compare = operations[node['operator']]
            if expected is None:
                return lambda row: False
            return lambda row: row[index] is not None and compare(row[index], expected)
        left, right = build(node['left']), build(node['right'])
        if node['operator'] == 'AND':
            return lambda row: left(row) and right(row)
        return lambda row: left(row) or right(row)
    return build(policy)


def validate_policy(policy):
    """Validate every branch before any rows are released."""
    if not isinstance(policy, dict):
        raise UnsupportedPolicyError('Policy must be a dictionary')
    kind = policy.get('type')
    if kind == 'constant' and type(policy.get('value')) is bool:
        return
    if kind == 'comparison':
        column = policy.get('column')
        value = policy.get('value')
        if column not in SUPPORTED_COLUMNS or policy.get('operator') not in SUPPORTED_COMPARISON_OPERATORS:
            raise UnsupportedPolicyError('Unsupported comparison')
        if column in {'name', 'department'} and policy['operator'] != '=':
            raise UnsupportedPolicyError('Text ranges require collation support')
        expected_type = int if column in {'id', 'salary'} else str
        if value is not None and type(value) is not expected_type:
            raise UnsupportedPolicyError('Policy literal does not match column type')
        return
    if kind == 'logical' and policy.get('operator') in SUPPORTED_LOGICAL_OPERATORS:
        validate_policy(policy.get('left'))
        validate_policy(policy.get('right'))
        return
    raise UnsupportedPolicyError('Unsupported policy structure')


def evaluate_policy(row: dict, policy: dict) -> bool:
    """Evaluate a supported policy using SQL-compatible NULL semantics."""

    if not isinstance(policy, dict):
        raise UnsupportedPolicyError("Policy must be a dictionary")

    policy_type = policy.get("type")

    if policy_type == 'constant':
        return policy['value']

    if policy_type == "comparison":
        return _evaluate_comparison(row, policy)

    if policy_type == "logical":
        return _evaluate_logical(row, policy)

    raise UnsupportedPolicyError(
        f"Unsupported policy type: {policy_type}"
    )


def _evaluate_comparison(row: dict, policy: dict) -> bool:
    column = policy.get("column")
    operator = policy.get("operator")
    expected = policy.get("value")

    if column not in SUPPORTED_COLUMNS:
        raise UnsupportedPolicyError(
            f"Unsupported policy column: {column}"
        )

    if operator not in SUPPORTED_COMPARISON_OPERATORS:
        raise UnsupportedPolicyError(
            f"Unsupported comparison operator: {operator}"
        )

    if column not in row:
        raise UnsupportedPolicyError(
            f"Column {column} is missing from row"
        )

    actual = row[column]

    # SQL comparisons involving NULL produce UNKNOWN.
    # UNKNOWN is not selected by a WHERE condition.
    if actual is None or expected is None:
        return False

    if operator == "=":
        return actual == expected

    if operator == "<":
        return actual < expected

    if operator == "<=":
        return actual <= expected

    if operator == ">":
        return actual > expected

    if operator == ">=":
        return actual >= expected

    raise UnsupportedPolicyError(
        f"Unsupported comparison operator: {operator}"
    )


def _evaluate_logical(row: dict, policy: dict) -> bool:
    operator = policy.get("operator")
    left = policy.get("left")
    right = policy.get("right")

    if operator not in SUPPORTED_LOGICAL_OPERATORS:
        raise UnsupportedPolicyError(
            f"Unsupported logical operator: {operator}"
        )

    if not isinstance(left, dict) or not isinstance(right, dict):
        raise UnsupportedPolicyError(
            "Logical policy requires left and right policies"
        )

    if operator == "AND":
        return evaluate_policy(row, left) and evaluate_policy(row, right)

    if operator == "OR":
        return evaluate_policy(row, left) or evaluate_policy(row, right)

    raise UnsupportedPolicyError(
        f"Unsupported logical operator: {operator}"
    )
