import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from ai_governance_review.bundle import create_bundle, verify_bundle
from ai_governance_review.loader import load_document
from ai_governance_review.policy import evaluate_policy
from ai_governance_review.providers import DeterministicProvider
from ai_governance_review.sanitize import sanitize_bundle
from ai_governance_review.validation import validate_intake_semantics

PROJECT_ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _complete_intake() -> dict[str, object]:
    return load_document(PROJECT_ROOT / "tests" / "fixtures" / "intake-complete.yaml")


def _evaluate(intake, policy):
    semantic_questions = validate_intake_semantics(intake)
    return evaluate_policy(intake, policy, semantic_questions)


def test_realistic_escalated_intake_produces_expected_review_matrix(example_policy):
    intake = _complete_intake()
    intake["system"].update({"hosting": "unknown", "human_oversight": False})
    intake["data"].update({"personal_data": True, "training_or_fine_tuning": True})
    intake["outputs"].update(
        {
            "external_distribution": True,
            "decisions_influenced": ["employment screening"],
        }
    )
    intake["evidence"] = [
        {
            "id": "training-data-record",
            "type": "record",
            "title": "Synthetic training data record",
        }
    ]

    findings, questions = _evaluate(intake, example_policy)

    assert {finding["rule_id"]: finding["status"] for finding in findings} == {
        "EXAMPLE-COMPLETENESS-1": "triggered",
        "EXAMPLE-DATA-1": "needs_information",
        "EXAMPLE-DATA-2": "triggered",
        "EXAMPLE-DATA-3": "not_applicable",
        "EXAMPLE-DATA-4": "not_applicable",
        "EXAMPLE-IMPACT-1": "triggered",
        "EXAMPLE-OUTPUT-1": "triggered",
        "EXAMPLE-OVERSIGHT-1": "triggered",
        "EXAMPLE-SYSTEM-1": "not_applicable",
        "EXAMPLE-VENDOR-1": "not_applicable",
    }
    assert [question["id"] for question in questions] == [
        "question-EXAMPLE-COMPLETENESS-1",
        "question-EXAMPLE-DATA-1",
        "question-EXAMPLE-IMPACT-1",
        "question-EXAMPLE-OUTPUT-1",
        "question-EXAMPLE-OVERSIGHT-1",
        "semantic-system-human-oversight",
    ]


def test_same_inputs_and_time_produce_byte_identical_bundles(tmp_path, example_policy):
    intake = _complete_intake()
    findings, questions = _evaluate(intake, example_policy)
    first = create_bundle(
        intake,
        example_policy,
        findings,
        questions,
        output_root=tmp_path / "first",
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    second = create_bundle(
        deepcopy(intake),
        deepcopy(example_policy),
        deepcopy(findings),
        deepcopy(questions),
        output_root=tmp_path / "second",
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )

    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_sanitization_removes_planted_markers_from_every_artifact(tmp_path, example_policy):
    marker = "TOP_SECRET_42"
    email_marker = "top-secret-42"
    intake = _complete_intake()
    intake["request"].update(
        {
            "id": marker,
            "title": marker,
            "owner": {"name": marker, "email": f"{email_marker}@example.invalid"},
        }
    )
    intake["purpose"].update(
        {
            "summary": marker,
            "intended_outcome": marker,
            "affected_people": [marker],
        }
    )
    intake["system"].update({"name": marker, "provider": marker})
    intake["data"].update({"categories": [marker], "retention": marker})
    intake["outputs"].update(
        {"types": [marker], "recipients": [marker], "decisions_influenced": [marker]}
    )
    findings, questions = _evaluate(intake, example_policy)
    source = create_bundle(
        intake,
        example_policy,
        findings,
        questions,
        output_root=tmp_path / "runs",
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    paths = [
        "request.title",
        "purpose.summary",
        "purpose.intended_outcome",
        "purpose.affected_people",
        "system.name",
        "system.provider",
        "data.categories",
        "data.retention",
        "outputs.types",
        "outputs.recipients",
        "outputs.decisions_influenced",
    ]

    sanitized = sanitize_bundle(source, tmp_path / "sanitized", paths)

    verify_bundle(sanitized)
    serialized_bundle = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(sanitized.iterdir())
    )
    assert marker not in serialized_bundle
    assert email_marker not in serialized_bundle
    sanitized_intake = json.loads(
        (sanitized / "intake.normalized.json").read_text(encoding="utf-8")
    )
    assert sanitized_intake["request"]["id"] == "sanitized-request"
