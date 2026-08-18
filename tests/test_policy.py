from copy import deepcopy

import pytest
from test_validation import VALID_INTAKE

from ai_governance_review.errors import ValidationError
from ai_governance_review.policy import evaluate_condition, evaluate_policy, get_path
from ai_governance_review.validation import validate_document

POLICY = {
    "policy": {
        "id": "example-ai-use-policy",
        "version": "0.1.0",
        "effective_date": "2026-01-01",
        "owner": "Example Governance Committee",
        "status": "demonstration",
        "jurisdiction_scope": ["example-only"],
    },
    "rules": [],
}


def test_get_path_distinguishes_missing_from_false():
    assert get_path(VALID_INTAKE, "data.personal_data") == (True, False)
    assert get_path(VALID_INTAKE, "data.not_recorded") == (False, None)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"equals": {"path": "data.personal_data", "value": False}}, True),
        ({"not_equals": {"path": "system.hosting", "value": "third_party"}}, True),
        ({"contains": {"path": "data.categories", "value": "internal documents"}}, True),
        ({"exists": {"path": "system.provider"}}, True),
        ({"exists": {"path": "system.not_recorded"}}, False),
        (
            {
                "in": {
                    "path": "system.autonomy",
                    "value": ["human_in_the_loop", "human_on_the_loop"],
                }
            },
            True,
        ),
        (
            {
                "all": [
                    {"exists": {"path": "system.provider"}},
                    {
                        "contains": {
                            "path": "data.categories",
                            "value": "internal documents",
                        }
                    },
                ]
            },
            True,
        ),
        (
            {
                "any": [
                    {"equals": {"path": "data.personal_data", "value": True}},
                    {"equals": {"path": "data.sensitive_data", "value": False}},
                ]
            },
            True,
        ),
        ({"not": {"equals": {"path": "outputs.external_distribution", "value": True}}}, True),
    ],
)
def test_condition_operators(condition, expected):
    assert evaluate_condition(condition, VALID_INTAKE) is expected


def test_unknown_operator_is_rejected_without_execution():
    condition = {"__import__": {"path": "os", "value": "system"}}

    with pytest.raises(ValidationError, match="unsupported condition operator '__import__'"):
        evaluate_condition(condition, VALID_INTAKE)


def test_triggered_rule_with_missing_evidence_needs_information():
    policy = deepcopy(POLICY)
    policy["rules"] = [
        {
            "id": "EXAMPLE-DATA-1",
            "title": "Document training data",
            "rationale": "Reviewers need the declared source of training data.",
            "severity": "block",
            "condition": {"equals": {"path": "data.training_or_fine_tuning", "value": True}},
            "finding": "Training is proposed.",
            "required_evidence": ["training-data-record"],
            "question": "Provide a training-data record.",
        }
    ]
    intake = deepcopy(VALID_INTAKE)
    intake["data"]["training_or_fine_tuning"] = True

    findings, questions = evaluate_policy(intake, policy, [])

    assert findings[0]["status"] == "needs_information"
    assert findings[0]["missing_evidence"] == ["training-data-record"]
    assert questions == [
        {
            "id": "question-EXAMPLE-DATA-1",
            "path": "evidence",
            "question": "Provide a training-data record.",
        }
    ]


def test_supplied_evidence_allows_triggered_finding():
    policy = deepcopy(POLICY)
    policy["rules"] = [
        {
            "id": "EXAMPLE-DATA-1",
            "title": "Document training data",
            "rationale": "Reviewers need the declared source of training data.",
            "severity": "review",
            "condition": {"equals": {"path": "data.training_or_fine_tuning", "value": True}},
            "finding": "Training is proposed.",
            "required_evidence": ["training-data-record"],
        }
    ]
    intake = deepcopy(VALID_INTAKE)
    intake["data"]["training_or_fine_tuning"] = True
    intake["evidence"] = [
        {"id": "training-data-record", "type": "record", "title": "Synthetic record"}
    ]

    findings, questions = evaluate_policy(intake, policy, [])

    assert findings[0]["status"] == "triggered"
    assert findings[0]["missing_evidence"] == []
    assert questions == []


def test_triggered_rule_question_remains_open_without_evidence_requirement():
    policy = deepcopy(POLICY)
    policy["rules"] = [
        {
            "id": "EXAMPLE-CONTROL-1",
            "title": "Describe personal-data controls",
            "rationale": "Reviewers need the proposed controls.",
            "severity": "review",
            "condition": {"equals": {"path": "data.personal_data", "value": True}},
            "finding": "Personal data is proposed.",
            "question": "Describe the access and retention controls.",
        }
    ]
    intake = deepcopy(VALID_INTAKE)
    intake["data"]["personal_data"] = True

    _, questions = evaluate_policy(intake, policy, [])

    assert questions == [
        {
            "id": "question-EXAMPLE-CONTROL-1",
            "path": "data.personal_data",
            "question": "Describe the access and retention controls.",
        }
    ]


def test_findings_are_sorted_and_include_observed_facts():
    policy = deepcopy(POLICY)
    policy["rules"] = [
        {
            "id": rule_id,
            "title": rule_id,
            "rationale": "Example rationale.",
            "severity": "info",
            "condition": condition,
            "finding": "Example finding.",
        }
        for rule_id, condition in [
            ("Z-LAST", {"exists": {"path": "system.provider"}}),
            ("A-FIRST", {"equals": {"path": "data.personal_data", "value": True}}),
        ]
    ]

    findings, _ = evaluate_policy(VALID_INTAKE, policy, [])

    assert [finding["rule_id"] for finding in findings] == ["A-FIRST", "Z-LAST"]
    assert findings[0]["facts"] == [{"path": "data.personal_data", "present": True, "value": False}]


def test_example_policy_document_is_schema_valid(example_policy):
    validate_document(example_policy, "policy")


@pytest.mark.parametrize(
    ("section", "field", "value", "rule_id", "evidence_id", "severity"),
    [
        (
            "system",
            "autonomy",
            "autonomous",
            "EXAMPLE-SYSTEM-1",
            "oversight-plan",
            "block",
        ),
        (
            "system",
            "hosting",
            "third_party",
            "EXAMPLE-VENDOR-1",
            "provider-assessment",
            "review",
        ),
        (
            "data",
            "sensitive_data",
            True,
            "EXAMPLE-DATA-3",
            "sensitive-data-assessment",
            "review",
        ),
        (
            "data",
            "cross_border_transfers",
            True,
            "EXAMPLE-DATA-4",
            "transfer-assessment",
            "review",
        ),
    ],
)
def test_example_policy_routes_additional_common_review_dimensions(
    example_policy, section, field, value, rule_id, evidence_id, severity
):
    intake = deepcopy(VALID_INTAKE)
    intake[section][field] = value

    findings, questions = evaluate_policy(intake, example_policy, [])
    finding = next(item for item in findings if item["rule_id"] == rule_id)

    assert finding["status"] == "needs_information"
    assert finding["severity"] == severity
    assert finding["missing_evidence"] == [evidence_id]
    assert questions == [
        {
            "id": f"question-{rule_id}",
            "path": "evidence",
            "question": finding["question"],
        }
    ]
