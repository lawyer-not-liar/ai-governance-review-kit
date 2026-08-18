"""Structure-preserving sanitization of saved review bundles."""

import copy
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from .bundle import create_bundle, verify_bundle
from .decision import record_decision
from .errors import ValidationError
from .providers import DeterministicProvider

_REDACTED = "[REDACTED]"
_DEFAULT_REPLACEMENTS = {
    "request.id": "sanitized-request",
    "request.owner.name": _REDACTED,
    "request.owner.email": "redacted@example.invalid",
}


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {path.name}: {exc}") from exc


def _redact_path(
    document: dict[str, object], dotted_path: str, replacement: object = _REDACTED
) -> object:
    parts = dotted_path.split(".")
    if not parts or any(not part for part in parts):
        raise ValidationError(f"invalid sensitive path: {dotted_path}")
    current: object = document
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValidationError(f"sensitive path does not exist: {dotted_path}")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise ValidationError(f"sensitive path does not exist: {dotted_path}")
    original = current[parts[-1]]
    current[parts[-1]] = replacement
    return original


def _replacement_for(value: object) -> object:
    if isinstance(value, bool):
        return "unknown"
    if isinstance(value, list):
        return []
    return _REDACTED


def _redact_local_uris(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                key == "uri"
                and isinstance(child, str)
                and (child.startswith("/") or child.startswith("file://"))
            ):
                value[key] = _REDACTED
            else:
                _redact_local_uris(child)
    elif isinstance(value, list):
        for child in value:
            _redact_local_uris(child)


def _redact_finding_facts(findings: list[object], replacements: dict[str, object]) -> None:
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("facts"), list):
            continue
        for fact in finding["facts"]:
            if isinstance(fact, dict) and fact.get("path") in replacements:
                fact["value"] = replacements[str(fact["path"])]


def sanitize_bundle(
    run_directory: Path,
    output_directory: Path,
    sensitive_paths: list[str],
) -> Path:
    """Create a separate, verified bundle with selected values redacted."""

    verify_bundle(run_directory)
    source = run_directory.resolve()
    destination = output_directory.resolve()
    if destination == source or source in destination.parents:
        raise ValidationError("sanitized destination must be outside the source bundle")
    if output_directory.exists():
        raise ValidationError(f"sanitized destination already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)

    intake = _read_json(run_directory / "intake.normalized.json")
    findings = _read_json(run_directory / "findings.json")
    questions = _read_json(run_directory / "open-questions.json")
    manifest = _read_json(run_directory / "manifest.json")
    policy = _read_json(run_directory / "policy.snapshot.json")
    if not isinstance(intake, dict) or not isinstance(findings, list):
        raise ValidationError("bundle intake and findings have invalid structure")
    if not isinstance(questions, list) or not isinstance(manifest, dict):
        raise ValidationError("bundle questions and manifest have invalid structure")
    if not isinstance(policy, dict):
        raise ValidationError("bundle policy snapshot has invalid structure")

    sanitized_intake = copy.deepcopy(intake)
    sanitized_findings = copy.deepcopy(findings)
    replacements: dict[str, object] = dict(_DEFAULT_REPLACEMENTS)
    for path, replacement in sorted(_DEFAULT_REPLACEMENTS.items()):
        _redact_path(sanitized_intake, path, replacement)
    for path in sorted(set(sensitive_paths) - set(_DEFAULT_REPLACEMENTS)):
        original = _redact_path(sanitized_intake, path)
        replacement = _replacement_for(original)
        _redact_path(sanitized_intake, path, replacement)
        replacements[path] = replacement
    _redact_local_uris(sanitized_intake)
    _redact_finding_facts(sanitized_findings, replacements)

    created_at = manifest.get("created_at")
    if not isinstance(created_at, str):
        raise ValidationError("bundle manifest created_at is invalid")
    parsed_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    temporary_root = Path(tempfile.mkdtemp(prefix=".sanitize-", dir=output_directory.parent))
    try:
        built = create_bundle(
            sanitized_intake,
            policy,
            sanitized_findings,
            copy.deepcopy(questions),
            output_root=temporary_root,
            provider=DeterministicProvider(),
            now=parsed_time,
        )
        decision_path = run_directory / "human-decision.json"
        if decision_path.exists():
            decision = _read_json(decision_path)
            if not isinstance(decision, dict):
                raise ValidationError("human-decision.json must contain an object")
            sanitized_decision = copy.deepcopy(decision)
            sanitized_decision["reviewer"] = _REDACTED
            record_decision(built, sanitized_decision)
        os.replace(built, output_directory)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    shutil.rmtree(temporary_root, ignore_errors=True)
    verify_bundle(output_directory)
    return output_directory
