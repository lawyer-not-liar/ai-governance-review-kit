"""Creation and integrity verification for review bundles."""

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .errors import ValidationError
from .providers import NarrativeProvider
from .render import render_assessment
from .validation import validate_document

_ARTIFACT_NAMES = (
    "intake.normalized.json",
    "findings.json",
    "evidence.json",
    "open-questions.json",
    "policy.snapshot.json",
    "draft-assessment.md",
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bytes(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _run_id(intake: dict[str, object], now: datetime) -> str:
    request = intake.get("request", {})
    request_id = request.get("id") if isinstance(request, dict) else None
    if not isinstance(request_id, str) or not request_id:
        raise ValidationError("intake request.id is required to create a bundle")
    timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{request_id}-{timestamp}"


def create_bundle(
    intake: dict[str, object],
    policy: dict[str, object],
    findings: list[dict[str, object]],
    questions: list[dict[str, object]],
    *,
    output_root: Path,
    provider: NarrativeProvider,
    now: datetime | None = None,
) -> Path:
    """Atomically write a complete, hash-addressed review bundle."""

    validate_document(intake, "intake")
    validate_document(policy, "policy")
    validate_document(findings, "findings")
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        raise ValidationError("bundle generation time must include a timezone")
    run_id = _run_id(intake, generated_at)
    output_root.mkdir(parents=True, exist_ok=True)
    final_directory = output_root / run_id
    if final_directory.exists():
        raise ValidationError(f"review run already exists: {final_directory}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=output_root))
    try:
        evidence = intake.get("evidence", [])
        assessment = render_assessment(intake, policy, findings, questions, provider)
        payloads = {
            "intake.normalized.json": _json_bytes(intake),
            "findings.json": _json_bytes(findings),
            "evidence.json": _json_bytes(evidence),
            "open-questions.json": _json_bytes(questions),
            "policy.snapshot.json": _json_bytes(policy),
            "draft-assessment.md": assessment.encode("utf-8"),
        }
        for name in _ARTIFACT_NAMES:
            _write_bytes(temporary / name, payloads[name])

        request = intake["request"]
        metadata = policy["policy"]
        if not isinstance(request, dict) or not isinstance(metadata, dict):
            raise ValidationError("validated intake and policy metadata are required")
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "request_id": request["id"],
            "created_at": generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "tool_version": __version__,
            "policy": {"id": metadata["id"], "version": metadata["version"]},
            "provider": provider.name,
            "artifacts": {name: _sha256(temporary / name) for name in _ARTIFACT_NAMES},
        }
        validate_document(manifest, "manifest")
        _write_bytes(temporary / "manifest.json", _json_bytes(manifest))
        os.replace(temporary, final_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return final_directory


def verify_bundle(run_directory: Path) -> None:
    """Verify manifest structure, artifact set, safe paths, and content hashes."""

    if run_directory.is_symlink():
        raise ValidationError("review bundle directory must not be a symbolic link")
    if not run_directory.is_dir():
        raise ValidationError(f"review bundle does not exist: {run_directory}")
    manifest_path = run_directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValidationError("review bundle is missing a regular manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read manifest.json: {exc}") from exc
    validate_document(manifest, "manifest")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict):
        raise ValidationError("manifest artifacts must be an object")
    for name in artifacts:
        artifact_path = Path(name)
        if artifact_path.is_absolute() or artifact_path.name != name or name in {".", ".."}:
            raise ValidationError(f"unsafe artifact path in manifest: {name}")

    allowed = {"manifest.json", *artifacts}
    present = {path.name for path in run_directory.iterdir()}
    unexpected = sorted(present - allowed)
    if unexpected:
        raise ValidationError(f"unexpected artifact in review bundle: {unexpected[0]}")
    missing = sorted(allowed - present)
    if missing:
        raise ValidationError(f"missing artifact in review bundle: {missing[0]}")

    for name, expected_hash in artifacts.items():
        path = run_directory / name
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"artifact is not a regular file: {name}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValidationError(f"hash mismatch for {name}")
