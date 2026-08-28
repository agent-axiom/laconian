import re
from collections.abc import Hashable, Mapping
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
    SequenceStartEvent,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import AliasToken, AnchorToken

from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
)

_MERGE_TAG = "tag:yaml.org,2002:merge"
_INT_TAG = "tag:yaml.org,2002:int"
_FLOAT_TAG = "tag:yaml.org,2002:float"
_NON_SEXAGESIMAL_INT = re.compile(
    r"""^(?:
        [-+]?0b[0-1_]+
        |[-+]?0[0-7_]+
        |[-+]?(?:0|[1-9][0-9_]*)
        |[-+]?0x[0-9a-fA-F_]+
    )$""",
    re.VERBOSE,
)
_NON_SEXAGESIMAL_FLOAT = re.compile(
    r"""^(?:
        [-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?
        |\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?
        |[-+]?\.(?:inf|Inf|INF)
        |\.(?:nan|NaN|NAN)
    )$""",
    re.VERBOSE,
)


class StrictYamlError(ValueError):
    """A strict YAML rejection whose message never contains source content."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(slots=True)
class _CollectionFrame:
    kind: str
    limit: int | None
    code: str
    child_count: int = 0
    pending_scalar_key: str | None = None

    @property
    def next_child_is_mapping_key(self) -> bool:
        return self.kind == "mapping" and self.child_count % 2 == 0

    def add_child(self) -> None:
        self.child_count += 1
        if self.limit is None:
            return
        count = self.child_count if self.kind == "sequence" else (self.child_count + 1) // 2
        check_collection_count(count, limit=self.limit, code=self.code)


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


class _StrictUniqueKeySafeLoader(_UniqueKeySafeLoader):
    """Case-source loader without YAML 1.1 sexagesimal number resolution."""

    def construct_yaml_int(self, node: ScalarNode) -> int:
        if ":" in self.construct_scalar(node):
            raise ConstructorError(
                "while constructing an integer",
                node.start_mark,
                "sexagesimal integers are forbidden",
                node.start_mark,
            )
        return super().construct_yaml_int(node)

    def construct_yaml_float(self, node: ScalarNode) -> float:
        if ":" in self.construct_scalar(node):
            raise ConstructorError(
                "while constructing a float",
                node.start_mark,
                "sexagesimal floats are forbidden",
                node.start_mark,
            )
        return super().construct_yaml_float(node)


def _strict_scalar_resolver(tag: str, resolver: re.Pattern[str]) -> re.Pattern[str]:
    if tag == _INT_TAG:
        return _NON_SEXAGESIMAL_INT
    if tag == _FLOAT_TAG:
        return _NON_SEXAGESIMAL_FLOAT
    return resolver


_StrictUniqueKeySafeLoader.yaml_implicit_resolvers = {
    initial: [(tag, _strict_scalar_resolver(tag, resolver)) for tag, resolver in resolvers]
    for initial, resolvers in _UniqueKeySafeLoader.yaml_implicit_resolvers.items()
}
_StrictUniqueKeySafeLoader.yaml_constructors = dict(_UniqueKeySafeLoader.yaml_constructors)
_StrictUniqueKeySafeLoader.add_constructor(
    _INT_TAG,
    _StrictUniqueKeySafeLoader.construct_yaml_int,
)
_StrictUniqueKeySafeLoader.add_constructor(
    _FLOAT_TAG,
    _StrictUniqueKeySafeLoader.construct_yaml_float,
)


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


def _is_explicit_sexagesimal_number(event: ScalarEvent) -> bool:
    return event.tag in {_INT_TAG, _FLOAT_TAG} and ":" in event.value


def _preflight_yaml_events(
    text: str,
    *,
    depth_limit: int,
    collection_limit: int | None,
    collection_code: str,
    node_limit: int | None,
    node_code: str,
    top_level_sequence_limits: Mapping[str, tuple[int, str]] | None,
) -> None:
    check_collection_count(0, limit=depth_limit, code="nesting_depth_limit")
    if collection_limit is not None:
        check_collection_count(0, limit=collection_limit, code=collection_code)
    if node_limit is None:
        node_limit = (
            collection_limit if collection_limit is not None else RESOURCE_LIMITS_V1.case_records
        ) * depth_limit
    if node_limit is not None:
        check_collection_count(0, limit=node_limit, code=node_code)
    if top_level_sequence_limits is not None:
        for limit, code in top_level_sequence_limits.values():
            check_collection_count(0, limit=limit, code=code)
    stack: list[_CollectionFrame] = []
    node_count = 0

    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, CollectionEndEvent):
                stack.pop()
                continue
            if not isinstance(event, NodeEvent):
                continue

            node_count += 1
            if node_limit is not None:
                check_collection_count(node_count, limit=node_limit, code=node_code)

            parent = stack[-1] if stack else None
            is_mapping_key = parent is not None and parent.next_child_is_mapping_key
            new_limit = collection_limit
            new_code = collection_code
            if isinstance(event, AliasEvent):
                raise StrictYamlError("yaml_alias", "YAML aliases are forbidden")
            if isinstance(event, ScalarEvent) and _is_explicit_sexagesimal_number(event):
                raise StrictYamlError(
                    "yaml_sexagesimal_number",
                    "YAML sexagesimal numbers are forbidden",
                )
            if (
                isinstance(event, ScalarEvent)
                and is_mapping_key
                and (event.tag == _MERGE_TAG or event.value == "<<")
            ):
                raise StrictYamlError("yaml_merge_key", "YAML merge keys are forbidden")
            if isinstance(event, ScalarEvent) and is_mapping_key and parent is not None:
                parent.pending_scalar_key = event.value
            if (
                isinstance(event, SequenceStartEvent)
                and parent is not None
                and len(stack) == 1
                and not is_mapping_key
                and parent.pending_scalar_key is not None
                and top_level_sequence_limits is not None
                and parent.pending_scalar_key in top_level_sequence_limits
            ):
                specific_limit, specific_code = top_level_sequence_limits[parent.pending_scalar_key]
                if collection_limit is None or specific_limit < collection_limit:
                    new_limit = specific_limit
                    new_code = specific_code
            if parent is not None:
                parent.add_child()
                if parent.kind == "mapping" and not is_mapping_key:
                    parent.pending_scalar_key = None

            if isinstance(event, CollectionStartEvent):
                depth = len(stack) + 1
                check_collection_count(
                    depth,
                    limit=depth_limit,
                    code="nesting_depth_limit",
                )
                kind = "mapping" if isinstance(event, MappingStartEvent) else "sequence"
                stack.append(_CollectionFrame(kind=kind, limit=new_limit, code=new_code))
    except StrictYamlError:
        raise
    except YAMLError:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None


def _preflight_mapping_keys(text: str) -> None:
    try:
        root = yaml.compose(text, Loader=_StrictUniqueKeySafeLoader)
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
        loaded: object = yaml.load(text, Loader=_StrictUniqueKeySafeLoader)
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
    node_limit: int | None = None,
    node_code: str = "yaml_nodes_limit",
    top_level_sequence_limits: Mapping[str, tuple[int, str]] | None = None,
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
        node_limit=node_limit,
        node_code=node_code,
        top_level_sequence_limits=top_level_sequence_limits,
    )
    _preflight_mapping_keys(text)
    return _construct_strict_yaml(text)
