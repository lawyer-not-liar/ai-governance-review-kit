#!/usr/bin/env python3
"""Run deterministic skill analysis with a machine-readable boundary."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
import tomllib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_POLICY = SKILL_ROOT / "references/generic-policy.json"
ARGUMENT_ERROR_MESSAGE = "invalid runner arguments; use analyze --intake PATH or self-check"
HELP_MESSAGE = "commands: analyze --intake PATH [--policy PATH]; self-check"
VALIDATION_ERROR_MESSAGE = "intake or policy could not be read or failed validation"
EXPECTED_PROJECT_NAME = "ai-governance-review-kit"
EXPECTED_PACKAGE_NAME = "ai_governance_review"


class _CommandValidationError(Exception):
    """Raised when command arguments do not satisfy the runner interface."""


class _HelpRequested(Exception):
    """Raised to route help through the JSON success envelope."""


class _EngineUnavailableError(Exception):
    """Raised when the engine resolves outside an approved distribution root."""


class _JsonHelpAction(argparse.Action):
    def __init__(
        self,
        option_strings: list[str],
        dest: str = argparse.SUPPRESS,
        default: object = argparse.SUPPRESS,
        help: str | None = None,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            default=default,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        raise _HelpRequested


class _JsonArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--help", action=_JsonHelpAction)

    def error(self, message: str) -> None:
        raise _CommandValidationError


def _source_checkout_path() -> Path | None:
    repository_root = SKILL_ROOT.parents[1]
    if repository_root / "skills" / "ai-governance-review" != SKILL_ROOT:
        return None

    project_file = repository_root / "pyproject.toml"
    package_root = repository_root / "src" / EXPECTED_PACKAGE_NAME
    package_init = package_root / "__init__.py"
    required_files = (
        project_file,
        package_init,
        package_root / "analysis.py",
        package_root / "schemas/intake.schema.json",
        repository_root / "policies/example/policy.yaml",
    )
    if any(path.is_symlink() or not path.is_file() for path in required_files):
        return None

    try:
        with project_file.open("rb") as stream:
            project = tomllib.load(stream).get("project")
        module = ast.parse(package_init.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(project, dict) or project.get("name") != EXPECTED_PROJECT_NAME:
        return None

    package_versions = [
        statement.value.value
        for statement in module.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        )
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    ]
    if len(package_versions) != 1 or project.get("version") != package_versions[0]:
        return None
    return package_root.parent


def _configure_import_paths() -> tuple[Path, ...]:
    paths = [SCRIPT_DIR / "runtime"]
    engine_roots = [SCRIPT_DIR / "runtime" / EXPECTED_PACKAGE_NAME]
    repository_src = _source_checkout_path()
    if repository_src is not None:
        paths.append(repository_src)
        engine_roots.append(repository_src / EXPECTED_PACKAGE_NAME)
    sys.path[:0] = [str(path) for path in paths]
    return tuple(engine_roots)


def _require_approved_engine_origin(engine_roots: tuple[Path, ...]) -> None:
    specification = importlib.util.find_spec(EXPECTED_PACKAGE_NAME)
    if specification is None or specification.origin is None:
        raise _EngineUnavailableError
    origin = Path(specification.origin).resolve()
    if not any(origin.is_relative_to(root.resolve()) for root in engine_roots):
        raise _EngineUnavailableError


def analyze(intake_path: Path, policy_path: Path) -> dict[str, object]:
    from ai_governance_review.analysis import analyze_review
    from ai_governance_review.loader import load_document

    return analyze_review(load_document(intake_path), load_document(policy_path))


def _self_check() -> dict[str, object]:
    from ai_governance_review.loader import load_document
    from ai_governance_review.validation import validate_document

    validate_document(load_document(DEFAULT_POLICY), "policy")
    return {"status": "available"}


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("--intake", type=Path, required=True)
    analyze_parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    commands.add_parser("self-check")
    return parser


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _runtime_error(error: ModuleNotFoundError) -> bool:
    return error.name in {"jsonschema", "yaml"}


def main(argv: list[str] | None = None) -> int:
    try:
        engine_roots = _configure_import_paths()
        _require_approved_engine_origin(engine_roots)
        arguments = _parser().parse_args(argv)
        if arguments.command == "analyze":
            result = analyze(arguments.intake, arguments.policy)
        else:
            result = _self_check()
    except _HelpRequested:
        _emit({"ok": True, "result": {"message": HELP_MESSAGE}})
        return 0
    except _CommandValidationError:
        _emit(
            {
                "ok": False,
                "error": {"kind": "validation", "message": ARGUMENT_ERROR_MESSAGE},
            }
        )
        return 2
    except _EngineUnavailableError:
        _emit(
            {
                "ok": False,
                "error": {
                    "kind": "runtime_unavailable",
                    "message": "required skill runtime dependencies are unavailable",
                },
            }
        )
        return 3
    except ModuleNotFoundError as exc:
        if _runtime_error(exc):
            _emit(
                {
                    "ok": False,
                    "error": {
                        "kind": "runtime_unavailable",
                        "message": "required skill runtime dependencies are unavailable",
                    },
                }
            )
            return 3
        _emit(
            {
                "ok": False,
                "error": {"kind": "internal", "message": "unexpected runner failure"},
            }
        )
        return 2
    except Exception as exc:
        from ai_governance_review.errors import ValidationError

        if isinstance(exc, ValidationError):
            _emit(
                {
                    "ok": False,
                    "error": {"kind": "validation", "message": VALIDATION_ERROR_MESSAGE},
                }
            )
        else:
            _emit(
                {
                    "ok": False,
                    "error": {"kind": "internal", "message": "unexpected runner failure"},
                }
            )
        return 2

    _emit({"ok": True, "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
