from collections.abc import Hashable
from dataclasses import dataclass

import yaml
from yaml.constructor import ConstructorError
from yaml.error import YAMLError
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    MappingStartEvent,
    NodeEvent,
    ScalarEvent,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import AliasToken, AnchorToken

from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
)

_MERGE_TAG = "tag:yaml.org,2002:merge"


class StrictYamlError(ValueError):
    """A strict YAML rejection whose message never contains source content."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(slots=True)
class _CollectionFrame:
    kind: str
    child_count: int = 0

    @property
    def next_child_is_mapping_key(self) -> bool:
        return self.kind == "mapping" and self.child_count % 2 == 0

    def add_child(self, *, collection_limit: int | None, collection_code: str) -> None:
        self.child_count += 1
        if collection_limit is None:
            return
        count = self.child_count if self.kind == "sequence" else (self.child_count + 1) // 2
        check_collection_count(count, limit=collection_limit, code=collection_code)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        mapping: dict[object, object] = {}

        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found forbidden YAML merge key '<<'",
                    key_node.start_mark,
                )

            key: object = self.construct_object(key_node, deep=deep)
            if key == "<<":
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found forbidden YAML merge key '<<'",
                    key_node.start_mark,
                )
            if not isinstance(key, Hashable):
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable key",
                    key_node.start_mark,
                )
            if key in mapping:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate mapping key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)

        return mapping


def safe_load_unique(text: str) -> object:
    loaded: object = yaml.load(text, Loader=_UniqueKeySafeLoader)
    return loaded


def _reject_reference_tokens(text: str) -> None:
    try:
        for token in yaml.scan(text, Loader=yaml.SafeLoader):
            if isinstance(token, AnchorToken):
                raise StrictYamlError("yaml_anchor", "YAML anchors are forbidden")
            if isinstance(token, AliasToken):
                raise StrictYamlError("yaml_alias", "YAML aliases are forbidden")
    except YAMLError:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None


def _preflight_yaml_events(
    text: str,
    *,
    depth_limit: int,
    collection_limit: int | None,
    collection_code: str,
) -> None:
    check_collection_count(0, limit=depth_limit, code="nesting_depth_limit")
    if collection_limit is not None:
        check_collection_count(0, limit=collection_limit, code=collection_code)
    stack: list[_CollectionFrame] = []

    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, CollectionEndEvent):
                stack.pop()
                continue
            if not isinstance(event, NodeEvent):
                continue

            parent = stack[-1] if stack else None
            if isinstance(event, AliasEvent):
                raise StrictYamlError("yaml_alias", "YAML aliases are forbidden")
            if (
                isinstance(event, ScalarEvent)
                and parent is not None
                and parent.next_child_is_mapping_key
                and (event.tag == _MERGE_TAG or event.value == "<<")
            ):
                raise StrictYamlError("yaml_merge_key", "YAML merge keys are forbidden")
            if parent is not None:
                parent.add_child(
                    collection_limit=collection_limit,
                    collection_code=collection_code,
                )

            if isinstance(event, CollectionStartEvent):
                depth = len(stack) + 1
                check_collection_count(
                    depth,
                    limit=depth_limit,
                    code="nesting_depth_limit",
                )
                kind = "mapping" if isinstance(event, MappingStartEvent) else "sequence"
                stack.append(_CollectionFrame(kind=kind))
    except StrictYamlError:
        raise
    except YAMLError:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None


def _preflight_mapping_keys(text: str) -> None:
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        pending: list[Node] = [] if root is None else [root]
        while pending:
            node = pending.pop()
            if isinstance(node, SequenceNode):
                pending.extend(node.value)
                continue
            if not isinstance(node, MappingNode):
                continue
            seen: set[tuple[str, str]] = set()
            for key_node, value_node in node.value:
                if not isinstance(key_node, ScalarNode):
                    raise StrictYamlError("invalid_yaml", "invalid YAML")
                if key_node.tag == _MERGE_TAG or key_node.value == "<<":
                    raise StrictYamlError("yaml_merge_key", "YAML merge keys are forbidden")
                key = (key_node.tag, key_node.value)
                if key in seen:
                    raise StrictYamlError(
                        "duplicate_mapping_key",
                        "duplicate mapping key",
                    )
                seen.add(key)
                pending.append(value_node)
    except StrictYamlError:
        raise
    except Exception:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None


def _construct_strict_yaml(text: str) -> object:
    try:
        loaded: object = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except ConstructorError as exc:
        problem = exc.problem or ""
        if "duplicate mapping key" in problem:
            raise StrictYamlError(
                "duplicate_mapping_key",
                "duplicate mapping key",
            ) from None
        if "merge key" in problem:
            raise StrictYamlError("yaml_merge_key", "YAML merge keys are forbidden") from None
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None
    except Exception:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None
    return loaded


def safe_load_unique_bytes(
    data: bytes,
    *,
    byte_limit: int = RESOURCE_LIMITS_V1.case_file_bytes,
    byte_code: str = "yaml_bytes_limit",
    depth_limit: int = RESOURCE_LIMITS_V1.nesting_depth,
    collection_limit: int | None = None,
    collection_code: str = "collection_limit",
) -> object:
    """Decode and load one strict, preflight-bounded YAML byte buffer."""

    if type(data) is not bytes:
        raise TypeError("strict YAML input must be bytes")
    check_collection_count(len(data), limit=byte_limit, code=byte_code)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ResourceLimitError("invalid_utf8") from None
    _reject_reference_tokens(text)
    _preflight_yaml_events(
        text,
        depth_limit=depth_limit,
        collection_limit=collection_limit,
        collection_code=collection_code,
    )
    _preflight_mapping_keys(text)
    return _construct_strict_yaml(text)
