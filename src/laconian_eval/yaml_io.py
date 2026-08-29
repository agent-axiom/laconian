from __future__ import annotations

import re
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.error import Mark, YAMLError
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    MappingStartEvent,
    NodeEvent,
    ScalarEvent,
    SequenceStartEvent,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.scanner import ScannerError
from yaml.tokens import AliasToken, AnchorToken, ScalarToken, TagToken

from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
)

_MERGE_TAG = "tag:yaml.org,2002:merge"
_INT_TAG = "tag:yaml.org,2002:int"
_FLOAT_TAG = "tag:yaml.org,2002:float"


class _SupportsYamlRead(Protocol):
    def read(self, size: int = -1) -> str | bytes: ...


_YamlStream: TypeAlias = str | bytes | _SupportsYamlRead
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


class _DiscardedYamlScalar(str):
    """Marker used when a scalar is scanned without retaining its value."""


_DISCARDED_YAML_SCALAR = _DiscardedYamlScalar("discarded")


@dataclass(slots=True)
class _YamlUtf8Budget:
    hard: bool = False
    used: int = 0
    discarded: bool = False

    @property
    def remaining(self) -> int:
        if self.discarded:
            return 0
        return RESOURCE_LIMITS_V1.bounded_string_bytes - self.used

    def discard(self, chunks: list[str]) -> None:
        chunks.clear()
        self.discarded = True

    def append(self, chunks: list[str], value: str) -> None:
        if self.discarded:
            return
        try:
            size = len(value.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            raise ResourceLimitError("invalid_utf8") from None
        if self.used + size > RESOURCE_LIMITS_V1.bounded_string_bytes:
            if self.hard:
                raise ResourceLimitError("bounded_string_limit")
            self.discard(chunks)
            return
        self.used += size
        chunks.append(value)

    def token_value(self, chunks: list[str]) -> str:
        if self.discarded:
            return _DISCARDED_YAML_SCALAR
        return "".join(chunks)


@dataclass(slots=True)
class _PendingYamlPieces:
    pieces: list[str]
    utf8_bytes: int = 0
    overflow: bool = False

    @classmethod
    def empty(cls) -> _PendingYamlPieces:
        return cls([])

    def __bool__(self) -> bool:
        return self.overflow or bool(self.pieces)

    def add(self, value: str) -> None:
        if not value or self.overflow:
            return
        try:
            size = len(value.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            raise ResourceLimitError("invalid_utf8") from None
        if self.utf8_bytes + size > RESOURCE_LIMITS_V1.bounded_string_bytes:
            self.pieces.clear()
            self.overflow = True
            return
        self.utf8_bytes += size
        self.pieces.append(value)

    def add_spaces(self, count: int) -> None:
        if count <= 0 or self.overflow:
            return
        if self.utf8_bytes + count > RESOURCE_LIMITS_V1.bounded_string_bytes:
            self.pieces.clear()
            self.overflow = True
            return
        self.utf8_bytes += count
        self.pieces.append(" " * count)

    def absorb(self, other: _PendingYamlPieces) -> None:
        if other.overflow:
            self.pieces.clear()
            self.overflow = True
            return
        for piece in other.pieces:
            self.add(piece)

    def append_to(self, budget: _YamlUtf8Budget, chunks: list[str]) -> None:
        if budget.discarded:
            return
        if self.overflow:
            if budget.hard:
                raise ResourceLimitError("bounded_string_limit")
            budget.discard(chunks)
            return
        for piece in self.pieces:
            budget.append(chunks, piece)


class _BoundedDiscriminatorLoader(yaml.SafeLoader):
    """PyYAML scanner with scalar budgets enforced before token allocation.

    The scalar routines intentionally track the supported PyYAML 6.0.x ``Scanner`` grammar.
    The only semantic change is bounded retention before ``prefix`` and token joins.
    """

    def fetch_alias(self) -> None:
        raise StrictYamlError("yaml_alias", "YAML aliases are forbidden")

    def fetch_anchor(self) -> None:
        raise StrictYamlError("yaml_anchor", "YAML anchors are forbidden")

    def _line_break(self) -> str:
        return cast(str, self.scan_line_break())  # type: ignore[no-untyped-call]

    def scan_directive_name(self, start_mark: Mark) -> str:
        length = 0
        character = self.peek(length)
        while (
            "0" <= character <= "9"
            or "A" <= character <= "Z"
            or "a" <= character <= "z"
            or character in "-_"
        ):
            if length >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                raise ResourceLimitError("bounded_string_limit")
            length += 1
            character = self.peek(length)
        if not length:
            raise ScannerError(
                "while scanning a directive",
                start_mark,
                "expected an alphanumeric directive name",
                self.get_mark(),
            )
        value = cast(str, self.prefix(length))
        self.forward(length)
        if self.peek() not in "\0 \r\n\x85\u2028\u2029":
            raise ScannerError(
                "while scanning a directive",
                start_mark,
                "invalid directive name",
                self.get_mark(),
            )
        return value

    def scan_yaml_directive_number(self, start_mark: Mark) -> int:
        if not ("0" <= self.peek() <= "9"):
            raise ScannerError(
                "while scanning a directive",
                start_mark,
                "expected a digit",
                self.get_mark(),
            )
        length = 0
        while "0" <= self.peek(length) <= "9":
            if length >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                raise ResourceLimitError("bounded_string_limit")
            length += 1
        value = int(self.prefix(length))
        self.forward(length)
        return value

    def scan_tag_handle(self, name: str, start_mark: Mark) -> str:
        if self.peek() != "!":
            raise ScannerError(
                f"while scanning a {name}",
                start_mark,
                "expected a tag handle",
                self.get_mark(),
            )
        length = 1
        character = self.peek(length)
        if character != " ":
            while (
                "0" <= character <= "9"
                or "A" <= character <= "Z"
                or "a" <= character <= "z"
                or character in "-_"
            ):
                if length >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                    raise ResourceLimitError("bounded_string_limit")
                length += 1
                character = self.peek(length)
            if character != "!":
                self.forward(length)
                raise ScannerError(
                    f"while scanning a {name}",
                    start_mark,
                    "invalid tag handle",
                    self.get_mark(),
                )
            if length >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                raise ResourceLimitError("bounded_string_limit")
            length += 1
        value = cast(str, self.prefix(length))
        self.forward(length)
        return value

    def scan_tag_uri(self, name: str, start_mark: Mark) -> str:
        chunks: list[str] = []
        budget = _YamlUtf8Budget(hard=True)
        length = 0
        character = self.peek(length)
        allowed = "-;/?:@&=+$,_.!~*'()[]%"
        while (
            "0" <= character <= "9"
            or "A" <= character <= "Z"
            or "a" <= character <= "z"
            or character in allowed
        ):
            if character == "%":
                if length:
                    value = self.prefix(length)
                    self.forward(length)
                    budget.append(chunks, value)
                    length = 0
                budget.append(chunks, self._scan_uri_escapes_bounded(name, start_mark))
            else:
                if length >= budget.remaining:
                    raise ResourceLimitError("bounded_string_limit")
                length += 1
            character = self.peek(length)
        if length:
            value = self.prefix(length)
            self.forward(length)
            budget.append(chunks, value)
        if not chunks:
            raise ScannerError(
                f"while parsing a {name}",
                start_mark,
                "expected a tag URI",
                self.get_mark(),
            )
        return "".join(chunks)

    def scan_tag(self) -> TagToken:
        """Scan a tag without PyYAML's unbounded shorthand-tag lookahead."""

        start_mark = self.get_mark()
        character = self.peek(1)
        if character == "<":
            handle = None
            self.forward(2)
            suffix = self.scan_tag_uri("tag", start_mark)
            if self.peek() != ">":
                raise ScannerError(
                    "while parsing a tag",
                    start_mark,
                    f"expected '>', but found {self.peek()!r}",
                    self.get_mark(),
                )
            self.forward()
        elif character in "\0 \t\r\n\x85\u2028\u2029":
            handle = None
            suffix = "!"
            self.forward()
        else:
            length = 1
            use_handle = False
            while character not in "\0 \r\n\x85\u2028\u2029":
                if character == "!":
                    use_handle = True
                    break
                if length >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                    raise ResourceLimitError("bounded_string_limit")
                length += 1
                character = self.peek(length)
            if use_handle:
                handle = self.scan_tag_handle("tag", start_mark)
            else:
                handle = "!"
                self.forward()
            suffix = self.scan_tag_uri("tag", start_mark)
        character = self.peek()
        if character not in "\0 \r\n\x85\u2028\u2029":
            raise ScannerError(
                "while scanning a tag",
                start_mark,
                f"expected ' ', but found {character!r}",
                self.get_mark(),
            )
        value = (handle, suffix)
        end_mark = self.get_mark()
        return TagToken(value, start_mark, end_mark)

    def _scan_uri_escapes_bounded(self, name: str, start_mark: Mark) -> str:
        codes = bytearray()
        mark = self.get_mark()
        while self.peek() == "%":
            if len(codes) >= RESOURCE_LIMITS_V1.bounded_string_bytes:
                raise ResourceLimitError("bounded_string_limit")
            self.forward()
            for offset in range(2):
                if self.peek(offset) not in "0123456789ABCDEFabcdef":
                    raise ScannerError(
                        f"while scanning a {name}",
                        start_mark,
                        "invalid URI escape sequence",
                        self.get_mark(),
                    )
            codes.append(int(self.prefix(2), 16))
            self.forward(2)
        try:
            return bytes(codes).decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ScannerError(
                f"while scanning a {name}",
                start_mark,
                str(error),
                mark,
            ) from None

    def _plain_terminator(self, offset: int) -> bool:
        character = self.peek(offset)
        if character in "\0 \t\r\n\x85\u2028\u2029":
            return True
        if character == ":" and self.peek(offset + 1) in (
            "\0 \t\r\n\x85\u2028\u2029" + (",[]{}" if self.flow_level else "")
        ):
            return True
        return bool(self.flow_level and character in ",?[]{}")

    def scan_plain(self) -> ScalarToken:
        chunks: list[str] = []
        budget = _YamlUtf8Budget()
        start_mark = self.get_mark()
        end_mark = start_mark
        indent = self.indent + 1
        spaces = _PendingYamlPieces.empty()
        while True:
            if self.peek() == "#" or self._plain_terminator(0):
                break
            spaces.append_to(budget, chunks)
            spaces = _PendingYamlPieces.empty()
            while not self._plain_terminator(0):
                length = 0
                max_length = (
                    RESOURCE_LIMITS_V1.bounded_string_bytes
                    if budget.discarded
                    else max(budget.remaining, 1)
                )
                while length < max_length and not self._plain_terminator(length):
                    length += 1
                if length == 0:
                    break
                self.allow_simple_key = False
                if budget.discarded:
                    self.forward(length)
                else:
                    value = self.prefix(length)
                    self.forward(length)
                    budget.append(chunks, value)
                end_mark = self.get_mark()
            scanned_spaces = self._scan_plain_spaces_bounded(indent, start_mark)
            if scanned_spaces is None:
                break
            spaces = scanned_spaces
            if not spaces or self.peek() == "#" or (not self.flow_level and self.column < indent):
                break
        return ScalarToken(budget.token_value(chunks), True, start_mark, end_mark)

    def _scan_plain_spaces_bounded(
        self,
        indent: int,
        start_mark: Mark,
    ) -> _PendingYamlPieces | None:
        space_count = 0
        while self.peek() == " ":
            self.forward()
            space_count += 1
        character = self.peek()
        pending = _PendingYamlPieces.empty()
        if character in "\r\n\x85\u2028\u2029":
            line_break = self._line_break()
            self.allow_simple_key = True
            prefix = self.prefix(3)
            if prefix in {"---", "..."} and self.peek(3) in "\0 \t\r\n\x85\u2028\u2029":
                return None
            breaks = _PendingYamlPieces.empty()
            while self.peek() in " \r\n\x85\u2028\u2029":
                if self.peek() == " ":
                    self.forward()
                else:
                    breaks.add(self._line_break())
                    prefix = self.prefix(3)
                    if prefix in {"---", "..."} and self.peek(3) in ("\0 \t\r\n\x85\u2028\u2029"):
                        return None
            if line_break != "\n":
                pending.add(line_break)
            elif not breaks:
                pending.add(" ")
            pending.absorb(breaks)
        elif space_count:
            pending.add_spaces(space_count)
        return pending

    def scan_flow_scalar(self, style: str) -> ScalarToken:
        double = style == '"'
        chunks: list[str] = []
        budget = _YamlUtf8Budget()
        start_mark = self.get_mark()
        quote = self.peek()
        self.forward()
        self._scan_flow_scalar_non_spaces_bounded(double, start_mark, budget, chunks)
        while self.peek() != quote:
            self._scan_flow_scalar_spaces_bounded(double, start_mark, budget, chunks)
            self._scan_flow_scalar_non_spaces_bounded(double, start_mark, budget, chunks)
        self.forward()
        end_mark = self.get_mark()
        return ScalarToken(budget.token_value(chunks), False, start_mark, end_mark, style)

    def _scan_flow_scalar_non_spaces_bounded(
        self,
        double: bool,
        start_mark: Mark,
        budget: _YamlUtf8Budget,
        chunks: list[str],
    ) -> None:
        while True:
            length = 0
            max_length = (
                RESOURCE_LIMITS_V1.bounded_string_bytes
                if budget.discarded
                else max(budget.remaining, 1)
            )
            while length < max_length and self.peek(length) not in "'\"\\\0 \t\r\n\x85\u2028\u2029":
                length += 1
            if length:
                if budget.discarded:
                    self.forward(length)
                else:
                    value = self.prefix(length)
                    self.forward(length)
                    budget.append(chunks, value)
                if length == max_length and self.peek() not in "'\"\\\0 \t\r\n\x85\u2028\u2029":
                    continue
            character = self.peek()
            if not double and character == "'" and self.peek(1) == "'":
                budget.append(chunks, "'")
                self.forward(2)
            elif (double and character == "'") or (not double and character in '"\\'):
                budget.append(chunks, character)
                self.forward()
            elif double and character == "\\":
                self.forward()
                character = self.peek()
                if character in self.ESCAPE_REPLACEMENTS:
                    budget.append(chunks, self.ESCAPE_REPLACEMENTS[character])
                    self.forward()
                elif character in self.ESCAPE_CODES:
                    length = self.ESCAPE_CODES[character]
                    self.forward()
                    for offset in range(length):
                        if self.peek(offset) not in "0123456789ABCDEFabcdef":
                            raise ScannerError(
                                "while scanning a double-quoted scalar",
                                start_mark,
                                f"expected escape sequence of {length} hexadecimal numbers",
                                self.get_mark(),
                            )
                    code = int(self.prefix(length), 16)
                    budget.append(chunks, chr(code))
                    self.forward(length)
                elif character in "\r\n\x85\u2028\u2029":
                    self._line_break()
                    breaks = self._scan_flow_scalar_breaks_bounded(double, start_mark)
                    breaks.append_to(budget, chunks)
                else:
                    raise ScannerError(
                        "while scanning a double-quoted scalar",
                        start_mark,
                        "found unknown escape character",
                        self.get_mark(),
                    )
            else:
                return

    def _scan_flow_scalar_spaces_bounded(
        self,
        double: bool,
        start_mark: Mark,
        budget: _YamlUtf8Budget,
        chunks: list[str],
    ) -> None:
        space_count = 0
        while self.peek() in " \t":
            self.forward()
            space_count += 1
        character = self.peek()
        if character == "\0":
            raise ScannerError(
                "while scanning a quoted scalar",
                start_mark,
                "found unexpected end of stream",
                self.get_mark(),
            )
        if character in "\r\n\x85\u2028\u2029":
            line_break = self._line_break()
            breaks = self._scan_flow_scalar_breaks_bounded(double, start_mark)
            if line_break != "\n":
                budget.append(chunks, line_break)
            elif not breaks:
                budget.append(chunks, " ")
            breaks.append_to(budget, chunks)
        elif space_count:
            pending = _PendingYamlPieces.empty()
            pending.add_spaces(space_count)
            pending.append_to(budget, chunks)

    def _scan_flow_scalar_breaks_bounded(
        self,
        double: bool,
        start_mark: Mark,
    ) -> _PendingYamlPieces:
        del double
        breaks = _PendingYamlPieces.empty()
        while True:
            prefix = self.prefix(3)
            if prefix in {"---", "..."} and self.peek(3) in "\0 \t\r\n\x85\u2028\u2029":
                raise ScannerError(
                    "while scanning a quoted scalar",
                    start_mark,
                    "found unexpected document separator",
                    self.get_mark(),
                )
            while self.peek() in " \t":
                self.forward()
            if self.peek() in "\r\n\x85\u2028\u2029":
                breaks.add(self._line_break())
            else:
                return breaks

    def scan_block_scalar(self, style: str) -> ScalarToken:
        folded = style == ">"
        chunks: list[str] = []
        budget = _YamlUtf8Budget()
        start_mark = self.get_mark()
        self.forward()
        chomping, increment = self.scan_block_scalar_indicators(start_mark)
        self.scan_block_scalar_ignored_line(start_mark)
        min_indent = max(self.indent + 1, 1)
        if increment is None:
            breaks, max_indent, end_mark = self._scan_block_scalar_indentation_bounded()
            indent = max(min_indent, max_indent)
        else:
            indent = min_indent + increment - 1
            breaks, end_mark = self._scan_block_scalar_breaks_bounded(indent)
        line_break = ""
        while self.column == indent and self.peek() != "\0":
            breaks.append_to(budget, chunks)
            leading_non_space = self.peek() not in " \t"
            while self.peek() not in "\0\r\n\x85\u2028\u2029":
                length = 0
                max_length = (
                    RESOURCE_LIMITS_V1.bounded_string_bytes
                    if budget.discarded
                    else max(budget.remaining, 1)
                )
                while length < max_length and self.peek(length) not in "\0\r\n\x85\u2028\u2029":
                    length += 1
                if budget.discarded:
                    self.forward(length)
                else:
                    value = self.prefix(length)
                    self.forward(length)
                    budget.append(chunks, value)
            line_break = self._line_break()
            breaks, end_mark = self._scan_block_scalar_breaks_bounded(indent)
            if self.column == indent and self.peek() != "\0":
                if folded and line_break == "\n" and leading_non_space and self.peek() not in " \t":
                    if not breaks:
                        budget.append(chunks, " ")
                else:
                    budget.append(chunks, line_break)
            else:
                break
        if chomping is not False:
            budget.append(chunks, line_break)
        if chomping is True:
            breaks.append_to(budget, chunks)
        return ScalarToken(budget.token_value(chunks), False, start_mark, end_mark, style)

    def _scan_block_scalar_indentation_bounded(
        self,
    ) -> tuple[_PendingYamlPieces, int, Mark]:
        breaks = _PendingYamlPieces.empty()
        max_indent = 0
        end_mark = self.get_mark()
        while self.peek() in " \r\n\x85\u2028\u2029":
            if self.peek() != " ":
                breaks.add(self._line_break())
                end_mark = self.get_mark()
            else:
                self.forward()
                max_indent = max(max_indent, self.column)
        return breaks, max_indent, end_mark

    def _scan_block_scalar_breaks_bounded(
        self,
        indent: int,
    ) -> tuple[_PendingYamlPieces, Mark]:
        breaks = _PendingYamlPieces.empty()
        end_mark = self.get_mark()
        while self.column < indent and self.peek() == " ":
            self.forward()
        while self.peek() in "\r\n\x85\u2028\u2029":
            breaks.add(self._line_break())
            end_mark = self.get_mark()
            while self.column < indent and self.peek() == " ":
                self.forward()
        return breaks, end_mark


def bounded_yaml_discriminator(stream: _YamlStream) -> str | None:
    """Find a top-level case/source discriminator without constructing the document."""

    loader: _BoundedDiscriminatorLoader | None = None
    stack: list[_CollectionFrame] = []
    node_count = 0
    document_count = 0
    case_kind: str | None = None
    schema_version: str | None = None
    provider = False
    case_files = False
    try:
        loader = _BoundedDiscriminatorLoader(cast(Any, stream))
        while loader.check_event():
            event = loader.get_event()  # type: ignore[no-untyped-call]
            if isinstance(event, DocumentStartEvent):
                document_count += 1
                if document_count > 1:
                    raise StrictYamlError("invalid_yaml", "invalid YAML")
                continue
            if isinstance(event, CollectionEndEvent):
                if stack:
                    stack.pop()
                continue
            if not isinstance(event, NodeEvent):
                continue
            node_count += 1
            check_collection_count(
                node_count,
                limit=RESOURCE_LIMITS_V1.case_records * RESOURCE_LIMITS_V1.nesting_depth,
                code="yaml_nodes_limit",
            )
            parent = stack[-1] if stack else None
            is_mapping_key = parent is not None and parent.next_child_is_mapping_key
            if isinstance(event, AliasEvent):
                raise StrictYamlError("yaml_alias", "YAML aliases are forbidden")
            if isinstance(event, ScalarEvent) and is_mapping_key and parent is not None:
                if isinstance(event.value, _DiscardedYamlScalar):
                    raise ResourceLimitError("bounded_string_limit")
                if event.tag == _MERGE_TAG or event.value == "<<":
                    raise StrictYamlError("yaml_merge_key", "YAML merge keys are forbidden")
                parent.pending_scalar_key = event.value
            elif isinstance(event, ScalarEvent) and parent is not None and len(stack) == 1:
                key = parent.pending_scalar_key
                if (
                    not isinstance(event.value, _DiscardedYamlScalar)
                    and key == "kind"
                    and event.value in {"response", "activation"}
                ):
                    case_kind = event.value
                if not isinstance(event.value, _DiscardedYamlScalar) and key == "schema_version":
                    schema_version = event.value
            if parent is not None:
                if not is_mapping_key and parent.pending_scalar_key == "provider":
                    provider = True
                if not is_mapping_key and parent.pending_scalar_key == "case_files":
                    case_files = True
                parent.add_child()
                if parent.kind == "mapping" and not is_mapping_key:
                    parent.pending_scalar_key = None
            if schema_version in {"1", "2"} and provider and case_files:
                return "source"
            if isinstance(event, CollectionStartEvent):
                check_collection_count(
                    len(stack) + 1,
                    limit=RESOURCE_LIMITS_V1.nesting_depth,
                    code="nesting_depth_limit",
                )
                kind = "mapping" if isinstance(event, MappingStartEvent) else "sequence"
                stack.append(
                    _CollectionFrame(
                        kind=kind,
                        limit=RESOURCE_LIMITS_V1.case_records,
                        code="validation_collection_limit",
                    )
                )
        return case_kind
    except (ResourceLimitError, StrictYamlError):
        raise
    except Exception:
        raise StrictYamlError("invalid_yaml", "invalid YAML") from None
    finally:
        if loader is not None:
            loader.dispose()


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
