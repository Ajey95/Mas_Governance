"""One schema check shared by guards and trace measurements."""

from __future__ import annotations

from typing import Any


def parameter_issues(schema: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    if not schema:
        return {"extra_keys": [], "missing_keys": [], "invalid_types": {}, "invalid_values": {}}
    allowed = set(schema.get("allowed_keys", []))
    required = set(schema.get("required_keys", []))
    actual = set(parameters)
    properties = schema.get("properties", {})
    type_checks = {
        "string": lambda value: isinstance(value, str),
        "boolean": lambda value: isinstance(value, bool),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
    }
    invalid_types = {
        key: expected
        for key, value in parameters.items() if key in properties
        for expected in [properties[key].get("type")]
        if expected in type_checks and not type_checks[expected](value)
    }
    invalid_values: dict[str, str] = {}
    for key, value in parameters.items():
        rule = properties.get(key, {})
        if key in invalid_types or not isinstance(rule, dict):
            continue
        if "const" in rule and value != rule["const"]:
            invalid_values[key] = "const"
        elif "enum" in rule and value not in rule["enum"]:
            invalid_values[key] = "enum"
        elif isinstance(value, str) and "max_length" in rule and len(value) > rule["max_length"]:
            invalid_values[key] = "max_length"
    return {
        "extra_keys": sorted(actual - allowed),
        "missing_keys": sorted(required - actual),
        "invalid_types": invalid_types,
        "invalid_values": invalid_values,
    }
