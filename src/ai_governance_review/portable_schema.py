"""Standard-library validation for the JSON Schema subset used by this project."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

_SUPPORTED_SCHEMA_KEYWORDS = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "allOf",
    "const",
    "default",
    "enum",
    "format",
    "items",
    "maxLength",
    "minItems",
    "minLength",
    "minProperties",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "title",
    "type",
    "uniqueItems",
}


@dataclass(frozen=True)
class ValidationIssue:
    """One portable schema-validation issue."""

    absolute_path: tuple[object, ...]
    message: str


def iter_errors(instance: object, schema: dict[str, object]) -> list[ValidationIssue]:
    """Validate against the closed schema subset bundled with the portable skill."""

    _ensure_supported_schema(schema)
    return _validate(instance, schema, schema, ())


def _ensure_supported_schema(schema: dict[str, object]) -> None:
    unknown = sorted(set(schema) - _SUPPORTED_SCHEMA_KEYWORDS)
    if unknown:
        raise ValueError(f"unsupported schema keyword {unknown[0]!r}")

    for container_name in ("$defs", "properties"):
        container = schema.get(container_name)
        if isinstance(container, dict):
            for child in container.values():
                if isinstance(child, dict):
                    _ensure_supported_schema(child)
    for child_name in ("additionalProperties", "items"):
        child = schema.get(child_name)
        if isinstance(child, dict):
            _ensure_supported_schema(child)
    for collection_name in ("allOf", "oneOf"):
        collection = schema.get(collection_name)
        if isinstance(collection, list):
            for child in collection:
                if isinstance(child, dict):
                    _ensure_supported_schema(child)


def _validate(
    instance: object,
    schema: dict[str, object],
    root_schema: dict[str, object],
    path: tuple[object, ...],
) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []

    reference = schema.get("$ref")
    if isinstance(reference, str):
        resolved = _resolve_reference(reference, root_schema)
        if resolved is None:
            return [ValidationIssue(path, f"unresolved schema reference {reference!r}")]
        errors.extend(_validate(instance, resolved, root_schema, path))

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for child in all_of:
            if isinstance(child, dict):
                errors.extend(_validate(instance, child, root_schema, path))

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = sum(
            not _validate(instance, child, root_schema, path)
            for child in one_of
            if isinstance(child, dict)
        )
        if matches != 1:
            errors.append(ValidationIssue(path, "value must match exactly one allowed schema"))

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _matches_type(instance, expected_type):
        return errors + [ValidationIssue(path, f"value must be of type {expected_type}")]

    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(ValidationIssue(path, f"value must equal {schema['const']!r}"))

    allowed = schema.get("enum")
    if isinstance(allowed, list) and not any(_json_equal(instance, item) for item in allowed):
        errors.append(ValidationIssue(path, f"value must be one of {allowed!r}"))

    if isinstance(instance, dict):
        errors.extend(_validate_object(instance, schema, root_schema, path))
    elif isinstance(instance, list):
        errors.extend(_validate_array(instance, schema, root_schema, path))
    elif isinstance(instance, str):
        errors.extend(_validate_string(instance, schema, path))

    return errors


def _resolve_reference(reference: str, root_schema: dict[str, object]) -> dict[str, object] | None:
    if not reference.startswith("#/"):
        return None
    current: object = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, dict) else None


def _matches_type(instance: object, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(instance, dict)
    if expected_type == "array":
        return isinstance(instance, list)
    if expected_type == "string":
        return isinstance(instance, str)
    if expected_type == "boolean":
        return isinstance(instance, bool)
    if expected_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected_type == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected_type == "null":
        return instance is None
    return False


def _json_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _validate_object(
    instance: dict[object, object],
    schema: dict[str, object],
    root_schema: dict[str, object],
    path: tuple[object, ...],
) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []
    required = schema.get("required", [])
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in instance:
                errors.append(ValidationIssue(path, f"required property {key!r} is missing"))

    minimum = schema.get("minProperties")
    if isinstance(minimum, int) and len(instance) < minimum:
        errors.append(ValidationIssue(path, f"object must have at least {minimum} properties"))

    properties = schema.get("properties", {})
    property_schemas = properties if isinstance(properties, dict) else {}
    for key, value in instance.items():
        child_schema = property_schemas.get(key)
        if isinstance(child_schema, dict):
            errors.extend(_validate(value, child_schema, root_schema, (*path, key)))

    additional = schema.get("additionalProperties", True)
    for key, value in instance.items():
        if key in property_schemas:
            continue
        if additional is False:
            errors.append(
                ValidationIssue((*path, key), f"additional property {key!r} is not allowed")
            )
        elif isinstance(additional, dict):
            errors.extend(_validate(value, additional, root_schema, (*path, key)))
    return errors


def _validate_array(
    instance: list[object],
    schema: dict[str, object],
    root_schema: dict[str, object],
    path: tuple[object, ...],
) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []
    minimum = schema.get("minItems")
    if isinstance(minimum, int) and len(instance) < minimum:
        errors.append(ValidationIssue(path, f"array must have at least {minimum} items"))
    if schema.get("uniqueItems") is True:
        seen: set[str] = set()
        for index, item in enumerate(instance):
            canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if canonical in seen:
                errors.append(ValidationIssue((*path, index), "array items must be unique"))
            seen.add(canonical)
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(instance):
            errors.extend(_validate(item, item_schema, root_schema, (*path, index)))
    return errors


def _validate_string(
    instance: str,
    schema: dict[str, object],
    path: tuple[object, ...],
) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []
    minimum = schema.get("minLength")
    if isinstance(minimum, int) and len(instance) < minimum:
        errors.append(ValidationIssue(path, f"string must contain at least {minimum} characters"))
    maximum = schema.get("maxLength")
    if isinstance(maximum, int) and len(instance) > maximum:
        errors.append(ValidationIssue(path, f"string must contain at most {maximum} characters"))
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.search(pattern, instance) is None:
        errors.append(ValidationIssue(path, f"string does not match pattern {pattern!r}"))
    format_name = schema.get("format")
    if format_name == "date" and not _valid_date(instance):
        errors.append(ValidationIssue(path, "string is not a valid date"))
    elif format_name == "date-time" and not _valid_datetime(instance):
        errors.append(ValidationIssue(path, "string is not a valid date-time"))
    return errors


def _valid_date(value: str) -> bool:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_datetime(value: str) -> bool:
    if (
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
            value,
        )
        is None
    ):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return False
    return True
