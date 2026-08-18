from pathlib import Path

import pytest

from ai_governance_review.analysis import analyze_review
from ai_governance_review.errors import ValidationError
from ai_governance_review.loader import load_document

ROOT = Path(__file__).parents[1]


class LegacyNarrativeProvider:
    name = "legacy-test-provider"

    def summarize(
        self,
        intake: dict[str, object],
        findings: list[dict[str, object]],
        open_questions: list[dict[str, object]],
    ) -> str:
        return "Legacy provider summary."


def test_analyze_review_returns_traceable_structured_result() -> None:
    intake = load_document(ROOT / "examples/intakes/example-assistant.yaml")
    policy = load_document(ROOT / "policies/example/policy.yaml")

    result = analyze_review(intake, policy)

    assert result["schema_version"] == "1.0"
    assert result["policy"] == {
        "id": "example-ai-use-policy",
        "version": "0.1.0",
        "status": "demonstration",
    }
    assert result["blocking_findings"] == []
    assert result["open_questions"] == []
    assert len(result["findings"]) == 6
    assert result["presentation_facts"] == {
        "policy": {
            "id": "example-ai-use-policy",
            "version": "0.1.0",
            "status": "demonstration",
        },
        "active_findings": {
            "total": 0,
            "triggered": 0,
            "needs_information": 0,
            "blocking": 0,
        },
        "open_questions": 0,
        "draft_heading": "# DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED",
    }
    assert "DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED" in result["draft_assessment"]

    presentation = result["presentation_text"]
    assert presentation.startswith("Review result\n- Deterministic engine: ran successfully")
    assert "Active findings: 0 total; 0 triggered; 0 need information; 0 blocking" in presentation
    assert "Open questions: 0" in presentation
    assert "EXAMPLE-DATA-1" not in presentation
    assert "not_applicable" not in presentation
    assert "illustrative" in presentation.lower()


def test_analyze_review_presentation_text_includes_only_active_findings() -> None:
    intake = load_document(ROOT / "examples/alpha/intakes/04-training-missing-evidence.yaml")
    policy = load_document(ROOT / "policies/example/policy.yaml")

    result = analyze_review(intake, policy)
    presentation = result["presentation_text"]

    assert "Active findings: 1 total; 0 triggered; 1 need information; 1 blocking" in presentation
    assert "EXAMPLE-DATA-2: Training-data documentation" in presentation
    assert "Missing evidence: training-data-record" in presentation
    assert "Provide the fictional organization's training-data record." in presentation
    assert "EXAMPLE-DATA-1" not in presentation
    assert "EXAMPLE-IMPACT-1" not in presentation
    assert "not_applicable" not in presentation


def test_analyze_review_rejects_superseded_policy() -> None:
    intake = load_document(ROOT / "examples/intakes/example-assistant.yaml")
    policy = load_document(ROOT / "policies/example/policy.yaml")
    policy["policy"]["status"] = "superseded"

    with pytest.raises(ValidationError, match="superseded policy"):
        analyze_review(intake, policy)


def test_analyze_review_preserves_existing_narrative_provider_contract() -> None:
    intake = load_document(ROOT / "examples/intakes/example-assistant.yaml")
    policy = load_document(ROOT / "policies/example/policy.yaml")

    result = analyze_review(intake, policy, LegacyNarrativeProvider())

    assert "Legacy provider summary" in result["draft_assessment"]
    assert result["presentation_text"].startswith("Review result")
