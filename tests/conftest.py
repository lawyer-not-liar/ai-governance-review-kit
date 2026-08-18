from pathlib import Path

import pytest

from ai_governance_review.loader import load_document

PROJECT_ROOT = Path(__file__).parents[1]


@pytest.fixture
def example_policy():
    return load_document(PROJECT_ROOT / "policies" / "example" / "policy.yaml")
