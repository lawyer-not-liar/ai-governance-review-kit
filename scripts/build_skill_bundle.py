#!/usr/bin/env python3
"""Build a clean, reproducible AI governance review skill archive."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

ARCHIVE_ROOT = "ai-governance-review"
SKILL_SOURCE = Path("skills/ai-governance-review")
ENGINE_SOURCE = Path("src/ai_governance_review")
RUNTIME_DESTINATION = Path("scripts/runtime/ai_governance_review")
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FORBIDDEN_BINARY_SUFFIXES = {".pyc", ".so", ".dylib", ".pyd"}
CANDIDATE_PREFIX = "ai-governance-skill-candidate-"


def validate_archive_path(name: str) -> None:
    """Reject archive names that are unsafe or outside the one allowed root."""

    path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != ARCHIVE_ROOT
    ):
        raise ValueError(f"unsafe archive path: {name!r}")


def _read_source(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError(f"symlink source is not allowed: {path}")
    if not path.is_file():
        raise ValueError(f"required source file is missing: {path}")
    if path.suffix.lower() in FORBIDDEN_BINARY_SUFFIXES:
        raise ValueError(f"binary source is not allowed: {path}")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError(f"binary source is not allowed: {path}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source is not UTF-8: {path}") from exc
    return data


def _reject_unsafe_entries(directory: Path) -> None:
    for entry in directory.iterdir():
        if entry.is_symlink():
            raise ValueError(f"symlink source is not allowed: {entry}")
        if entry.name.startswith("."):
            raise ValueError(f"hidden source is not allowed: {entry}")


def _skill_files(skill_root: Path) -> dict[str, bytes]:
    if skill_root.is_symlink() or not skill_root.is_dir():
        raise ValueError(f"required skill directory is invalid: {skill_root}")
    agents = skill_root / "agents"
    if agents.is_symlink() or not agents.is_dir():
        raise ValueError(f"required source directory is invalid: {agents}")
    files = {
        "SKILL.md": _read_source(skill_root / "SKILL.md"),
        "agents/openai.yaml": _read_source(agents / "openai.yaml"),
    }

    scripts = skill_root / "scripts"
    references = skill_root / "references"
    for directory in (scripts, references):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"required source directory is invalid: {directory}")
        _reject_unsafe_entries(directory)

    for source in sorted(scripts.iterdir(), key=lambda path: path.name):
        if source.is_file() and source.suffix == ".py":
            files[f"scripts/{source.name}"] = _read_source(source)

    for source in sorted(references.iterdir(), key=lambda path: path.name):
        if source.is_file():
            if source.name.startswith("."):
                raise ValueError(f"hidden source is not allowed: {source}")
            files[f"references/{source.name}"] = _read_source(source)
    return files


def _validate_engine_tree(engine_root: Path) -> None:
    if engine_root.is_symlink() or not engine_root.is_dir():
        raise ValueError(f"required engine directory is invalid: {engine_root}")
    for current, directory_names, file_names in os.walk(engine_root, followlinks=False):
        current_path = Path(current)
        directory_names[:] = sorted(directory_names)
        for directory_name in directory_names:
            directory = current_path / directory_name
            if directory.is_symlink():
                raise ValueError(f"symlink source is not allowed: {directory}")
            if directory_name.startswith("."):
                raise ValueError(f"hidden runtime directory is not allowed: {directory}")
        for file_name in file_names:
            source = current_path / file_name
            if source.is_symlink():
                raise ValueError(f"symlink source is not allowed: {source}")


def _engine_files(engine_root: Path) -> dict[str, bytes]:
    _validate_engine_tree(engine_root)
    selected = sorted(engine_root.glob("*.py"))
    schemas = engine_root / "schemas"
    if schemas.is_symlink() or not schemas.is_dir():
        raise ValueError(f"required schema directory is invalid: {schemas}")
    selected.extend(sorted(schemas.glob("*.json")))

    files: dict[str, bytes] = {}
    for source in selected:
        relative = source.relative_to(engine_root)
        destination = RUNTIME_DESTINATION / relative
        files[destination.as_posix()] = _read_source(source)
    return files


def _engine_version(init_source: bytes) -> str:
    module = ast.parse(init_source.decode("utf-8"))
    versions = []
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if (
            any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in statement.targets
            )
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            versions.append(statement.value.value)
    if len(versions) != 1 or not versions[0]:
        raise ValueError("engine __version__ must be one non-empty string assignment")
    return versions[0]


def _manifest(files: dict[str, bytes]) -> bytes:
    engine_version = _engine_version(files["scripts/runtime/ai_governance_review/__init__.py"])
    policy_document = json.loads(files["references/generic-policy.json"].decode("utf-8"))
    if not isinstance(policy_document, dict):
        raise ValueError("generic policy document must be an object")
    policy = policy_document.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("generic policy metadata must be an object")
    manifest = {
        "schema_version": "1.0",
        "skill": ARCHIVE_ROOT,
        "skill_version": engine_version,
        "engine_version": engine_version,
        "policy": policy,
        "files": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())},
    }
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _write_zip(staging_root: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source in sorted(path for path in staging_root.rglob("*") if path.is_file()):
            relative = source.relative_to(staging_root).as_posix()
            archive_name = f"{ARCHIVE_ROOT}/{relative}"
            validate_archive_path(archive_name)
            info = zipfile.ZipInfo(archive_name, date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)


def _resolve_output(output: Path) -> Path:
    requested_output = output.expanduser()
    if requested_output.is_symlink():
        raise ValueError(f"output path must not be a symlink: {requested_output}")
    if not requested_output.is_absolute():
        requested_output = Path.cwd() / requested_output
    return requested_output.resolve(strict=False)


def build_bundle(root: Path, output: Path) -> None:
    repository_root = root.expanduser().resolve(strict=True)
    if not repository_root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    resolved_output = _resolve_output(output)

    skill_files = _skill_files(repository_root / SKILL_SOURCE)
    engine_files = _engine_files(repository_root / ENGINE_SOURCE)
    files = {**skill_files, **engine_files}
    for relative in files:
        validate_archive_path(f"{ARCHIVE_ROOT}/{relative}")
    manifest = _manifest(files)

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="ai-governance-skill-", dir=resolved_output.parent
    ) as temporary:
        temporary_root = Path(temporary)
        staging_root = temporary_root / ARCHIVE_ROOT
        for relative, data in sorted(files.items()):
            destination = staging_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (staging_root / "manifest.json").write_bytes(manifest)
        temporary_archive = temporary_root / "bundle.zip"
        _write_zip(staging_root, temporary_archive)
        os.replace(temporary_archive, resolved_output)


def build_verified_bundle(root: Path, output: Path) -> None:
    """Build, verify, and atomically publish one candidate archive."""

    resolved_output = _resolve_output(output)
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=CANDIDATE_PREFIX, dir=resolved_output.parent
    ) as temporary:
        candidate = Path(temporary) / "candidate.zip"
        build_bundle(root, candidate)
        verify_bundle(root, candidate)
        os.replace(candidate, resolved_output)


def _run_smoke_command(
    command: list[str], *, cwd: Path, environment: dict[str, str], stage: str
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"{stage} smoke check failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{stage} smoke check produced invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ValueError(f"{stage} smoke check was not successful")


def verify_bundle(root: Path, archive_path: Path) -> None:
    """Smoke-test an extracted bundle outside the repository."""

    repository_root = root.expanduser().resolve(strict=True)
    built_archive = archive_path.expanduser().resolve(strict=True)
    source_intake = repository_root / "examples/intakes/example-assistant.yaml"
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ValueError("PyYAML is required for the verification smoke check") from exc

    with tempfile.TemporaryDirectory(prefix="ai-governance-skill-verify-") as temporary:
        temporary_root = Path(temporary)
        extracted = temporary_root / "extracted"
        with zipfile.ZipFile(built_archive) as archive:
            archive.extractall(extracted)
        runner = extracted / ARCHIVE_ROOT / "scripts/review_ai_use.py"
        outside = temporary_root / "outside"
        outside.mkdir()
        intake = outside / "intake.json"
        intake.write_text(
            json.dumps(yaml.safe_load(source_intake.read_text(encoding="utf-8"))),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)

        _run_smoke_command(
            [sys.executable, "-S", str(runner), "self-check"],
            cwd=outside,
            environment=environment,
            stage="self-check",
        )
        _run_smoke_command(
            [sys.executable, "-S", str(runner), "analyze", "--intake", str(intake)],
            cwd=outside,
            environment=environment,
            stage="analysis",
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="build and smoke-test an extracted bundle in a temporary directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.verify:
            build_verified_bundle(arguments.root, arguments.output)
        else:
            build_bundle(arguments.root, arguments.output)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
