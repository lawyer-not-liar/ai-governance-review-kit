#!/usr/bin/env python3
"""Evaluate the fictional alpha corpus against independent golden expectations."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "src"))

from ai_governance_review.bundle import create_bundle, verify_bundle  # noqa: E402
from ai_governance_review.decision import record_decision  # noqa: E402
from ai_governance_review.loader import load_document  # noqa: E402
from ai_governance_review.policy import evaluate_policy  # noqa: E402
from ai_governance_review.providers import DeterministicProvider  # noqa: E402
from ai_governance_review.render import render_assessment  # noqa: E402
from ai_governance_review.validation import (  # noqa: E402
    validate_document,
    validate_intake_semantics,
)

FIXED_TIME = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
DEFAULT_POLICY = "policies/example/policy.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SCRIPT_ROOT, help="Repository root")
    parser.add_argument(
        "--scenarios",
        type=Path,
        help="Scenario manifest; defaults to examples/alpha/scenarios.yaml under root",
    )
    parser.add_argument("--report", type=Path, help="Write a Markdown human-review workbook")
    return parser.parse_args()


def resolve_under(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{label} escapes the repository root")
    return path


def expected_mapping(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{label} must map string identifiers to string statuses")
    return dict(value)


def expected_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return sorted(value)


def compare(label: str, expected: object, actual: object, failures: list[str]) -> None:
    if expected != actual:
        failures.append(
            f"{label}: expected {json.dumps(expected, sort_keys=True)}, "
            f"got {json.dumps(actual, sort_keys=True)}"
        )


def evaluate_scenario(root: Path, scenario: dict[str, object]) -> list[str]:
    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError("every scenario requires a non-empty id")
    expected = scenario.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"{scenario_id}.expected must be an object")

    intake = load_document(resolve_under(root, scenario.get("intake"), f"{scenario_id}.intake"))
    policy = load_document(
        resolve_under(root, scenario.get("policy", DEFAULT_POLICY), f"{scenario_id}.policy")
    )
    validate_document(intake, "intake")
    validate_document(policy, "policy")
    questions = validate_intake_semantics(intake)
    findings, questions = evaluate_policy(intake, policy, questions)

    actual_findings = {str(finding["rule_id"]): str(finding["status"]) for finding in findings}
    actual_questions = sorted(str(question["id"]) for question in questions)
    actual_blocking = sorted(
        str(finding["id"])
        for finding in findings
        if finding.get("severity") == "block"
        and finding.get("status") in {"triggered", "needs_information"}
    )
    failures: list[str] = []
    compare(
        "findings",
        expected_mapping(expected.get("findings"), f"{scenario_id}.expected.findings"),
        actual_findings,
        failures,
    )
    compare(
        "open_questions",
        expected_string_list(
            expected.get("open_questions"), f"{scenario_id}.expected.open_questions"
        ),
        actual_questions,
        failures,
    )
    compare(
        "blocking_findings",
        expected_string_list(
            expected.get("blocking_findings"), f"{scenario_id}.expected.blocking_findings"
        ),
        actual_blocking,
        failures,
    )

    decision_value = scenario.get("decision")
    if decision_value is not None:
        decision = load_document(resolve_under(root, decision_value, f"{scenario_id}.decision"))
        validate_document(decision, "decision")
        with tempfile.TemporaryDirectory(prefix="ai-governance-alpha-") as raw_directory:
            run_directory = create_bundle(
                intake,
                policy,
                findings,
                questions,
                output_root=Path(raw_directory),
                provider=DeterministicProvider(),
                now=FIXED_TIME,
            )
            decision_path = record_decision(run_directory, decision)
            verify_bundle(run_directory)
            recorded = json.loads(decision_path.read_text(encoding="utf-8"))
        compare("decision", expected.get("decision"), recorded.get("decision"), failures)
    elif "decision" in expected:
        failures.append("decision: expectation provided without a decision fixture")
    return failures


def write_human_report(root: Path, scenarios: list[dict[str, object]], destination: Path) -> None:
    lines = [
        "# AI Governance Review Kit - Alpha Review Workbook",
        "",
        "> All scenarios are fictional. Golden expectations test configured behavior; they do ",
        "> not establish legal compliance or the correctness of an organization's policy.",
        "",
        "Score each dimension from 1 (unusable) to 5 (clear and actionable). Record concrete ",
        "edits or missing questions in the notes column.",
        "",
    ]
    for index, scenario in enumerate(scenarios, start=1):
        scenario_id = str(scenario["id"])
        intake = load_document(resolve_under(root, scenario.get("intake"), f"{scenario_id}.intake"))
        policy = load_document(
            resolve_under(root, scenario.get("policy", DEFAULT_POLICY), f"{scenario_id}.policy")
        )
        questions = validate_intake_semantics(intake)
        findings, questions = evaluate_policy(intake, policy, questions)
        provider = DeterministicProvider()
        assessment = render_assessment(intake, policy, findings, questions, provider)
        expected = scenario["expected"]
        assert isinstance(expected, dict)
        lines.extend(
            [
                f"## Scenario {index}: {scenario_id}",
                "",
                f"**Review focus:** {scenario.get('review_focus', '')}",
                "",
                "### Golden expectations",
                "",
                "```json",
                json.dumps(expected, indent=2, sort_keys=True),
                "```",
                "",
                "### Generated draft assessment",
                "",
                assessment,
                "",
                "### Human usefulness scorecard",
                "",
                "| Dimension | Score (1-5) | Notes |",
                "| --- | --- | --- |",
                "| Facts are accurately represented |  |  |",
                "| Findings are traceable to policy |  |  |",
                "| Questions are specific and answerable |  |  |",
                "| Severity and escalation are proportionate |  |  |",
                "| Recommended next action is clear |  |  |",
                "| Draft avoids false confidence |  |  |",
                "",
                "**Disposition:** Accept / Revise / Reject",
                "",
            ]
        )
    destination.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = (
        args.scenarios.resolve()
        if args.scenarios is not None
        else root / "examples" / "alpha" / "scenarios.yaml"
    )
    try:
        manifest = load_document(manifest_path)
        if manifest.get("schema_version") != "1.0":
            raise ValueError("unsupported scenario manifest version")
        scenarios = manifest.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("scenario manifest must contain a non-empty scenarios list")
        identifiers = [scenario.get("id") for scenario in scenarios if isinstance(scenario, dict)]
        if len(identifiers) != len(scenarios) or len(set(identifiers)) != len(identifiers):
            raise ValueError("scenario ids must be present and unique")
    except (OSError, ValueError) as exc:
        print(f"Alpha validation could not start: {exc}", file=sys.stderr)
        return 2

    passed = 0
    for scenario in scenarios:
        assert isinstance(scenario, dict)
        scenario_id = str(scenario["id"])
        try:
            failures = evaluate_scenario(root, scenario)
        except Exception as exc:  # keep the corpus report complete across scenario failures
            failures = [f"evaluation error: {exc}"]
        if failures:
            print(f"FAIL {scenario_id}")
            for failure in failures:
                print(f"  - {failure}")
        else:
            passed += 1
            print(f"PASS {scenario_id}")

    print(f"{passed}/{len(scenarios)} alpha scenarios passed.")
    if passed != len(scenarios):
        return 1
    if args.report is not None:
        try:
            write_human_report(root, scenarios, args.report.resolve())
        except OSError as exc:
            print(f"Could not write alpha review workbook: {exc}", file=sys.stderr)
            return 2
        print(f"Human review workbook written to {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
