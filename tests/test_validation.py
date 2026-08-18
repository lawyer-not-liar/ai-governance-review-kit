import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_governance_review.errors import ValidationError
from ai_governance_review.validation import validate_document, validate_intake_semantics

SCHEMA_DIR = Path(__file__).parents[1] / "src" / "ai_governance_review" / "schemas"


VALID_INTAKE = {
    "schema_version": "1.0",
    "request": {
        "id": "example-1",
        "title": "Internal writing assistant",
        "owner": {"name": "Alex Example", "email": "alex@example.invalid"},
    },
    "purpose": {
        "summary": "Suggest edits to internal drafts.",
        "intended_outcome": "Help staff revise prose.",
        "affected_people": ["employees"],
        "deployment_scope": "internal",
    },
    "system": {
        "name": "Example Assistant",
        "provider": "Example Systems",
        "hosting": "managed_private",
        "autonomy": "human_in_the_loop",
        "human_oversight": True,
    },
    "data": {
        "categories": ["internal documents"],
        "personal_data": False,
        "sensitive_data": False,
        "training_or_fine_tuning": False,
        "retention": "Inputs are deleted after processing.",
        "cross_border_transfers": False,
    },
    "outputs": {
        "types": ["text"],
        "recipients": ["employees"],
        "external_distribution": False,
        "decisions_influenced": [],
    },
    "evidence": [],
}


def test_all_public_schemas_are_valid_and_have_stable_ids():
    paths = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert len(paths) == 5

    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith("https://example.invalid/ai-governance-review-kit/schemas/")


def test_valid_intake_passes_schema_validation():
    validate_document(VALID_INTAKE, "intake")


def test_unknown_intake_fields_are_rejected():
    intake = deepcopy(VALID_INTAKE)
    intake["secret_override"] = True

    with pytest.raises(ValidationError) as error:
        validate_document(intake, "intake")

    assert "secret_override" in " ".join(error.value.details)


def test_unknown_material_facts_become_open_questions():
    intake = deepcopy(VALID_INTAKE)
    intake["data"]["personal_data"] = "unknown"
    intake["outputs"]["external_distribution"] = "unknown"

    questions = validate_intake_semantics(intake)

    assert [question["path"] for question in questions] == [
        "data.personal_data",
        "outputs.external_distribution",
    ]


def test_unknown_deployment_scope_and_autonomy_become_open_questions():
    intake = deepcopy(VALID_INTAKE)
    intake["purpose"]["deployment_scope"] = "unknown"
    intake["system"]["autonomy"] = "unknown"

    questions = validate_intake_semantics(intake)

    assert [question["path"] for question in questions] == [
        "purpose.deployment_scope",
        "system.autonomy",
    ]


def test_contradictory_human_oversight_becomes_open_question():
    intake = deepcopy(VALID_INTAKE)
    intake["system"]["autonomy"] = "human_in_the_loop"
    intake["system"]["human_oversight"] = False

    questions = validate_intake_semantics(intake)

    assert questions == [
        {
            "id": "semantic-system-human-oversight",
            "path": "system.human_oversight",
            "question": (
                "The system is described as human-in-the-loop but human oversight is false. "
                "Which description is correct?"
            ),
        }
    ]
