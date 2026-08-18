from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
RUNNER = PROJECT_ROOT / "scripts" / "run_alpha_validation.py"


def load_alpha_scenarios() -> dict[str, dict]:
    source = PROJECT_ROOT / "examples" / "alpha" / "scenarios.yaml"
    manifest = yaml.safe_load(source.read_text(encoding="utf-8"))
    return {scenario["id"]: scenario for scenario in manifest["scenarios"]}


def load_project_yaml(relative_path: str) -> dict:
    return yaml.safe_load((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_alpha_runner_validates_all_golden_scenarios() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--root", str(PROJECT_ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "12/12 alpha scenarios passed." in result.stdout


def test_alpha_scenarios_cover_non_training_personal_and_external_matrix() -> None:
    scenarios = load_alpha_scenarios()
    expected = {
        "low-risk-assistant": (
            "examples/alpha/intakes/01-low-risk-assistant.yaml",
            False,
            False,
            False,
        ),
        "external-distribution": (
            "examples/alpha/intakes/06-external-distribution.yaml",
            False,
            False,
            True,
        ),
        "personal-data-missing-evidence": (
            "examples/alpha/intakes/02-personal-data-missing-evidence.yaml",
            True,
            False,
            False,
        ),
        "personal-data-external-distribution": (
            "examples/alpha/intakes/12-personal-data-external-distribution.yaml",
            True,
            False,
            True,
        ),
    }

    actual = {}
    for scenario_id in expected:
        scenario = scenarios[scenario_id]
        intake = load_project_yaml(scenario["intake"])
        values = (
            intake["data"]["personal_data"],
            intake["data"]["training_or_fine_tuning"],
            intake["outputs"]["external_distribution"],
        )
        assert all(type(value) is bool for value in values)
        actual[scenario_id] = (
            scenario["intake"],
            *values,
        )

    assert actual == expected


def test_alpha_scenarios_preserve_training_contracts() -> None:
    scenarios = load_alpha_scenarios()
    contracts = {
        "training-missing-evidence": ("needs_information", "declined", False),
        "training-with-documented-override": ("triggered", "approved", True),
        "combined-high-risk-decline": ("triggered", "declined", False),
    }

    for scenario_id, (finding_status, decision_status, requires_override) in contracts.items():
        scenario = scenarios[scenario_id]
        intake = load_project_yaml(scenario["intake"])
        decision = load_project_yaml(scenario["decision"])

        assert intake["data"]["training_or_fine_tuning"] is True
        assert scenario["expected"]["findings"]["EXAMPLE-DATA-2"] == finding_status
        assert "finding-EXAMPLE-DATA-2" in scenario["expected"]["blocking_findings"]
        assert scenario["expected"]["decision"] == decision_status
        assert decision["decision"] == decision_status

        if requires_override:
            assert {item["finding_id"] for item in decision["overrides"]} == {
                "finding-EXAMPLE-DATA-2"
            }
            assert all(item["rationale"].strip() for item in decision["overrides"])


def test_alpha_runner_writes_human_review_workbook(tmp_path: Path) -> None:
    report_path = tmp_path / "alpha-review.md"

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(PROJECT_ROOT),
            "--report",
            str(report_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = report_path.read_text(encoding="utf-8")
    assert report.count("## Scenario ") == 12
    assert "### Generated draft assessment" in report
    assert "### Human usefulness scorecard" in report


def test_alpha_runner_rejects_golden_expectation_drift(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "examples" / "alpha" / "scenarios.yaml"
    manifest = yaml.safe_load(source.read_text(encoding="utf-8"))
    manifest["scenarios"][0]["expected"]["findings"]["EXAMPLE-DATA-1"] = "triggered"
    changed_manifest = tmp_path / "changed-scenarios.yaml"
    changed_manifest.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(PROJECT_ROOT),
            "--scenarios",
            str(changed_manifest),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "FAIL low-risk-assistant" in result.stdout
    assert '"EXAMPLE-DATA-1": "triggered"' in result.stdout


def test_alpha_runner_rejects_unknown_manifest_version(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "examples" / "alpha" / "scenarios.yaml"
    manifest = yaml.safe_load(source.read_text(encoding="utf-8"))
    manifest["schema_version"] = "2.0"
    changed_manifest = tmp_path / "changed-scenarios.yaml"
    changed_manifest.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(PROJECT_ROOT),
            "--scenarios",
            str(changed_manifest),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "unsupported scenario manifest version" in result.stderr
