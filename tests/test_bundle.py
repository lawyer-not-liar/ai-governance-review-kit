import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_governance_review.bundle import create_bundle, verify_bundle
from ai_governance_review.errors import ValidationError
from ai_governance_review.loader import load_document
from ai_governance_review.policy import evaluate_policy
from ai_governance_review.presentation import build_presentation_facts
from ai_governance_review.providers import DeterministicProvider
from ai_governance_review.render import render_assessment
from ai_governance_review.validation import validate_intake_semantics

PROJECT_ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def complete_inputs(example_policy):
    intake = load_document(PROJECT_ROOT / "tests" / "fixtures" / "intake-complete.yaml")
    questions = validate_intake_semantics(intake)
    findings, questions = evaluate_policy(intake, example_policy, questions)
    return intake, example_policy, findings, questions


def test_deterministic_provider_has_stable_human_gated_summary(complete_inputs):
    intake, policy, findings, questions = complete_inputs
    provider = DeterministicProvider()
    presentation_facts = build_presentation_facts(policy, findings, questions, [])

    first = provider.summarize_from_presentation_facts(intake, presentation_facts)
    second = provider.summarize_from_presentation_facts(intake, presentation_facts)

    assert first == second
    assert "draft assessment" in first.lower()
    assert "0 triggered finding(s)" in first
    assert "human reviewer" in first.lower()


def test_rendered_assessment_has_warning_and_source_boundaries(complete_inputs):
    intake, policy, findings, questions = complete_inputs

    assessment = render_assessment(
        intake,
        policy,
        findings,
        questions,
        DeterministicProvider(),
    )

    assert assessment.startswith("# DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED")
    assert "Requester-supplied facts" in assessment
    assert "Policy-derived findings" in assessment
    assert "Requester-provided evidence references were not fetched or verified" in assessment
    assert "This is not an organizational decision" in assessment


def test_rendered_assessment_omits_non_applicable_rule_noise(complete_inputs):
    intake, policy, findings, questions = complete_inputs

    assessment = render_assessment(
        intake,
        policy,
        findings,
        questions,
        DeterministicProvider(),
    )

    assert "No active policy findings were identified" in assessment
    assert "EXAMPLE\\-DATA\\-1:" not in assessment


def test_create_bundle_writes_stable_artifacts_and_hashes(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )

    assert run_dir.name == "example-1-20260805T120000Z"
    assert sorted(path.name for path in run_dir.iterdir()) == [
        "draft-assessment.md",
        "evidence.json",
        "findings.json",
        "intake.normalized.json",
        "manifest.json",
        "open-questions.json",
        "policy.snapshot.json",
    ]
    policy_snapshot = json.loads((run_dir / "policy.snapshot.json").read_text(encoding="utf-8"))
    assert policy_snapshot == complete_inputs[1]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "deterministic"
    for name, expected_hash in manifest["artifacts"].items():
        actual_hash = hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        assert actual_hash == expected_hash
    verify_bundle(run_dir)


def test_create_bundle_refuses_to_overwrite_existing_run(tmp_path, complete_inputs):
    create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )

    with pytest.raises(ValidationError, match="already exists"):
        create_bundle(
            *complete_inputs,
            output_root=tmp_path,
            provider=DeterministicProvider(),
            now=FIXED_TIME,
        )


def test_create_bundle_validates_request_id_before_using_it_as_a_path(tmp_path, complete_inputs):
    intake, policy, findings, questions = complete_inputs
    unsafe_intake = deepcopy(intake)
    unsafe_intake["request"]["id"] = "../../outside"

    with pytest.raises(ValidationError, match="intake validation failed"):
        create_bundle(
            unsafe_intake,
            policy,
            findings,
            questions,
            output_root=tmp_path,
            provider=DeterministicProvider(),
            now=FIXED_TIME,
        )

    assert list(tmp_path.iterdir()) == []


def test_verify_bundle_detects_changed_finding(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    (run_dir / "findings.json").write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="hash mismatch for findings.json"):
        verify_bundle(run_dir)


def test_verify_bundle_detects_changed_policy_snapshot(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    (run_dir / "policy.snapshot.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="hash mismatch for policy.snapshot.json"):
        verify_bundle(run_dir)


def test_verify_bundle_detects_missing_artifact(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    (run_dir / "evidence.json").unlink()

    with pytest.raises(ValidationError, match="missing artifact.*evidence.json"):
        verify_bundle(run_dir)


def test_verify_bundle_rejects_unexpected_artifacts(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    (run_dir / "untracked-secret.txt").write_text("secret", encoding="utf-8")

    with pytest.raises(ValidationError, match="unexpected artifact"):
        verify_bundle(run_dir)


def test_verify_bundle_rejects_manifest_path_traversal(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["../outside.json"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValidationError, match="unsafe artifact path"):
        verify_bundle(run_dir)


def test_verify_bundle_rejects_symlinked_run_directory(tmp_path, complete_inputs):
    run_dir = create_bundle(
        *complete_inputs,
        output_root=tmp_path,
        provider=DeterministicProvider(),
        now=FIXED_TIME,
    )
    alias = tmp_path / "review-alias"
    alias.symlink_to(run_dir, target_is_directory=True)

    with pytest.raises(ValidationError, match="must not be a symbolic link"):
        verify_bundle(alias)
