"""Command-line interface for local AI governance reviews."""

import argparse
import sys
from pathlib import Path

from .analysis import analyze_review
from .bundle import create_bundle
from .decision import record_decision
from .errors import ValidationError
from .loader import load_document
from .policy import evaluate_policy
from .providers import DeterministicProvider
from .render import render_assessment
from .sanitize import sanitize_bundle
from .validation import validate_document, validate_intake_semantics


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-review",
        description="Create traceable draft AI governance assessments for human review.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate an intake and optional policy")
    validate.add_argument("intake", type=Path)
    validate.add_argument("--policy", type=Path)

    review = subparsers.add_parser("review", help="Generate a draft review assessment")
    review.add_argument("intake", type=Path)
    review.add_argument("--policy", type=Path, required=True)
    output = review.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path)
    output.add_argument("--no-save", action="store_true")

    decide = subparsers.add_parser("decide", help="Record one human decision")
    decide.add_argument("run_directory", type=Path)
    decide.add_argument("--decision-file", type=Path, required=True)

    sanitize = subparsers.add_parser("sanitize", help="Create a redacted support bundle")
    sanitize.add_argument("run_directory", type=Path)
    sanitize.add_argument("--output", type=Path, required=True)
    sanitize.add_argument("--path", action="append", default=[], dest="sensitive_paths")
    return parser


def _policy_path(path: Path) -> Path:
    return path / "policy.yaml" if path.is_dir() else path


def _load_validated_intake(path: Path) -> dict[str, object]:
    intake = load_document(path)
    validate_document(intake, "intake")
    return intake


def _load_validated_policy(path: Path) -> dict[str, object]:
    policy = load_document(_policy_path(path))
    validate_document(policy, "policy")
    return policy


def _evaluate(
    intake: dict[str, object], policy: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    result = analyze_review(intake, policy)
    return result["findings"], result["open_questions"]


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command == "validate":
        intake = _load_validated_intake(arguments.intake)
        questions = validate_intake_semantics(intake)
        label = "Valid intake."
        if arguments.policy:
            policy = _load_validated_policy(arguments.policy)
            _, questions = evaluate_policy(intake, policy, questions)
            label = "Valid intake and policy."
        print(f"{label} Open questions: {len(questions)}")
        return 0

    if arguments.command == "review":
        intake = _load_validated_intake(arguments.intake)
        policy = _load_validated_policy(arguments.policy)
        findings, questions = _evaluate(intake, policy)
        provider = DeterministicProvider()
        if arguments.no_save:
            print(render_assessment(intake, policy, findings, questions, provider), end="")
            return 0
        output_root = arguments.output or Path("runs")
        run_directory = create_bundle(
            intake,
            policy,
            findings,
            questions,
            output_root=output_root,
            provider=provider,
        )
        print(run_directory.resolve())
        return 0

    if arguments.command == "decide":
        decision = load_document(arguments.decision_file)
        decision_path = record_decision(arguments.run_directory, decision)
        print(decision_path.resolve())
        return 0

    if arguments.command == "sanitize":
        output = sanitize_bundle(
            arguments.run_directory,
            arguments.output,
            arguments.sensitive_paths,
        )
        print(output.resolve())
        return 0

    raise ValidationError(f"unsupported command: {arguments.command}")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a stable process exit code."""

    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        return _dispatch(arguments)
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("internal error: unexpected failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
