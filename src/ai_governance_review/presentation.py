"""Deterministic facts for AI-assisted result presentation."""

ACTIVE_STATUSES = frozenset({"triggered", "needs_information"})
DRAFT_HEADING = "# DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED"


def build_presentation_facts(
    policy: dict[str, object],
    findings: list[dict[str, object]],
    open_questions: list[dict[str, object]],
    blocking_findings: list[str],
) -> dict[str, object]:
    """Return the only quantitative facts an AI-assisted host should present."""

    metadata = policy.get("policy", {})
    assert isinstance(metadata, dict)
    active = [item for item in findings if item.get("status") in ACTIVE_STATUSES]
    return {
        "policy": {
            "id": str(metadata.get("id", "")),
            "version": str(metadata.get("version", "")),
            "status": str(metadata.get("status", "")),
        },
        "active_findings": {
            "total": len(active),
            "triggered": sum(item.get("status") == "triggered" for item in active),
            "needs_information": sum(item.get("status") == "needs_information" for item in active),
            "blocking": len(blocking_findings),
        },
        "open_questions": len(open_questions),
        "draft_heading": DRAFT_HEADING,
    }


def _plain(value: object) -> str:
    """Collapse generated policy text to one display-safe line."""

    return " ".join(str(value).split())


def build_presentation_text(
    presentation_facts: dict[str, object],
    findings: list[dict[str, object]],
    open_questions: list[dict[str, object]],
) -> str:
    """Render the canonical result block from engine facts."""

    policy = presentation_facts["policy"]
    active_counts = presentation_facts["active_findings"]
    assert isinstance(policy, dict)
    assert isinstance(active_counts, dict)
    lines = [
        "Review result",
        "- Deterministic engine: ran successfully",
        f"- Policy: {_plain(policy['id'])} version {_plain(policy['version'])}",
        (
            f"- Active findings: {active_counts['total']} total; "
            f"{active_counts['triggered']} triggered; "
            f"{active_counts['needs_information']} need information; "
            f"{active_counts['blocking']} blocking"
        ),
        f"- Open questions: {presentation_facts['open_questions']}",
        f"- Draft heading: {_plain(presentation_facts['draft_heading'])}",
    ]
    active = [finding for finding in findings if finding.get("status") in ACTIVE_STATUSES]
    if active:
        lines.extend(["", "Active findings"])
        for finding in active:
            lines.extend(
                [
                    f"- {_plain(finding.get('rule_id', 'unknown'))}: "
                    f"{_plain(finding.get('title', ''))}",
                    f"  - Severity: {_plain(finding.get('severity', ''))}",
                    f"  - Status: {_plain(finding.get('status', ''))}",
                    f"  - Explanation: {_plain(finding.get('explanation', ''))}",
                ]
            )
            missing = finding.get("missing_evidence", [])
            if isinstance(missing, list) and missing:
                lines.append(f"  - Missing evidence: {_plain(', '.join(map(str, missing)))}")

    if open_questions:
        lines.extend(["", "Open questions"])
        lines.extend(f"- {_plain(item.get('question', ''))}" for item in open_questions)

    lines.extend(
        [
            "",
            "Human review boundaries",
            "- This uses an illustrative generic policy and is not legal advice, approval, "
            "rejection, or an organizational decision.",
            "- Evidence references were not fetched or independently verified.",
            "- A human reviewer must verify the intake and evidence, resolve open questions, "
            "and record the actual decision separately.",
        ]
    )
    return "\n".join(lines)
