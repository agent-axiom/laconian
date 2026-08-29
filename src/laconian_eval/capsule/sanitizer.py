"""Deterministic, content-free diagnostic sanitization."""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Iterator
from dataclasses import dataclass, fields

from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

DIAGNOSTIC_TRUNCATION_SUFFIX = "…[TRUNCATED]"

_GENERIC_PATTERN_ERROR = "sanitizer pattern table rejected"
_GENERIC_DIAGNOSTIC_ERROR = "diagnostic sanitization failed"
_GENERIC_OUTPUT_ERROR = "output sanitization failed"
_UNSAFE_PROVIDER_METADATA_ERROR = "unsafe_provider_metadata"
_URL_AUTHORITY_REPLACEMENT = b"[URL-AUTHORITY]"
_OUTPUT_STREAM_CHUNK_CHARACTERS = 4096
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
class SanitizedOutput:
    """Post-redaction output evidence with optional retained text."""

    text: str | None
    byte_length: int
    sha256: str
    credential_replacement_count: int

    @property
    def was_redacted(self) -> bool:
        return self.credential_replacement_count > 0


@dataclass(frozen=True, slots=True)
class _Pattern:
    value: bytes
    replacement: bytes
    class_index: int
    credential: bool
    path: bool
    ascii_case_insensitive: bool


@dataclass(frozen=True, slots=True)
class _CredentialPattern:
    text: str
    utf8: bytes


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
    ordered = sorted(
        compiled,
        key=lambda item: (-len(item.value), item.class_index, item.value),
    )
    deduplicated: list[_Pattern] = []
    seen: set[bytes] = set()
    for item in ordered:
        if item.value in seen:
            continue
        deduplicated.append(item)
        seen.add(item.value)
    return tuple(deduplicated)


