import os
import subprocess
import sys
from pathlib import Path

import yaml

from ai_governance_review import cli
from ai_governance_review.loader import load_document
from ai_governance_review.policy import evaluate_policy
from ai_governance_review.providers import DeterministicProvider
from ai_governance_review.render import render_assessment
from ai_governance_review.validation import validate_intake_semantics

PROJECT_ROOT = Path(__file__).parents[1]
INTAKE = PROJECT_ROOT / "examples" / "intakes" / "example-assistant.yaml"
POLICY = PROJECT_ROOT / "policies" / "example"
DECISION = PROJECT_ROOT / "examples" / "decisions" / "example-decision.yaml"


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    source_path = str(PROJECT_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in [source_path, environment.get("PYTHONPATH", "")] if part
    )
    return subprocess.run(
        [sys.executable, "-m", "ai_governance_review.cli", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_accepts_synthetic_intake(tmp_path):
    result = run_cli("validate", str(INTAKE), "--policy", str(POLICY), cwd=tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "Valid intake and policy. Open questions: 0"


def test_review_no_save_prints_assessment_without_creating_runs(tmp_path):
    result = run_cli(
        "review",
        str(INTAKE),
        "--policy",
        str(POLICY),
        "--no-save",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert "DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED" in result.stdout
    assert not (tmp_path / "runs").exists()


def test_review_no_save_preserves_existing_assessment_output(tmp_path):
    intake = load_document(INTAKE)
    policy = load_document(POLICY / "policy.yaml")
    findings, questions = evaluate_policy(intake, policy, validate_intake_semantics(intake))
    expected = render_assessment(
        intake,
        policy,
        findings,
        questions,
        DeterministicProvider(),
    )

    result = run_cli(
        "review",
        str(INTAKE),
        "--policy",
        str(POLICY),
        "--no-save",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == expected


def test_review_no_save_is_deterministic(tmp_path):
    arguments = (
        "review",
        str(INTAKE),
        "--policy",
        str(POLICY),
        "--no-save",
    )

    first = run_cli(*arguments, cwd=tmp_path)
    second = run_cli(*arguments, cwd=tmp_path)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr == ""


def test_end_to_end_review_decide_and_sanitize(tmp_path):
    runs = tmp_path / "runs"
    review = run_cli(
        "review",
        str(INTAKE),
        "--policy",
        str(POLICY),
        "--output",
        str(runs),
        cwd=tmp_path,
    )
    assert review.returncode == 0, review.stderr
    run_directory = Path(review.stdout.strip())
    assert run_directory.is_dir()

    decide = run_cli(
        "decide",
        str(run_directory),
        "--decision-file",
        str(DECISION),
        cwd=tmp_path,
    )
    assert decide.returncode == 0, decide.stderr
    assert (run_directory / "human-decision.json").is_file()

    sanitized_directory = tmp_path / "sanitized"
    sanitize = run_cli(
        "sanitize",
        str(run_directory),
        "--output",
        str(sanitized_directory),
        "--path",
        "purpose.summary",
        cwd=tmp_path,
    )
    assert sanitize.returncode == 0, sanitize.stderr
    assert sanitized_directory.is_dir()
    assert "Alex Example" not in (sanitized_directory / "draft-assessment.md").read_text()


def test_invalid_input_returns_two_and_actionable_error(tmp_path):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("schema_version: '1.0'\nunexpected: true\n", encoding="utf-8")

    result = run_cli("validate", str(invalid), cwd=tmp_path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "intake validation failed" in result.stderr


def test_unexpected_internal_error_returns_one_without_exception_details(monkeypatch, capsys):
    def fail(_arguments):
        raise RuntimeError("token=must-not-be-printed")

    monkeypatch.setattr(cli, "_dispatch", fail)

    assert cli.main(["validate", str(INTAKE)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "internal error: unexpected failure\n"
    assert "token" not in captured.err


def test_review_rejects_output_with_no_save(tmp_path):
    result = run_cli(
        "review",
        str(INTAKE),
        "--policy",
        str(POLICY),
        "--output",
        str(tmp_path / "runs"),
        "--no-save",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr


def test_review_rejects_superseded_policy(tmp_path):
    policy = load_document(POLICY / "policy.yaml")
    policy["policy"]["status"] = "superseded"
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    result = run_cli(
        "review",
        str(INTAKE),
        "--policy",
        str(policy_path),
        "--no-save",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "superseded policy" in result.stderr
