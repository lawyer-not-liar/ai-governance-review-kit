import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_governance_review.bundle import create_bundle, verify_bundle
from ai_governance_review.errors import ValidationError
from ai_governance_review.loader import load_document
from ai_governance_review.policy import evaluate_policy
from ai_governance_review.providers import DeterministicProvider
from ai_governance_review.sanitize import sanitize_bundle
from ai_governance_review.validation import validate_intake_semantics

PROJECT_ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _bundle(tmp_path, example_policy):
    intake = load_document(PROJECT_ROOT / "tests" / "fixtures" / "intake-complete.yaml")
    intake["evidence"] = [
        {
            "id": "architecture-record",
            "type": "document",
            "title": "Architecture record",
            "uri": "/Us" + "ers/alex/private/architecture.pdf",
        }
    ]
    questions = validate_intake_semantics(intake)
    findings, questions = evaluate_policy(intake, example_policy, questions)
    return create_bundle(
        intake,
        example_policy,
        findings,
        questions,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )


def test_sanitize_redacts_identifiers_custom_paths_and_local_uris(tmp_path, example_policy):
    run_dir = _bundle(tmp_path / "runs", example_policy)
    source_before = (run_dir / "intake.normalized.json").read_bytes()

    sanitized = sanitize_bundle(
        run_dir,
        tmp_path / "sanitized",
        ["purpose.summary"],
    )

    intake = json.loads((sanitized / "intake.normalized.json").read_text(encoding="utf-8"))
    manifest = json.loads((sanitized / "manifest.json").read_text(encoding="utf-8"))
    assert intake["request"]["id"] == "sanitized-request"
    assert manifest["request_id"] == "sanitized-request"
    assert intake["request"]["owner"] == {
        "name": "[REDACTED]",
        "email": "redacted@example.invalid",
    }
    assert intake["purpose"]["summary"] == "[REDACTED]"
    assert intake["evidence"][0]["uri"] == "[REDACTED]"
    assert (run_dir / "intake.normalized.json").read_bytes() == source_before
    verify_bundle(sanitized)


def test_sanitize_redacts_fact_values_for_custom_paths(tmp_path, example_policy):
    run_dir = _bundle(tmp_path / "runs", example_policy)

    sanitized = sanitize_bundle(
        run_dir,
        tmp_path / "sanitized",
        ["data.personal_data"],
    )

    findings = json.loads((sanitized / "findings.json").read_text(encoding="utf-8"))
    personal_facts = [
        fact
        for finding in findings
        for fact in finding["facts"]
        if fact["path"] == "data.personal_data"
    ]
    assert personal_facts and all(fact["value"] == "unknown" for fact in personal_facts)


def test_sanitize_refuses_destination_inside_source_bundle(tmp_path, example_policy):
    run_dir = _bundle(tmp_path / "runs", example_policy)

    with pytest.raises(ValidationError, match="outside the source bundle"):
        sanitize_bundle(run_dir, run_dir / "sanitized", [])


def test_sanitize_refuses_to_overwrite_destination(tmp_path, example_policy):
    run_dir = _bundle(tmp_path / "runs", example_policy)
    destination = tmp_path / "sanitized"
    destination.mkdir()

    with pytest.raises(ValidationError, match="already exists"):
        sanitize_bundle(run_dir, destination, [])