def _compiled_credential_patterns(patterns: SanitizerPatterns) -> tuple[_CredentialPattern, ...]:
    if type(patterns) is not SanitizerPatterns:
        raise SanitizerError("invalid_sanitizer_pattern", _GENERIC_PATTERN_ERROR)
    return tuple(
        sorted(
            (
                _CredentialPattern(
                    text=value,
                    utf8=value.encode("utf-8", errors="strict"),
                )
                for value in patterns.credential_values
            ),
            key=lambda item: (-len(item.utf8), item.utf8),
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


def _prefix_lengths(pattern: str) -> tuple[int, ...]:
    lengths = [0] * len(pattern)
    matched = 0
    for offset in range(1, len(pattern)):
        while matched and pattern[offset] != pattern[matched]:
            matched = lengths[matched - 1]
        if pattern[offset] == pattern[matched]:
            matched += 1
        lengths[offset] = matched
    return tuple(lengths)


def _credential_occurrences(value: str, pattern: str) -> Iterator[int]:
    prefix_lengths = _prefix_lengths(pattern)
    matched = 0
    for offset in range(str.__len__(value)):
        character = str.__getitem__(value, offset)
        while matched and character != pattern[matched]:
            matched = prefix_lengths[matched - 1]
        if character == pattern[matched]:
            matched += 1
        if matched == len(pattern):
            yield offset - len(pattern) + 1
            matched = prefix_lengths[matched - 1]


def _is_ascii_alphanumeric(byte: int) -> bool:
    return 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122


def _local_identity_is_delimited(data: bytes, offset: int, pattern: _Pattern) -> bool:
    end = offset + len(pattern.value)
    before_is_boundary = offset == 0 or not _is_ascii_alphanumeric(data[offset - 1])
    after_is_boundary = end == len(data) or not _is_ascii_alphanumeric(data[end])
    return before_is_boundary and after_is_boundary


def _contains_url_authority(value: str) -> bool:
    return any(_ascii_scheme_length(value, offset) > 0 for offset in range(len(value)))


def _contains_control(value: str) -> bool:
    return any(ord(character) <= 0x1F or 0x7F <= ord(character) <= 0x9F for character in value)


def sanitize_output(
    value: str,
    *,
    patterns: SanitizerPatterns,
) -> SanitizedOutput:
    """Redact credentials while streaming post-redaction output evidence."""

    if (
        type(value) is not str
        or not value
        or not any(not character.isspace() for character in value)
    ):
        raise SanitizerError("invalid_output", _GENERIC_OUTPUT_ERROR)
    compiled = _compiled_credential_patterns(patterns)
    digest = hashlib.sha256()
    retained_chunks: list[bytes] | None = []
    byte_length = 0
    credential_count = 0
    source_length = str.__len__(value)
    transformed_buffer = bytearray()
    batch_limit = _OUTPUT_STREAM_CHUNK_CHARACTERS
    source_chunk_characters = max(batch_limit // 4, 1)

    def record_transformed_chunk(chunk: bytes) -> None:
        nonlocal byte_length, retained_chunks
        digest.update(chunk)
        byte_length += len(chunk)
        if retained_chunks is not None:
            if byte_length <= RESOURCE_LIMITS_V1.output_utf8_bytes:
                retained_chunks.append(chunk)
            else:
                retained_chunks.clear()
                retained_chunks = None

    def flush_transformed_buffer() -> None:
        if not transformed_buffer:
            return
        chunk = bytes(transformed_buffer)
        transformed_buffer.clear()
        record_transformed_chunk(chunk)

    def emit_transformed(data: bytes) -> None:
        offset = 0
        while offset < len(data):
            available = batch_limit - len(transformed_buffer)
            take = min(available, len(data) - offset)
            transformed_buffer.extend(data[offset : offset + take])
            offset += take
            if len(transformed_buffer) == batch_limit:
                flush_transformed_buffer()

    def emit_source_span(start: int, end: int) -> None:
        for chunk_start in range(start, end, source_chunk_characters):
            chunk = str.__getitem__(
                value,
                slice(chunk_start, min(chunk_start + source_chunk_characters, end)),
            )
            try:
                encoded = chunk.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                raise SanitizerError("invalid_output", _GENERIC_OUTPUT_ERROR) from None
            emit_transformed(encoded)

    occurrences: list[tuple[int, int, Iterator[int]]] = []
    for compiled_order, pattern in enumerate(compiled):
        iterator = _credential_occurrences(value, pattern.text)
        occurrence = next(iterator, None)
        if occurrence is not None:
            heapq.heappush(occurrences, (occurrence, compiled_order, iterator))

    source_index = 0
    while occurrences:
        occurrence, compiled_order, iterator = heapq.heappop(occurrences)
        if occurrence >= source_index:
            pattern = compiled[compiled_order]
            emit_source_span(source_index, occurrence)
            emit_transformed(b"[REDACTED]")
            credential_count += 1
            source_index = occurrence + len(pattern.text)
        next_occurrence = next(iterator, None)
        if next_occurrence is not None:
            heapq.heappush(
                occurrences,
                (next_occurrence, compiled_order, iterator),
            )

    emit_source_span(source_index, source_length)
    flush_transformed_buffer()

    text = (
        None
        if retained_chunks is None
        else b"".join(retained_chunks).decode("utf-8", errors="strict")
    )
    return SanitizedOutput(
        text=text,
        byte_length=byte_length,
        sha256=digest.hexdigest(),
        credential_replacement_count=credential_count,
    )


def provider_metadata_is_safe(
    value: object,
    *,
    patterns: SanitizerPatterns,
) -> bool:
    """Return whether optional provider metadata is safe to persist unchanged."""

    if value is None:
        return True
    if type(value) is not str or not value:
        return False
    if str.__len__(value) > RESOURCE_LIMITS_V1.bounded_string_bytes:
        return False
    if not any(not character.isspace() for character in value):
        return False
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    if len(encoded) > RESOURCE_LIMITS_V1.bounded_string_bytes:
        return False
    if _contains_control(value) or _contains_url_authority(value):
        return False

    compiled = _compiled_patterns(patterns)
    offset = 0
    while offset < len(encoded):
        for pattern in compiled:
            if not _matches(encoded, offset, pattern):
                continue
            if (
                pattern.credential
                or pattern.path
                or _local_identity_is_delimited(
                    encoded,
                    offset,
                    pattern,
                )
            ):
                return False
        offset += _codepoint_length(encoded[offset])
    return True


def require_safe_provider_metadata(
    value: object,
    *,
    patterns: SanitizerPatterns,
) -> str | None:
    """Return safe metadata unchanged or fail with a content-free error."""

    if not provider_metadata_is_safe(value, patterns=patterns):
        raise SanitizerError(
            _UNSAFE_PROVIDER_METADATA_ERROR,
            _UNSAFE_PROVIDER_METADATA_ERROR,
        )
    if value is None:
        return None
    assert isinstance(value, str)
    return value


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


def _normalized_diagnostic(
    diagnostic: str,
    *,
    patterns: SanitizerPatterns,
) -> SanitizedDiagnostic:
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
        text=normalized,
        credential_replacement_count=credential_count,
    )


def _truncate_diagnostic(diagnostic: SanitizedDiagnostic) -> SanitizedDiagnostic:
    return SanitizedDiagnostic(
        text=_truncate(diagnostic.text),
        credential_replacement_count=diagnostic.credential_replacement_count,
    )


def sanitize_diagnostic(
    diagnostic: str,
    *,
    patterns: SanitizerPatterns,
) -> SanitizedDiagnostic:
    """Sanitize one diagnostic with deterministic non-rescanning replacement."""

    if type(diagnostic) is not str or not _valid_utf8(diagnostic):
        raise SanitizerError("invalid_diagnostic", _GENERIC_DIAGNOSTIC_ERROR)
    return _truncate_diagnostic(_normalized_diagnostic(diagnostic, patterns=patterns))


def sanitize_diagnostic_or_constant(
    value: object,
    *,
    patterns: SanitizerPatterns,
) -> SanitizedDiagnostic:
    """Sanitize a diagnostic or return the fixed content-free fallback."""

    fallback = SanitizedDiagnostic(
        text=_GENERIC_DIAGNOSTIC_ERROR,
        credential_replacement_count=0,
    )
    if type(value) is not str or not _valid_utf8(value):
        return fallback
    normalized = _normalized_diagnostic(value, patterns=patterns)
    return _truncate_diagnostic(normalized) if normalized.text.strip() else fallback
