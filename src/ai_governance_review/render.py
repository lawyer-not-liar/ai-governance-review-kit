"""Markdown rendering for draft review assessments."""

import html

from .presentation import DRAFT_HEADING, build_presentation_facts
from .providers import NarrativeProvider


def _md(value: object) -> str:
    text = html.escape(str(value), quote=True)
    for character in "\\`*_{}[]()#+-.!|":
        text = text.replace(character, f"\\{character}")
    return text.replace("\n", " ")


def _value(document: dict[str, object], section: str, key: str, default: object = "") -> object:
    selected = document.get(section, {})
    return selected.get(key, default) if isinstance(selected, dict) else default


def render_assessment(
    intake: dict[str, object],
    policy: dict[str, object],
    findings: list[dict[str, object]],
    questions: list[dict[str, object]],
    provider: NarrativeProvider,
    *,
    presentation_facts: dict[str, object] | None = None,
) -> str:
    """Render a review bundle as escaped, human-readable Markdown."""

    metadata = policy.get("policy", {})
    policy_id = metadata.get("id", "unknown") if isinstance(metadata, dict) else "unknown"
    policy_version = metadata.get("version", "unknown") if isinstance(metadata, dict) else "unknown"
    if presentation_facts is None:
        blocking_findings = sorted(
            str(finding["id"])
            for finding in findings
            if finding.get("severity") == "block"
            and finding.get("status") in {"triggered", "needs_information"}
        )
        presentation_facts = build_presentation_facts(
            policy, findings, questions, blocking_findings
        )
    lines = [
        DRAFT_HEADING,
        "",
        "> This is not an organizational decision, approval, or legal opinion.",
        "",
        "## Draft summary",
        "",
        _md(
            provider.summarize_from_presentation_facts(intake, presentation_facts)
            if callable(getattr(provider, "summarize_from_presentation_facts", None))
            else provider.summarize(intake, findings, questions)
        ),
        "",
        "## Requester-supplied facts",
        "",
        (
            f"- Request: {_md(_value(intake, 'request', 'id'))} - "
            f"{_md(_value(intake, 'request', 'title'))}"
        ),
        f"- Purpose: {_md(_value(intake, 'purpose', 'summary'))}",
        f"- System: {_md(_value(intake, 'system', 'name'))}",
        f"- Provider: {_md(_value(intake, 'system', 'provider'))}",
        f"- Deployment scope: {_md(_value(intake, 'purpose', 'deployment_scope'))}",
        "",
        "## Policy-derived findings",
        "",
        f"Policy: `{_md(policy_id)}` version `{_md(policy_version)}`",
        "",
    ]
    active_findings = [finding for finding in findings if finding.get("status") != "not_applicable"]
    if not active_findings:
        lines.extend(["No active policy findings were identified.", ""])
    else:
        for finding in active_findings:
            lines.extend(
                [
                    (
                        f"### {_md(finding.get('rule_id', 'unknown'))}: "
                        f"{_md(finding.get('title', ''))}"
                    ),
                    "",
                    f"- Severity: **{_md(finding.get('severity', ''))}**",
                    f"- Status: **{_md(finding.get('status', ''))}**",
                    f"- Explanation: {_md(finding.get('explanation', ''))}",
                ]
            )
            missing = finding.get("missing_evidence", [])
            if isinstance(missing, list) and missing:
                lines.append(f"- Missing evidence: {_md(', '.join(str(item) for item in missing))}")
            lines.append("")

    lines.extend(["## Open questions", ""])
    if questions:
        lines.extend(f"- {_md(question.get('question', ''))}" for question in questions)
    else:
        lines.append("- None identified by the configured checks.")

    lines.extend(["", "## Evidence references", ""])
    evidence = intake.get("evidence", [])
    if isinstance(evidence, list) and evidence:
        for item in evidence:
            if isinstance(item, dict):
                lines.append(
                    f"- `{_md(item.get('id', ''))}`: {_md(item.get('title', 'Untitled'))} "
                    f"({_md(item.get('type', 'unspecified'))})"
                )
    else:
        lines.append("- No evidence references were supplied.")
    lines.extend(
        [
            "",
            "Requester-provided evidence references were not fetched or verified.",
            "",
            "## Human review required",
            "",
            "A reviewer must verify the intake, examine the underlying evidence, resolve open "
            "questions, and record the actual decision separately.",
            "",
        ]
    )
    return "\n".join(lines)
