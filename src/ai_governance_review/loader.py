"""Safe loading for user-controlled YAML and JSON documents."""

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError


def _construct_unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValidationError(f"duplicate key '{key}' in JSON document")
        mapping[key] = value
    return mapping


def _load_yaml(text: str, name: str) -> object:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ValidationError("YAML input requires the optional PyYAML dependency") from exc

    class _UniqueKeyLoader(yaml.SafeLoader):
        """Safe YAML loader that rejects ambiguous duplicate mapping keys."""

    def construct_unique_mapping(
        loader: _UniqueKeyLoader,
        node: yaml.nodes.MappingNode,
        deep: bool = False,
    ) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValidationError(f"duplicate key '{key}' in YAML document")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ValidationError(f"could not parse {name}: {exc}") from exc


def load_document(path: Path) -> dict[str, object]:
    """Load one YAML or JSON object from disk without executing content."""

    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"could not read {path}: {exc}") from exc

    try:
        if suffix == ".json":
            document: Any = json.loads(text, object_pairs_hook=_construct_unique_json)
        elif suffix in {".yaml", ".yml"}:
            document = _load_yaml(text, path.name)
        else:
            raise ValidationError(
                f"unsupported file type '{suffix}'; supported formats are .json, .yaml, and .yml"
            )
    except ValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise ValidationError(f"could not parse {path.name}: {exc}") from exc

    if not isinstance(document, dict):
        raise ValidationError(f"{path.name} top level must be an object")
    return document
