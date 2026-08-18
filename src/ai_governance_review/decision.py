"""Human decision recording with bundle-integrity enforcement."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .bundle import verify_bundle
from .errors import ValidationError
from .validation import validate_document


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {path.name}: {exc}") from exc


def _write_temporary(directory: Path, suffix: str, content: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=".decision-", suffix=suffix, dir=directory)
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def record_decision(run_directory: Path, decision: dict[str, object]) -> Path:
    """Append one verified human decision to an immutable draft review bundle."""

    verify_bundle(run_directory)
    decision_path = run_directory / "human-decision.json"
    if decision_path.exists():
        raise ValidationError("review bundle already contains a human decision")
    validate_document(decision, "decision")

    reviewer = decision.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValidationError("decision reviewer must be non-empty")
    manifest = _read_json(run_directory / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValidationError("manifest must be an object")
    if decision.get("policy") != manifest.get("policy"):
        raise ValidationError("decision policy does not match the reviewed bundle policy")

    findings = _read_json(run_directory / "findings.json")
    if not isinstance(findings, list):
        raise ValidationError("findings.json must contain a list")
    open_questions = _read_json(run_directory / "open-questions.json")
    if not isinstance(open_questions, list):
        raise ValidationError("open-questions.json must contain a list")
    blocking = {
        str(finding.get("id"))
        for finding in findings
        if isinstance(finding, dict)
        and finding.get("severity") == "block"
        and finding.get("status") in {"triggered", "needs_information"}
    }
    overrides = decision.get("overrides", [])
    override_ids: set[str] = set()
    if isinstance(overrides, list):
        for override in overrides:
            if not isinstance(override, dict):
                continue
            finding_id = override.get("finding_id")
            rationale = override.get("rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValidationError("every override requires a non-empty rationale")
            if isinstance(finding_id, str):
                override_ids.add(finding_id)

    if decision.get("decision") in {"approved", "approved_with_conditions"}:
        if open_questions:
            raise ValidationError(
                "approval requires all unresolved open questions to be resolved "
                "in a regenerated review bundle"
            )
        unaddressed = sorted(blocking - override_ids)
        if unaddressed:
            raise ValidationError(
                "approval must document an override for blocking finding(s): "
                + ", ".join(unaddressed)
            )
        if decision.get("decision") == "approved_with_conditions" and not decision.get(
            "conditions"
        ):
            raise ValidationError("approved_with_conditions requires at least one condition")

    decision_bytes = _json_bytes(decision)
    decision_temp = _write_temporary(run_directory, ".json", decision_bytes)
    manifest_path = run_directory / "manifest.json"
    original_manifest_bytes = manifest_path.read_bytes()
    updated_manifest = dict(manifest)
    artifacts = dict(updated_manifest.get("artifacts", {}))
    artifacts[decision_path.name] = hashlib.sha256(decision_bytes).hexdigest()
    updated_manifest["artifacts"] = artifacts
    validate_document(updated_manifest, "manifest")
    manifest_temp = _write_temporary(run_directory, ".json", _json_bytes(updated_manifest))
    decision_installed = False
    manifest_installed = False

    try:
        os.replace(decision_temp, decision_path)
        decision_installed = True
        os.replace(manifest_temp, manifest_path)
        manifest_installed = True
        verify_bundle(run_directory)
    except Exception:
        decision_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)
        if decision_installed:
            decision_path.unlink(missing_ok=True)
        if manifest_installed:
            rollback_temp = _write_temporary(run_directory, ".json", original_manifest_bytes)
            try:
                os.replace(rollback_temp, manifest_path)
            finally:
                rollback_temp.unlink(missing_ok=True)
        raise
    return decision_path
