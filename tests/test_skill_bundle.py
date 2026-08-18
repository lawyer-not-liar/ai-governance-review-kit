import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pytest
import yaml

ROOT = Path(__file__).parents[1]
BUILDER = ROOT / "scripts/build_skill_bundle.py"
SKILL_SOURCE = ROOT / "skills/ai-governance-review"
ENGINE_SOURCE = ROOT / "src/ai_governance_review"
ARCHIVE_ROOT = "ai-governance-review"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _build(root: Path, output: Path, *, verify: bool = False) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(BUILDER), "--root", str(root), "--output", str(output)]
    if verify:
        command.append("--verify")
    return subprocess.run(
        command,
        cwd=root.parent,
        text=True,
        capture_output=True,
        check=False,
    )


def _copy_bundle_sources(destination: Path) -> Path:
    root = destination / "repository"
    shutil.copytree(SKILL_SOURCE, root / "skills/ai-governance-review")
    shutil.copytree(ENGINE_SOURCE, root / "src/ai_governance_review")
    return root


def _copy_verifier_sources(destination: Path) -> Path:
    root = _copy_bundle_sources(destination)
    shutil.copytree(ROOT / "examples", root / "examples")
    return root


def _load_builder_module():
    spec = importlib.util.spec_from_file_location("skill_bundle_builder", BUILDER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_has_one_safe_root_and_verified_manifest(tmp_path: Path) -> None:
    output = tmp_path / "ai-governance-review-skill.zip"

    completed = _build(ROOT, output)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert names
        assert names == sorted(names)
        assert {PurePosixPath(name).parts[0] for name in names} == {ARCHIVE_ROOT}
        assert all(name.startswith(f"{ARCHIVE_ROOT}/") for name in names)
        assert not any(".runtime-deps" in name for name in names)
        assert not any(
            "__pycache__" in name or name.endswith((".pyc", ".so", ".dylib", ".pyd"))
            for name in names
        )
        assert not any(
            part in {".git", ".repository-local-denylist", "tests", ".coverage"}
            for name in names
            for part in PurePosixPath(name).parts
        )
        assert f"{ARCHIVE_ROOT}/SKILL.md" in names
        assert f"{ARCHIVE_ROOT}/manifest.json" in names
        assert f"{ARCHIVE_ROOT}/scripts/runtime/ai_governance_review/analysis.py" in names

        manifest = json.loads(archive.read(f"{ARCHIVE_ROOT}/manifest.json"))
        assert set(manifest) == {
            "schema_version",
            "skill",
            "skill_version",
            "engine_version",
            "policy",
            "files",
        }
        assert manifest["schema_version"] == "1.0"
        assert manifest["skill"] == ARCHIVE_ROOT
        assert manifest["skill_version"] == "0.1.2"
        assert manifest["engine_version"] == "0.1.2"
        canonical_policy = yaml.safe_load(
            (ROOT / "policies/example/policy.yaml").read_text(encoding="utf-8")
        )
        assert manifest["policy"] == canonical_policy["policy"]

        expected_files = {
            name.removeprefix(f"{ARCHIVE_ROOT}/")
            for name in names
            if name != f"{ARCHIVE_ROOT}/manifest.json"
        }
        assert set(manifest["files"]) == expected_files
        for relative_path, digest in manifest["files"].items():
            assert digest == digest.lower()
            assert len(digest) == 64
            int(digest, 16)
            assert (
                digest
                == hashlib.sha256(archive.read(f"{ARCHIVE_ROOT}/{relative_path}")).hexdigest()
            )

        assert all(info.date_time == FIXED_TIMESTAMP for info in archive.infolist())


def test_extracted_bundle_runs_from_runtime_outside_repository(tmp_path: Path) -> None:
    output = tmp_path / "skill.zip"
    completed = _build(ROOT, output)
    assert completed.returncode == 0, completed.stderr

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
    skill = extracted / ARCHIVE_ROOT
    runner = skill / "scripts/review_ai_use.py"
    outside = tmp_path / "outside"
    outside.mkdir()
    intake = outside / "intake.json"
    intake.write_text(
        json.dumps(
            yaml.safe_load(
                (ROOT / "examples/intakes/example-assistant.yaml").read_text(encoding="utf-8")
            )
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    self_check = subprocess.run(
        [sys.executable, "-S", str(runner), "self-check"],
        cwd=outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    analysis = subprocess.run(
        [sys.executable, "-S", str(runner), "analyze", "--intake", str(intake)],
        cwd=outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_intake = outside / "invalid-intake.json"
    invalid_document = json.loads(intake.read_text(encoding="utf-8"))
    invalid_document["unexpected"] = True
    invalid_intake.write_text(json.dumps(invalid_document), encoding="utf-8")
    invalid_analysis = subprocess.run(
        [sys.executable, "-S", str(runner), "analyze", "--intake", str(invalid_intake)],
        cwd=outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    origin_probe = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                "import importlib.util, pathlib; "
                f"p = pathlib.Path({str(runner)!r}); "
                "s = importlib.util.spec_from_file_location('extracted_runner', p); "
                "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m._configure_import_paths(); "
                "import ai_governance_review.analysis as a; "
                "print(pathlib.Path(a.__file__).resolve())"
            ),
        ],
        cwd=outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert self_check.returncode == 0
    assert json.loads(self_check.stdout) == {"ok": True, "result": {"status": "available"}}
    assert self_check.stderr == ""
    assert analysis.returncode == 0
    payload = json.loads(analysis.stdout)
    assert payload["ok"] is True
    assert len(payload["result"]["findings"]) == 6
    assert analysis.stderr == ""
    assert invalid_analysis.returncode == 2
    assert json.loads(invalid_analysis.stdout)["error"]["kind"] == "validation"
    assert invalid_analysis.stderr == ""
    assert origin_probe.returncode == 0, origin_probe.stderr
    imported_path = Path(origin_probe.stdout.strip())
    assert imported_path.is_relative_to(skill / "scripts/runtime/ai_governance_review")


def test_extracted_portable_runtime_preserves_all_alpha_scenarios(tmp_path: Path) -> None:
    output = tmp_path / "skill.zip"
    completed = _build(ROOT, output)
    assert completed.returncode == 0, completed.stderr

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
    runner = extracted / ARCHIVE_ROOT / "scripts/review_ai_use.py"
    outside = tmp_path / "outside"
    outside.mkdir()
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    manifest = yaml.safe_load((ROOT / "examples/alpha/scenarios.yaml").read_text(encoding="utf-8"))

    for scenario in manifest["scenarios"]:
        policy_source = scenario.get("policy", "policies/example/policy.yaml")
        intake_path = outside / f"{scenario['id']}-intake.json"
        intake_path.write_text(
            json.dumps(yaml.safe_load((ROOT / scenario["intake"]).read_text(encoding="utf-8"))),
            encoding="utf-8",
        )
        command = [
            sys.executable,
            "-S",
            str(runner),
            "analyze",
            "--intake",
            str(intake_path),
        ]
        if scenario.get("policy"):
            policy_path = outside / f"{scenario['id']}-policy.json"
            policy_path.write_text(
                json.dumps(yaml.safe_load((ROOT / policy_source).read_text(encoding="utf-8"))),
                encoding="utf-8",
            )
            command.extend(["--policy", str(policy_path)])

        result = subprocess.run(
            command,
            cwd=outside,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, f"{scenario['id']}: {result.stdout}{result.stderr}"
        payload = json.loads(result.stdout)
        analysis = payload["result"]
        actual_statuses = {item["rule_id"]: item["status"] for item in analysis["findings"]}
        assert actual_statuses == scenario["expected"]["findings"], scenario["id"]
        assert [item["id"] for item in analysis["open_questions"]] == scenario["expected"][
            "open_questions"
        ], scenario["id"]
        assert analysis["blocking_findings"] == scenario["expected"]["blocking_findings"], scenario[
            "id"
        ]
        expected_policy = yaml.safe_load((ROOT / policy_source).read_text(encoding="utf-8"))[
            "policy"
        ]
        expected_statuses = scenario["expected"]["findings"]
        expected_active = [
            status
            for status in expected_statuses.values()
            if status in {"triggered", "needs_information"}
        ]
        assert analysis["presentation_facts"] == {
            "policy": {
                "id": expected_policy["id"],
                "version": expected_policy["version"],
                "status": expected_policy["status"],
            },
            "active_findings": {
                "total": len(expected_active),
                "triggered": expected_active.count("triggered"),
                "needs_information": expected_active.count("needs_information"),
                "blocking": len(scenario["expected"]["blocking_findings"]),
            },
            "open_questions": len(scenario["expected"]["open_questions"]),
            "draft_heading": "# DRAFT ASSESSMENT - HUMAN REVIEW REQUIRED",
        }, scenario["id"]
        presentation_text = analysis["presentation_text"]
        assert presentation_text.startswith("Review result"), scenario["id"]
        assert "not_applicable" not in presentation_text, scenario["id"]
        for rule_id, status in expected_statuses.items():
            if status in {"triggered", "needs_information"}:
                assert rule_id in presentation_text, scenario["id"]
            else:
                assert rule_id not in presentation_text, scenario["id"]


def test_damaged_extracted_bundle_rejects_unrelated_ancestor_source(tmp_path: Path) -> None:
    output = tmp_path / "skill.zip"
    completed = _build(ROOT, output)
    assert completed.returncode == 0, completed.stderr

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
    skill = extracted / ARCHIVE_ROOT
    shutil.rmtree(skill / "scripts/runtime")
    shutil.copytree(ENGINE_SOURCE, tmp_path / "src/ai_governance_review")
    outside = tmp_path / "outside"
    outside.mkdir()
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    self_check = subprocess.run(
        [sys.executable, str(skill / "scripts/review_ai_use.py"), "self-check"],
        cwd=outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert self_check.returncode == 3
    assert self_check.stderr == ""
    payload = json.loads(self_check.stdout)
    assert payload["ok"] is False
    assert payload["error"] == {
        "kind": "runtime_unavailable",
        "message": "required skill runtime dependencies are unavailable",
    }


def test_verify_builds_and_smoke_tests_an_extracted_bundle(tmp_path: Path) -> None:
    output = tmp_path / "skill.zip"

    completed = _build(ROOT, output, verify=True)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert output.is_file()
    assert not any(ROOT.glob("ai-governance-skill-verify-*"))
    assert not (ROOT / "extracted").exists()
    assert not (ROOT / "reviews").exists()


def test_verify_runs_extracted_runner_with_clean_environment_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _load_builder_module()
    root = _copy_verifier_sources(tmp_path)
    archive = tmp_path / "skill.zip"
    builder.build_bundle(root, archive)
    calls: list[tuple[list[str], Path]] = []
    monkeypatch.setenv("PYTHONPATH", "must-not-reach-the-extracted-runner")

    def fake_run(
        command: list[str], *, cwd: Path, env: dict[str, str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        assert command[1] == "-S"
        runner = Path(command[2])
        assert runner.is_file()
        assert cwd.is_dir()
        assert not cwd.is_relative_to(root)
        assert "PYTHONPATH" not in env
        calls.append((command, cwd))
        if command[3] == "self-check":
            return subprocess.CompletedProcess(
                command, 0, stdout='{"ok": true, "result": {}}', stderr=""
            )
        intake = Path(command[-1])
        assert intake.suffix == ".json"
        assert (
            json.loads(intake.read_text(encoding="utf-8"))["request"]["id"] == "example-assistant-1"
        )
        return subprocess.CompletedProcess(
            command, 0, stdout='{"ok": true, "result": {}}', stderr=""
        )

    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    builder.verify_bundle(root, archive)

    assert [command[3] for command, _ in calls] == ["self-check", "analyze"]
    temporary_root = calls[0][1].parent
    extracted_skill_root = (temporary_root / "extracted" / ARCHIVE_ROOT).resolve()
    runner_paths = [Path(command[2]).resolve() for command, _ in calls]
    assert all(path.is_relative_to(extracted_skill_root) for path in runner_paths)
    assert all(not path.is_relative_to(root) for path in runner_paths)
    assert not temporary_root.exists()
    assert not any(root.glob("ai-governance-skill-verify-*"))
    assert not (root / "extracted").exists()
    assert not (root / "reviews").exists()


def test_verify_checks_candidate_before_replacing_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _load_builder_module()
    root = _copy_verifier_sources(tmp_path)
    output = tmp_path / "skill.zip"
    original = b"known-good artifact"
    output.write_bytes(original)
    checked_candidates: list[Path] = []

    def fake_verify_bundle(repository_root: Path, archive_path: Path) -> None:
        assert repository_root == root
        assert output.read_bytes() == original
        assert archive_path != output
        with zipfile.ZipFile(archive_path) as archive:
            assert f"{ARCHIVE_ROOT}/manifest.json" in archive.namelist()
        checked_candidates.append(archive_path)

    monkeypatch.setattr(builder, "verify_bundle", fake_verify_bundle)

    result = builder.main(["--root", str(root), "--output", str(output), "--verify"])

    assert result == 0
    assert len(checked_candidates) == 1
    assert not checked_candidates[0].exists()
    with zipfile.ZipFile(output) as archive:
        assert f"{ARCHIVE_ROOT}/manifest.json" in archive.namelist()


@pytest.mark.parametrize(
    ("responses", "expected_error", "expected_calls"),
    [
        (
            [(7, '{"ok": true}', "sensitive child output"), (0, '{"ok": true}', "")],
            "self-check smoke check failed",
            1,
        ),
        (
            [(0, '{"ok": true}', ""), (8, '{"ok": true}', "sensitive child output")],
            "analysis smoke check failed",
            2,
        ),
        (
            [(0, "not JSON", ""), (0, '{"ok": true}', "")],
            "self-check smoke check produced invalid JSON",
            1,
        ),
        (
            [
                (0, '{"ok": false, "error": "sensitive child output"}', ""),
                (0, '{"ok": true}', ""),
            ],
            "self-check smoke check was not successful",
            1,
        ),
    ],
    ids=["self-check-nonzero", "analyze-nonzero", "invalid-json", "unsuccessful-envelope"],
)
def test_verify_returns_controlled_failure_for_unsuccessful_smoke_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    responses: list[tuple[int, str, str]],
    expected_error: str,
    expected_calls: int,
) -> None:
    builder = _load_builder_module()
    root = _copy_verifier_sources(tmp_path)
    output = tmp_path / "skill.zip"
    original = b"known-good artifact"
    output.write_bytes(original)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        returncode, stdout, stderr = responses.pop(0)
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(builder.subprocess, "run", fake_run)

    result = builder.main(["--root", str(root), "--output", str(output), "--verify"])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == f"build failed: {expected_error}\n"
    assert "sensitive child output" not in captured.err
    assert len(calls) == expected_calls
    assert output.read_bytes() == original
    assert not any(root.glob("ai-governance-skill-verify-*"))
    assert not (root / "extracted").exists()
    assert not (root / "reviews").exists()


@pytest.mark.parametrize(
    ("behavior", "expected_error"),
    [
        ("self-check-nonzero", "self-check smoke check failed"),
        ("analysis-nonzero", "analysis smoke check failed"),
        ("invalid-json", "self-check smoke check produced invalid JSON"),
        ("unsuccessful-envelope", "self-check smoke check was not successful"),
    ],
)
@pytest.mark.parametrize("existing_output", [False, True], ids=["no-prior-output", "known-good"])
def test_verify_failure_never_publishes_candidate_black_box(
    tmp_path: Path,
    behavior: str,
    expected_error: str,
    existing_output: bool,
) -> None:
    root = _copy_verifier_sources(tmp_path)
    runner = root / "skills/ai-governance-review/scripts/review_ai_use.py"
    runner.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

command = sys.argv[1]
behavior = {behavior!r}
if behavior == "self-check-nonzero" and command == "self-check":
    print("private child diagnostic", file=sys.stderr)
    raise SystemExit(7)
if behavior == "analysis-nonzero" and command == "analyze":
    print("private child diagnostic", file=sys.stderr)
    raise SystemExit(8)
if behavior == "invalid-json" and command == "self-check":
    print("not JSON")
elif behavior == "unsuccessful-envelope" and command == "self-check":
    print(json.dumps({{"ok": False, "error": "private child diagnostic"}}))
else:
    print(json.dumps({{"ok": True, "result": {{}}}}))
""",
        encoding="utf-8",
    )
    output = tmp_path / "release-looking.zip"
    original = b"known-good artifact"
    if existing_output:
        output.write_bytes(original)

    completed = _build(root, output, verify=True)

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == f"build failed: {expected_error}\n"
    assert "private child diagnostic" not in completed.stderr
    if existing_output:
        assert output.read_bytes() == original
    else:
        assert not output.exists()
    assert not any(tmp_path.glob("ai-governance-skill-candidate-*"))


def test_two_builds_are_byte_for_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_result = _build(ROOT, first)
    second_result = _build(ROOT, second)

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_runtime_dependencies_and_repository_artifacts_are_not_bundled(tmp_path: Path) -> None:
    root = _copy_bundle_sources(tmp_path)
    excluded = {
        root / "skills/ai-governance-review/.runtime-deps/private.py": "private",
        root / "skills/ai-governance-review/scripts/__pycache__/runner.pyc": "cache",
        root / "skills/ai-governance-review/.git/config": "config",
        root / ".repository-local-denylist": "local exclusion",
    }
    for path, contents in excluded.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    output = tmp_path / "clean.zip"
    completed = _build(root, output)

    assert completed.returncode == 0, completed.stderr
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    assert not any(
        token in name
        for name in names
        for token in (".runtime-deps", "__pycache__", ".git", ".repository-local-denylist")
    )


@pytest.mark.parametrize("unsafe_name", ["/absolute", "../escape", "root/../escape", "C:/escape"])
def test_archive_path_validator_rejects_absolute_and_parent_paths(unsafe_name: str) -> None:
    builder = _load_builder_module()

    with pytest.raises(ValueError, match="unsafe archive path"):
        builder.validate_archive_path(unsafe_name)


@pytest.mark.parametrize(
    "invalid_source",
    [
        "symlink",
        "symlink_directory",
        "hidden_runtime",
        "hidden_skill_file",
        "binary",
        "non_utf8",
        "invalid_policy",
    ],
)
def test_invalid_source_does_not_replace_existing_output(
    tmp_path: Path, invalid_source: str
) -> None:
    root = _copy_bundle_sources(tmp_path)
    if invalid_source == "symlink":
        selected = root / "skills/ai-governance-review/scripts/review_ai_use.py"
        selected.unlink()
        selected.symlink_to(root / "skills/ai-governance-review/SKILL.md")
    elif invalid_source == "symlink_directory":
        agents = root / "skills/ai-governance-review/agents"
        external_agents = tmp_path / "external-agents"
        shutil.copytree(agents, external_agents)
        shutil.rmtree(agents)
        agents.symlink_to(external_agents, target_is_directory=True)
    elif invalid_source == "hidden_runtime":
        hidden = root / "src/ai_governance_review/.hidden"
        hidden.mkdir()
        (hidden / "module.py").write_text("SECRET = True\n", encoding="utf-8")
    elif invalid_source == "hidden_skill_file":
        (root / "skills/ai-governance-review/scripts/.private.py").write_text(
            "SECRET = True\n", encoding="utf-8"
        )
    elif invalid_source == "binary":
        (root / "skills/ai-governance-review/references/unsafe.so").write_bytes(b"binary")
    elif invalid_source == "non_utf8":
        (root / "skills/ai-governance-review/references/invalid.txt").write_bytes(b"\xff")
    else:
        (root / "skills/ai-governance-review/references/generic-policy.json").write_text(
            "[]\n", encoding="utf-8"
        )

    output = tmp_path / "existing.zip"
    original = b"existing output must survive"
    output.write_bytes(original)

    completed = _build(root, output)

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert completed.stderr.startswith("build failed:")
    assert output.read_bytes() == original
