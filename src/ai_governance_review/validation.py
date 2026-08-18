"""Schema and semantic validation for review documents."""

import json
from importlib.resources import files

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError:  # Portable skill hosts may intentionally have no site packages.
    Draft202012Validator = None  # type: ignore[assignment,misc]
    FormatChecker = None  # type: ignore[assignment,misc]

from .errors import ValidationError
from .portable_schema import iter_errors as iter_portable_errors

_SCHEMA_NAMES = {"intake", "policy", "findings", "decision", "manifest"}
_MATERIAL_PATHS = (
    "purpose.deployment_scope",
    "system.autonomy",
    "system.human_oversight",
    "data.personal_data",
    "data.sensitive_data",
    "data.training_or_fine_tuning",
    "data.cross_border_transfers",
    "outputs.external_distribution",
)


def _read_schema(schema_name: str) -> dict[str, object]:
    if schema_name not in _SCHEMA_NAMES:
        raise ValidationError(f"unknown schema '{schema_name}'")
    resource = files("ai_governance_review").joinpath("schemas", f"{schema_name}.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_document(document: object, schema_name: str) -> None:
    """Validate a document against a bundled canonical schema."""

    schema = _read_schema(schema_name)
    if Draft202012Validator is None or FormatChecker is None:
        errors = iter_portable_errors(document, schema)
    else:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = list(validator.iter_errors(document))
    errors = sorted(errors, key=lambda error: list(error.absolute_path))
    if not errors:
        return

    details = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        details.append(f"{path}: {error.message}")
    raise ValidationError(f"{schema_name} validation failed", details)


def _get_path(document: dict[str, object], path: str) -> tuple[bool, object | None]:
    current: object = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def validate_intake_semantics(intake: dict[str, object]) -> list[dict[str, str]]:
    """Return questions for unknown or internally contradictory material facts."""

    questions: list[dict[str, str]] = []
    present, autonomy = _get_path(intake, "system.autonomy")
    oversight_present, oversight = _get_path(intake, "system.human_oversight")
    if present and oversight_present and autonomy == "human_in_the_loop" and oversight is False:
        questions.append(
            {
                "id": "semantic-system-human-oversight",
                "path": "system.human_oversight",
                "question": (
                    "The system is described as human-in-the-loop but human oversight is false. "
                    "Which description is correct?"
                ),
            }
        )

    for path in _MATERIAL_PATHS:
        value_present, value = _get_path(intake, path)
        if value_present and value == "unknown":
            questions.append(
                {
                    "id": f"unknown-{path.replace('.', '-')}",
                    "path": path,
                    "question": f"Provide a confirmed value for {path}.",
                }
            )
    return questions
