"""Constrained, deterministic evaluation of organization-owned policy rules."""

from collections.abc import Iterable

from .errors import ValidationError

_LEAF_OPERATORS = {"equals", "not_equals", "contains", "exists", "in"}
_GROUP_OPERATORS = {"all", "any", "not"}
_OPERATORS = _LEAF_OPERATORS | _GROUP_OPERATORS


def get_path(document: dict[str, object], path: str) -> tuple[bool, object | None]:
    """Return whether a dotted path exists and its value without conflating false with missing."""

    current: object = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def evaluate_condition(condition: dict[str, object], facts: dict[str, object]) -> bool:
    """Evaluate one condition using only the closed operator vocabulary."""

    if len(condition) != 1:
        raise ValidationError("a policy condition must contain exactly one operator")
    operator, operand = next(iter(condition.items()))
    if operator not in _OPERATORS:
        raise ValidationError(f"unsupported condition operator '{operator}'")

    if operator == "all":
        return all(evaluate_condition(child, facts) for child in _condition_list(operand, "all"))
    if operator == "any":
        return any(evaluate_condition(child, facts) for child in _condition_list(operand, "any"))
    if operator == "not":
        if not isinstance(operand, dict):
            raise ValidationError("the 'not' operator requires one nested condition")
        return not evaluate_condition(operand, facts)

    if not isinstance(operand, dict) or not isinstance(operand.get("path"), str):
        raise ValidationError(f"the '{operator}' operator requires a string path")
    present, observed = get_path(facts, operand["path"])
    if operator == "exists":
        return present
    if "value" not in operand:
        raise ValidationError(f"the '{operator}' operator requires a value")
    expected = operand["value"]
    if not present:
        return False
    if operator == "equals":
        return observed == expected
    if operator == "not_equals":
        return observed != expected
    if operator == "contains":
        if isinstance(observed, (list, tuple, set, str, dict)):
            return expected in observed
        return False
    if operator == "in":
        if not isinstance(expected, list):
            raise ValidationError("the 'in' operator value must be a list")
        return observed in expected
    raise AssertionError("operator dispatch is exhaustive")


def _condition_list(operand: object, operator: str) -> list[dict[str, object]]:
    if (
        not isinstance(operand, list)
        or not operand
        or not all(isinstance(item, dict) for item in operand)
    ):
        raise ValidationError(f"the '{operator}' operator requires a non-empty condition list")
    return operand


def _paths_in_condition(condition: dict[str, object]) -> list[str]:
    operator, operand = next(iter(condition.items()))
    if operator in _LEAF_OPERATORS:
        if isinstance(operand, dict) and isinstance(operand.get("path"), str):
            return [operand["path"]]
        return []
    if operator in {"all", "any"} and isinstance(operand, list):
        return sorted(
            {
                path
                for child in operand
                if isinstance(child, dict)
                for path in _paths_in_condition(child)
            }
        )
    if operator == "not" and isinstance(operand, dict):
        return _paths_in_condition(operand)
    return []


def _evidence_ids(intake: dict[str, object]) -> set[str]:
    evidence = intake.get("evidence", [])
    if not isinstance(evidence, list):
        return set()
    return {
        item["id"]
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return sorted({item for item in value if isinstance(item, str)})


def evaluate_policy(
    intake: dict[str, object],
    policy: dict[str, object],
    semantic_questions: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Evaluate policy rules and return stable findings plus open questions."""

    metadata = policy.get("policy")
    rules = policy.get("rules")
    if not isinstance(metadata, dict) or not isinstance(rules, list):
        raise ValidationError("policy document must contain policy metadata and rules")
    supplied_evidence = _evidence_ids(intake)
    findings: list[dict[str, object]] = []
    questions: list[dict[str, object]] = [dict(question) for question in semantic_questions]

    rules_by_id = sorted(
        rules,
        key=lambda item: item.get("id", "") if isinstance(item, dict) else "",
    )
    for rule in rules_by_id:
        if not isinstance(rule, dict) or not isinstance(rule.get("condition"), dict):
            raise ValidationError("each policy rule must be an object with a condition")
        rule_id = str(rule.get("id", ""))
        matched = evaluate_condition(rule["condition"], intake)
        required_evidence = _as_string_list(rule.get("required_evidence", []))
        missing_evidence = sorted(set(required_evidence) - supplied_evidence) if matched else []
        status = "not_applicable"
        if matched:
            status = "needs_information" if missing_evidence else "triggered"
        fact_paths = _paths_in_condition(rule["condition"])
        finding = {
            "id": f"finding-{rule_id}",
            "rule_id": rule_id,
            "title": str(rule.get("title", "")),
            "severity": str(rule.get("severity", "review")),
            "status": status,
            "policy": {
                "id": str(metadata.get("id", "")),
                "version": str(metadata.get("version", "")),
            },
            "facts": [
                {"path": path, "present": present, "value": value}
                for path in fact_paths
                for present, value in [get_path(intake, path)]
            ],
            "required_evidence": required_evidence,
            "missing_evidence": missing_evidence,
            "explanation": str(rule.get("finding", "")),
        }
        if isinstance(rule.get("question"), str):
            finding["question"] = rule["question"]
        findings.append(finding)

        if status == "needs_information":
            questions.append(
                {
                    "id": f"question-{rule_id}",
                    "path": "evidence",
                    "question": str(
                        rule.get(
                            "question",
                            f"Provide evidence records: {', '.join(missing_evidence)}.",
                        )
                    ),
                }
            )
        elif (
            status == "triggered"
            and not required_evidence
            and isinstance(rule.get("question"), str)
        ):
            questions.append(
                {
                    "id": f"question-{rule_id}",
                    "path": fact_paths[0] if len(fact_paths) == 1 else "policy",
                    "question": rule["question"],
                }
            )

    deduplicated = {str(question["id"]): question for question in questions}
    return findings, [deduplicated[key] for key in sorted(deduplicated)]
