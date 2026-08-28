"""Deterministic, content-free diagnostic sanitization."""

from __future__ import annotations

from dataclasses import dataclass, fields

from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

DIAGNOSTIC_TRUNCATION_SUFFIX = "…[TRUNCATED]"

_GENERIC_PATTERN_ERROR = "sanitizer pattern table rejected"
_GENERIC_DIAGNOSTIC_ERROR = "diagnostic sanitization failed"
_URL_AUTHORITY_REPLACEMENT = b"[URL-AUTHORITY]"
_PATH_FIELDS = frozenset(
    {
        "capsule_roots",
        "source_roots",
        "input_roots",
        "cwd_roots",
        "home_roots",
    }
)
_CASE_INSENSITIVE_FIELDS = frozenset({"local_fqdns", "local_hostnames"})
_FIELD_REPLACEMENTS = (
    ("credential_values", b"[REDACTED]"),
    ("capsule_roots", b"[CAPSULE]"),
    ("source_roots", b"[SOURCE]"),
    ("input_roots", b"[INPUT]"),
    ("cwd_roots", b"[CWD]"),
    ("home_roots", b"[HOME]"),
    ("local_fqdns", b"[HOST]"),
    ("local_hostnames", b"[HOST]"),
    ("local_usernames", b"[USER]"),
)


