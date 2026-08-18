import json

import pytest

from ai_governance_review.errors import ValidationError
from ai_governance_review.loader import load_document


def test_loads_json_and_yaml_documents(tmp_path):
    expected = {"request": {"id": "example-1"}, "enabled": True}
    json_path = tmp_path / "document.json"
    yaml_path = tmp_path / "document.yaml"
    json_path.write_text(json.dumps(expected), encoding="utf-8")
    yaml_path.write_text("request:\n  id: example-1\nenabled: true\n", encoding="utf-8")

    assert load_document(json_path) == expected
    assert load_document(yaml_path) == expected


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path / "intake.yaml"
    path.write_text("request:\n  id: one\n  id: two\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="duplicate key 'id'"):
        load_document(path)


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "intake.json"
    path.write_text('{"request": {"id": "one", "id": "two"}}', encoding="utf-8")

    with pytest.raises(ValidationError, match="duplicate key 'id'"):
        load_document(path)


def test_unsupported_file_type_is_rejected(tmp_path):
    path = tmp_path / "intake.toml"
    path.write_text("title = 'demo'\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="supported formats are .json, .yaml, and .yml"):
        load_document(path)


def test_document_root_must_be_an_object(tmp_path):
    path = tmp_path / "intake.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="top level must be an object"):
        load_document(path)
