import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ai_governance_review.decision as decision_module
from ai_governance_review.bundle import create_bundle, verify_bundle
from ai_governance_review.decision import record_decision
from ai_governance_review.errors import ValidationError
from ai_governance_review.loader import load_document
from ai_governance_review.policy import evaluate_policy
from ai_governance_review.providers import DeterministicProvider
from ai_governance_review.validation import validate_intake_semantics

PROJECT_ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _decision(**changes):
    decision = {
        "schema_version": "1.0",
        "reviewer": "Jordan Reviewer",
        "decision": "approved",
        "decided_at": "2026-08-05T13:00:00Z",
        "policy": {"id": "example-ai-use-policy", "version": "0.1.0"},
        "conditions": [],
        "unresolved_risks": [],
        "acknowledged_findings": [],
        "overrides": [],
        "independent_review_confirmed": True,
    }
    decision.update(changes)
    return decision


def _bundle_from_intake(tmp_path, example_policy, intake):
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


def _bundle(tmp_path, example_policy, fixture="intake-complete.yaml"):
    intake = load_document(PROJECT_ROOT / "tests" / "fixtures" / fixture)
    return _bundle_from_intake(tmp_path, example_policy, intake)


def _training_intake_with_evidence():
    intake = load_document(PROJECT_ROOT / "tests" / "fixtures" / "intake-missing-evidence.yaml")
    intake["evidence"] = [
        {
            "id": "training-data-record",
            "type": "record",
            "title": "Synthetic training-data record",
        }
    ]
    return intake


def test_record_decision_adds_hashed_human_artifact(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)

    decision_path = record_decision(run_dir, _decision())

    assert decision_path.name == "human-decision.json"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "human-decision.json" in manifest["artifacts"]
    verify_bundle(run_dir)


def test_record_decision_verifies_bundle_before_writing(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)
    (run_dir / "findings.json").write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="hash mismatch"):
        record_decision(run_dir, _decision())

    assert not (run_dir / "human-decision.json").exists()


def test_record_decision_requires_matching_policy_version(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)
    decision = _decision(policy={"id": "example-ai-use-policy", "version": "9.9.9"})

    with pytest.raises(ValidationError, match="policy does not match"):
        record_decision(run_dir, decision)


def test_record_decision_requires_independent_review_confirmation(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)

    with pytest.raises(ValidationError, match="independent_review_confirmed"):
        record_decision(run_dir, _decision(independent_review_confirmed=False))


def test_approval_requires_all_blocking_findings_to_be_addressed(tmp_path, example_policy):
    run_dir = _bundle_from_intake(tmp_path, example_policy, _training_intake_with_evidence())

    with pytest.raises(ValidationError, match="document an override.*finding-EXAMPLE-DATA-2"):
        record_decision(run_dir, _decision())


def test_approval_cannot_acknowledge_away_blocking_finding(tmp_path, example_policy):
    run_dir = _bundle_from_intake(tmp_path, example_policy, _training_intake_with_evidence())
    decision = _decision(
        decision="approved_with_conditions",
        conditions=["Document the acknowledged block in the deployment record."],
        acknowledged_findings=["finding-EXAMPLE-DATA-2"],
    )

    with pytest.raises(ValidationError, match="finding-EXAMPLE-DATA-2"):
        record_decision(run_dir, decision)

    assert not (run_dir / "human-decision.json").exists()


def test_approved_with_conditions_accepts_nonempty_condition(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)
    decision = _decision(
        decision="approved_with_conditions",
        conditions=["Complete a review after the fictional pilot."],
    )

    record_decision(run_dir, decision)

    verify_bundle(run_dir)


def test_rejection_can_record_unresolved_blocking_findings(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy, "intake-missing-evidence.yaml")
    decision = _decision(
        decision="declined",
        unresolved_risks=["Required training-data evidence was not supplied."],
    )

    record_decision(run_dir, decision)

    verify_bundle(run_dir)


def test_approval_accepts_documented_override_for_blocking_finding(tmp_path, example_policy):
    run_dir = _bundle_from_intake(tmp_path, example_policy, _training_intake_with_evidence())
    decision = _decision(
        overrides=[
            {
                "finding_id": "finding-EXAMPLE-DATA-2",
                "rationale": "The reviewer confirmed the synthetic source record offline.",
            }
        ]
    )

    record_decision(run_dir, decision)

    verify_bundle(run_dir)


def test_approval_requires_all_open_questions_to_be_resolved(tmp_path, example_policy):
    intake = load_document(PROJECT_ROOT / "tests" / "fixtures" / "intake-complete.yaml")
    intake["data"]["personal_data"] = "unknown"
    run_dir = _bundle_from_intake(tmp_path, example_policy, intake)

    with pytest.raises(ValidationError, match="unresolved open question"):
        record_decision(run_dir, _decision())

    assert not (run_dir / "human-decision.json").exists()


def test_override_requires_non_whitespace_rationale(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy, "intake-missing-evidence.yaml")
    decision = _decision(overrides=[{"finding_id": "finding-EXAMPLE-DATA-2", "rationale": "   "}])

    with pytest.raises(ValidationError, match="non-empty rationale"):
        record_decision(run_dir, decision)


def test_existing_decision_is_append_protected(tmp_path, example_policy):
    run_dir = _bundle(tmp_path, example_policy)
    record_decision(run_dir, _decision())

    with pytest.raises(ValidationError, match="already contains a human decision"):
        record_decision(run_dir, deepcopy(_decision()))


def test_manifest_write_failure_rolls_back_decision(tmp_path, example_policy, monkeypatch):
    run_dir = _bundle(tmp_path, example_policy)
    original_manifest = (run_dir / "manifest.json").read_bytes()
    real_replace = decision_module.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated manifest replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(decision_module.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated manifest replacement failure"):
        record_decision(run_dir, _decision())

    assert not (run_dir / "human-decision.json").exists()
    assert (run_dir / "manifest.json").read_bytes() == original_manifest
    verify_bundle(run_dir)