class SanitizerError(ValueError):
    """A content-free sanitizer failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _valid_utf8(value: str) -> bool:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _normalize_pattern(field_name: str, value: str) -> str:
    if field_name in _PATH_FIELDS and value != "/":
        return value.rstrip("/")
    return value


@dataclass(frozen=True, slots=True)
class SanitizerPatterns:
    """One immutable operation-owned table of exact sanitizer patterns."""

    credential_values: tuple[str, ...] = ()
    capsule_roots: tuple[str, ...] = ()
    source_roots: tuple[str, ...] = ()
    input_roots: tuple[str, ...] = ()
    cwd_roots: tuple[str, ...] = ()
    home_roots: tuple[str, ...] = ()
    local_fqdns: tuple[str, ...] = ()
    local_hostnames: tuple[str, ...] = ()
    local_usernames: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for definition in fields(self):
            values = object.__getattribute__(self, definition.name)
            if type(values) is not tuple:
                raise SanitizerError("invalid_sanitizer_pattern", _GENERIC_PATTERN_ERROR)
            normalized: list[str] = []
            seen: set[str] = set()
            for value in values:
                if type(value) is not str or not _valid_utf8(value):
                    raise SanitizerError("invalid_sanitizer_pattern", _GENERIC_PATTERN_ERROR)
                pattern = _normalize_pattern(definition.name, value)
                if pattern and pattern not in seen:
                    normalized.append(pattern)
                    seen.add(pattern)
            object.__setattr__(self, definition.name, tuple(normalized))


@dataclass(frozen=True, slots=True)
class SanitizedDiagnostic:
    """Sanitized diagnostic text plus pre-truncation credential replacement count."""

    text: str
    credential_replacement_count: int


@dataclass(frozen=True, slots=True)
class _Pattern:
    value: bytes
    replacement: bytes
    class_index: int
    credential: bool
    path: bool
    ascii_case_insensitive: bool


def _ascii_lower(value: bytes) -> bytes:
    return bytes(byte + 32 if 65 <= byte <= 90 else byte for byte in value)


def _compiled_patterns(patterns: SanitizerPatterns) -> tuple[_Pattern, ...]:
    if type(patterns) is not SanitizerPatterns:
        raise SanitizerError("invalid_sanitizer_pattern", _GENERIC_PATTERN_ERROR)
    compiled: list[_Pattern] = []
    for class_index, (field_name, replacement) in enumerate(_FIELD_REPLACEMENTS):
        values = object.__getattribute__(patterns, field_name)
        for value in values:
            encoded = value.encode("utf-8", errors="strict")
            compiled.append(
                _Pattern(
                    value=encoded,
                    replacement=replacement,
                    class_index=class_index,
                    credential=field_name == "credential_values",
                    path=field_name in _PATH_FIELDS,
                    ascii_case_insensitive=field_name in _CASE_INSENSITIVE_FIELDS,
                )
            )
    return tuple(
        sorted(
            compiled,
            key=lambda item: (-len(item.value), item.class_index, item.value),
        )
    )


def _url_terminator(character: str) -> bool:
    codepoint = ord(character)
    return (
        character in "/?#" or character.isspace() or codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F
    )


def _ascii_scheme_length(value: str, offset: int) -> int:
    for scheme in ("https://", "http://"):
        candidate = value[offset : offset + len(scheme)]
        try:
            encoded = candidate.encode("ascii", errors="strict")
        except UnicodeEncodeError:
            continue
        if _ascii_lower(encoded) == scheme.encode("ascii"):
            return len(scheme)
    return 0


def _url_segments(value: str) -> tuple[tuple[bytes, bool], ...]:
    segments: list[tuple[bytes, bool]] = []
    start = 0
    offset = 0
    while offset < len(value):
        scheme_length = _ascii_scheme_length(value, offset)
        if scheme_length == 0:
            offset += 1
            continue
        authority_start = offset + scheme_length
        authority_end = authority_start
        while authority_end < len(value) and not _url_terminator(value[authority_end]):
            authority_end += 1
        if start < authority_start:
            segments.append((value[start:authority_start].encode("utf-8"), False))
        segments.append((_URL_AUTHORITY_REPLACEMENT, True))
        start = authority_end
        offset = authority_end
    if start < len(value):
        segments.append((value[start:].encode("utf-8"), False))
    return tuple(segments)


def _matches(data: bytes, offset: int, pattern: _Pattern) -> bool:
    end = offset + len(pattern.value)
    if end > len(data):
        return False
    candidate = data[offset:end]
    if pattern.ascii_case_insensitive:
        equal = _ascii_lower(candidate) == _ascii_lower(pattern.value)
    else:
        equal = candidate == pattern.value
    if not equal or not pattern.path:
        return equal
    if pattern.value == b"/":
        return True
    return end == len(data) or data[end] == ord("/")


def _codepoint_length(first_byte: int) -> int:
    if first_byte < 0x80:
        return 1
    if first_byte < 0xE0:
        return 2
    if first_byte < 0xF0:
        return 3
    return 4


def _replace_patterns(data: bytes, patterns: tuple[_Pattern, ...]) -> tuple[bytes, int]:
    output = bytearray()
    credential_count = 0
    offset = 0
    while offset < len(data):
        selected = next((item for item in patterns if _matches(data, offset, item)), None)
        if selected is not None:
            output.extend(selected.replacement)
            credential_count += int(selected.credential)
            offset += len(selected.value)
            continue
        width = _codepoint_length(data[offset])
        output.extend(data[offset : offset + width])
        offset += width
    return bytes(output), credential_count


def _normalize_controls_and_whitespace(value: str) -> str:
    output: list[str] = []
    in_ascii_whitespace = False
    for character in value:
        codepoint = ord(character)
        if codepoint <= 0x08 or 0x0E <= codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F:
            continue
        if character == " " or 0x09 <= codepoint <= 0x0D:
            if not in_ascii_whitespace:
                output.append(" ")
                in_ascii_whitespace = True
            continue
        output.append(character)
        in_ascii_whitespace = False
    return "".join(output)


def _truncate(value: str) -> str:
    limit = RESOURCE_LIMITS_V1.diagnostic_bytes
    if len(value.encode("utf-8")) <= limit:
        return value
    suffix_bytes = DIAGNOSTIC_TRUNCATION_SUFFIX.encode("utf-8")
    budget = limit - len(suffix_bytes)
    prefix: list[str] = []
    used = 0
    for character in value:
        encoded = character.encode("utf-8")
        if used + len(encoded) > budget:
            break
        prefix.append(character)
        used += len(encoded)
    return "".join(prefix) + DIAGNOSTIC_TRUNCATION_SUFFIX


def sanitize_diagnostic(
    diagnostic: str,
    *,
    patterns: SanitizerPatterns,
) -> SanitizedDiagnostic:
    """Sanitize one diagnostic with deterministic non-rescanning replacement."""

    if type(diagnostic) is not str or not _valid_utf8(diagnostic):
        raise SanitizerError("invalid_diagnostic", _GENERIC_DIAGNOSTIC_ERROR)
    compiled = _compiled_patterns(patterns)
    credential_count = 0
    output = bytearray()
    for segment, protected in _url_segments(diagnostic):
        if protected:
            output.extend(segment)
            continue
        replaced, count = _replace_patterns(segment, compiled)
        output.extend(replaced)
        credential_count += count
    normalized = _normalize_controls_and_whitespace(output.decode("utf-8", errors="strict"))
    return SanitizedDiagnostic(
        text=_truncate(normalized),
        credential_replacement_count=credential_count,
    )
