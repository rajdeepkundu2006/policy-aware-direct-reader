from database.policy_ast import (
    PolicyParseError,
    build_policy_map,
    parse_policy_expression,
)


def test_parse_department_policy():
    expression = "(department = 'IT'::text)"

    result = parse_policy_expression(expression)

    assert result == {
        "type": "comparison",
        "column": "department",
        "operator": "=",
        "value": "IT",
    }


def test_parse_salary_policy():
    expression = "(salary >= 70000)"

    result = parse_policy_expression(expression)

    assert result == {
        "type": "comparison",
        "column": "salary",
        "operator": ">=",
        "value": 70000,
    }


def test_parse_and_policy():
    expression = "((department = 'IT'::text) AND (salary >= 70000))"

    result = parse_policy_expression(expression)

    assert result == {
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


def test_parse_or_policy():
    expression = "((department = 'IT'::text) OR (department = 'HR'::text))"

    result = parse_policy_expression(expression)

    assert result == {
        "type": "logical",
        "operator": "OR",
        "left": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "IT",
        },
        "right": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "HR",
        },
    }


def test_build_policy_map():
    policy_rows = [
        {
            "role_name": "it_user",
            "using_expr": "(department = 'IT'::text)",
        },
        {
            "role_name": "hr_user",
            "using_expr": "(department = 'HR'::text)",
        },
        {
            "role_name": "finance_user",
            "using_expr": "(department = 'Finance'::text)",
        },
    ]

    result = build_policy_map(policy_rows)

    assert result == {
        "it_user": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "IT",
        },
        "hr_user": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "HR",
        },
        "finance_user": {
            "type": "comparison",
            "column": "department",
            "operator": "=",
            "value": "Finance",
        },
    }


def test_unsupported_policy_raises_error():
    expression = "(department LIKE '%IT%'::text)"

    try:
        parse_policy_expression(expression)
    except PolicyParseError:
        pass
    else:
        raise AssertionError("Unsupported policy should raise PolicyParseError")