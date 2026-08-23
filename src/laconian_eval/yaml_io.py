from collections.abc import Hashable

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

_MERGE_TAG = "tag:yaml.org,2002:merge"


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
