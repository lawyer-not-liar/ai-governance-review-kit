import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ai_governance_review.analysis import analyze_review
from ai_governance_review.portable_schema import iter_errors

ROOT = Path(__file__).parents[1]


def test_portable_schema_validates_nested_object_composition() -> None:
    schema = {
        "$defs": {
            "leaf": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string", "minLength": 2}},
                "additionalProperties": False,
            }
        },
        "allOf": [
            {"$ref": "#/$defs/leaf"},
            {"required": ["name"]},
        ],
    }

    assert iter_errors({"name": "ok"}, schema) == []
    errors = iter_errors({"name": "x", "extra": True}, schema)

    assert {(error.absolute_path, error.message) for error in errors} == {
        (("name",), "string must contain at least 2 characters"),
        (("extra",), "additional property 'extra' is not allowed"),
    }


def test_portable_schema_enforces_exactly_one_composed_branch() -> None:
    schema = {
        "oneOf": [
            {
                "type": "object",
                "required": ["yes"],
                "properties": {"yes": {"const": True}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["no"],
                "properties": {"no": {"const": True}},
                "additionalProperties": False,
            },
        ]
    }

    assert iter_errors({"yes": True}, schema) == []
    assert iter_errors({}, schema)[0].message == "value must match exactly one allowed schema"
    assert iter_errors({"yes": True, "no": True}, schema)[0].message == (
        "value must match exactly one allowed schema"
    )


def test_portable_schema_validates_array_constraints_and_item_paths() -> None:
    schema = {
        "type": "array",
        "minItems": 2,
        "uniqueItems": True,
        "items": {"type": "string", "pattern": "^[a-z]+$"},
    }

    assert iter_errors(["one", "two"], schema) == []
    errors = iter_errors(["ONE", "ONE"], schema)

    assert {(error.absolute_path, error.message) for error in errors} == {
        ((1,), "array items must be unique"),
        ((0,), "string does not match pattern '^[a-z]+$'"),
        ((1,), "string does not match pattern '^[a-z]+$'"),
    }
    assert iter_errors([], schema)[0].message == "array must have at least 2 items"


def test_portable_schema_validates_string_lengths_and_formats() -> None:
    schema = {"type": "string", "minLength": 2, "maxLength": 4}

    assert iter_errors("okay", schema) == []
    assert iter_errors("x", schema)[0].message == "string must contain at least 2 characters"
    assert iter_errors("excess", schema)[0].message == "string must contain at most 4 characters"
    assert iter_errors("2026-02-29", {"type": "string", "format": "date"})
    assert not iter_errors("2028-02-29", {"type": "string", "format": "date"})
    assert iter_errors("2026-08-12T25:00:00Z", {"type": "string", "format": "date-time"})
    assert not iter_errors("2026-08-12T17:30:00-07:00", {"type": "string", "format": "date-time"})


def test_portable_schema_uses_json_type_and_equality_rules() -> None:
    cases = [
        (True, {"type": "boolean"}, False),
        (1, {"type": "boolean"}, True),
        (1, {"type": "integer"}, False),
        (True, {"type": "integer"}, True),
        (1.5, {"type": "number"}, False),
        (None, {"type": "null"}, False),
        (1, {"enum": [True]}, True),
        (False, {"const": 0}, True),
    ]

    for instance, schema, should_error in cases:
        assert bool(iter_errors(instance, schema)) is should_error


def test_portable_schema_validates_additional_values_and_reference_failures() -> None:
    schema = {
        "type": "object",
        "minProperties": 1,
        "properties": {},
        "additionalProperties": {"type": "string"},
    }

    assert iter_errors({"key": "value"}, schema) == []
    assert iter_errors({"key": 7}, schema)[0].absolute_path == ("key",)
    assert iter_errors({}, schema)[0].message == "object must have at least 1 properties"
    assert iter_errors("anything", {"$ref": "#/missing"})[0].message == (
        "unresolved schema reference '#/missing'"
    )


def test_portable_schema_agrees_with_jsonschema_for_skill_documents() -> None:
    intake = yaml.safe_load(
        (ROOT / "examples/intakes/example-assistant.yaml").read_text(encoding="utf-8")
    )
    policy = json.loads(
        (ROOT / "skills/ai-governance-review/references/generic-policy.json").read_text(
            encoding="utf-8"
        )
    )
    findings = analyze_review(intake, policy)["findings"]
    cases: list[tuple[str, object, bool]] = [
        ("intake", intake, True),
        ("policy", policy, True),
        ("findings", findings, True),
    ]

    unknown_field = deepcopy(intake)
    unknown_field["unexpected"] = True
    cases.append(("intake", unknown_field, False))
    missing_owner = deepcopy(intake)
    del missing_owner["request"]["owner"]
    cases.append(("intake", missing_owner, False))
    invalid_email = deepcopy(intake)
    invalid_email["request"]["owner"]["email"] = "not-an-email"
    cases.append(("intake", invalid_email, False))
    duplicate_categories = deepcopy(intake)
    duplicate_categories["data"]["categories"] = ["support tickets", "support tickets"]
    cases.append(("intake", duplicate_categories, False))
    invalid_condition = deepcopy(policy)
    invalid_condition["rules"][0]["condition"] = {
        "equals": {"path": "data.personal_data", "value": True},
        "exists": {"path": "data.personal_data"},
    }
    cases.append(("policy", invalid_condition, False))
    invalid_date = deepcopy(policy)
    invalid_date["policy"]["effective_date"] = "2026-02-29"
    cases.append(("policy", invalid_date, False))
    invalid_finding = deepcopy(findings)
    invalid_finding[0]["severity"] = "automatic-approval"
    cases.append(("findings", invalid_finding, False))

    for schema_name, document, expected_valid in cases:
        schema = json.loads(
            (ROOT / f"src/ai_governance_review/schemas/{schema_name}.schema.json").read_text(
                encoding="utf-8"
            )
        )
        canonical_errors = list(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document)
        )
        portable_errors = iter_errors(document, schema)

        assert (not canonical_errors) is expected_valid, schema_name
        assert (not portable_errors) is expected_valid, schema_name


def test_portable_schema_fails_closed_on_an_unknown_validation_keyword() -> None:
    with pytest.raises(ValueError, match="unsupported schema keyword 'minimum'"):
        iter_errors(4, {"type": "number", "minimum": 5})
