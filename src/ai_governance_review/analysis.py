"""Structured deterministic analysis shared by AI-assisted and CLI surfaces."""

from .errors import ValidationError
from .policy import evaluate_policy
from .presentation import build_presentation_facts, build_presentation_text
from .providers import DeterministicProvider, NarrativeProvider
from .render import render_assessment
from .validation import validate_document, validate_intake_semantics


def analyze_review(
    intake: dict[str, object],
    policy: dict[str, object],
    provider: NarrativeProvider | None = None,
) -> dict[str, object]:
    """Validate and evaluate one intake without recording a human decision."""

    validate_document(intake, "intake")
    validate_document(policy, "policy")
    metadata = policy.get("policy", {})
    if not isinstance(metadata, dict):
        raise ValidationError("policy metadata must be an object")
    if metadata.get("status") == "superseded":
        raise ValidationError("cannot generate a review with a superseded policy")

    questions = validate_intake_semantics(intake)
    findings, questions = evaluate_policy(intake, policy, questions)
    validate_document(findings, "findings")
    narrative = provider or DeterministicProvider()
    blocking = sorted(
        str(finding["id"])
        for finding in findings
        if finding.get("severity") == "block"
        and finding.get("status") in {"triggered", "needs_information"}
    )
    presentation_facts = build_presentation_facts(policy, findings, questions, blocking)
    return {
        "schema_version": "1.0",
        "policy": {
            "id": str(metadata.get("id", "")),
            "version": str(metadata.get("version", "")),
            "status": str(metadata.get("status", "")),
        },
        "findings": findings,
        "open_questions": questions,
        "blocking_findings": blocking,
        "presentation_facts": presentation_facts,
        "presentation_text": build_presentation_text(presentation_facts, findings, questions),
        "draft_assessment": render_assessment(
            intake,
            policy,
            findings,
            questions,
            narrative,
            presentation_facts=presentation_facts,
        ),
    }
