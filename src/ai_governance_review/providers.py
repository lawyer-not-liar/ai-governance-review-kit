"""Narrative-provider boundary for optional synthesis."""

from typing import Protocol


class NarrativeProvider(Protocol):
    """Produce explanatory prose without making an organizational decision."""

    name: str

    def summarize(
        self,
        intake: dict[str, object],
        findings: list[dict[str, object]],
        open_questions: list[dict[str, object]],
    ) -> str: ...


class DeterministicProvider:
    """Offline, reproducible prose assembled from already-evaluated facts."""

    name = "deterministic"

    def summarize(
        self,
        intake: dict[str, object],
        findings: list[dict[str, object]],
        open_questions: list[dict[str, object]],
    ) -> str:
        """Preserve the original provider interface for external adapters."""

        triggered = sum(finding.get("status") == "triggered" for finding in findings)
        needs_information = sum(
            finding.get("status") == "needs_information" for finding in findings
        )
        return self._render_summary(intake, triggered, needs_information, len(open_questions))

    def summarize_from_presentation_facts(
        self,
        intake: dict[str, object],
        presentation_facts: dict[str, object],
    ) -> str:
        """Render the built-in summary from the authoritative presentation facts."""

        active_findings = presentation_facts["active_findings"]
        assert isinstance(active_findings, dict)
        triggered = active_findings["triggered"]
        needs_information = active_findings["needs_information"]
        question_count = presentation_facts["open_questions"]
        return self._render_summary(intake, triggered, needs_information, question_count)

    @staticmethod
    def _render_summary(
        intake: dict[str, object],
        triggered: object,
        needs_information: object,
        question_count: object,
    ) -> str:
        request = intake.get("request", {})
        title = (
            request.get("title", "Untitled request")
            if isinstance(request, dict)
            else "Untitled request"
        )
        return (
            f"This draft assessment covers {title}. The demonstration policy produced "
            f"{triggered} triggered finding(s), {needs_information} finding(s) needing "
            f"information, and {question_count} open question(s). A human reviewer "
            "must evaluate the facts, evidence, policy fit, and resulting conditions."
        )
