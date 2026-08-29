from __future__ import annotations

import builtins
import hashlib
from dataclasses import FrozenInstanceError

import pytest

import laconian_eval.capsule.sanitizer as sanitizer_module
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.sanitizer import (
    DIAGNOSTIC_TRUNCATION_SUFFIX,
    SanitizedDiagnostic,
    SanitizerError,
    SanitizerPatterns,
    sanitize_diagnostic,
)


def _patterns(**overrides: tuple[str, ...]) -> SanitizerPatterns:
    values: dict[str, tuple[str, ...]] = {
        "credential_values": (),
        "capsule_roots": (),
        "source_roots": (),
        "input_roots": (),
        "cwd_roots": (),
        "home_roots": (),
        "local_fqdns": (),
        "local_hostnames": (),
        "local_usernames": (),
    }
    values.update(overrides)
    return SanitizerPatterns(**values)


def test_sanitizer_pattern_table_and_result_are_immutable() -> None:
    patterns = _patterns(credential_values=("secret",))
    result = sanitize_diagnostic("secret", patterns=patterns)

    assert result == SanitizedDiagnostic(
        text="[REDACTED]",
        credential_replacement_count=1,
    )
    with pytest.raises(FrozenInstanceError):
        patterns.credential_values = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"  # type: ignore[misc]


def test_longest_original_utf8_match_wins_before_class_priority() -> None:
    patterns = _patterns(
        credential_values=("/workspace",),
        source_roots=("/workspace/project",),
    )

    result = sanitize_diagnostic(
        "failed below /workspace/project/src",
        patterns=patterns,
    )

    assert result.text == "failed below [SOURCE]/src"
    assert result.credential_replacement_count == 0


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("credential_values", "[REDACTED]"),
        ("capsule_roots", "[CAPSULE]"),
        ("source_roots", "[SOURCE]"),
        ("input_roots", "[INPUT]"),
        ("cwd_roots", "[CWD]"),
        ("home_roots", "[HOME]"),
        ("local_fqdns", "[HOST]"),
        ("local_hostnames", "[HOST]"),
        ("local_usernames", "[USER]"),
    ],
)
def test_equal_pattern_uses_normative_class_priority(
    field: str,
    replacement: str,
) -> None:
    ordered_fields = (
        "credential_values",
        "capsule_roots",
        "source_roots",
        "input_roots",
        "cwd_roots",
        "home_roots",
        "local_fqdns",
        "local_hostnames",
        "local_usernames",
    )
    first_index = ordered_fields.index(field)
    values = {
        name: (("same",) if ordered_fields.index(name) >= first_index else ())
        for name in ordered_fields
    }

    result = sanitize_diagnostic("same", patterns=_patterns(**values))

    assert result.text == replacement
    assert result.credential_replacement_count == (1 if field == "credential_values" else 0)


def test_empty_and_duplicate_patterns_are_omitted_or_deduplicated() -> None:
    patterns = _patterns(
        credential_values=("", "token", "token"),
        capsule_roots=("", "/capsule/", "/capsule"),
    )

    result = sanitize_diagnostic(
        "token token at /capsule/file",
        patterns=patterns,
    )

    assert result.text == "[REDACTED] [REDACTED] at [CAPSULE]/file"
    assert result.credential_replacement_count == 2


@pytest.mark.parametrize("pattern", [123, "\ud800"])
def test_pattern_table_rejects_non_strings_and_surrogates_without_echo(
    pattern: object,
) -> None:
    with pytest.raises(SanitizerError) as caught:
        SanitizerPatterns(credential_values=(pattern,))  # type: ignore[arg-type]

    assert caught.value.code == "invalid_sanitizer_pattern"
    assert str(caught.value) == "sanitizer pattern table rejected"


def test_pattern_table_requires_exact_builtin_strings() -> None:
    class StringSubclass(str):
        pass

    with pytest.raises(SanitizerError) as caught:
        SanitizerPatterns(
            credential_values=(StringSubclass("secret"),),
        )

    assert caught.value.code == "invalid_sanitizer_pattern"
    assert str(caught.value) == "sanitizer pattern table rejected"


def test_pattern_table_rejects_mutable_sequence_aliases() -> None:
    mutable = ["secret"]

    with pytest.raises(SanitizerError) as caught:
        SanitizerPatterns(credential_values=mutable)  # type: ignore[arg-type]

    mutable[0] = "changed-after-construction"
    assert caught.value.code == "invalid_sanitizer_pattern"
    assert str(caught.value) == "sanitizer pattern table rejected"


def test_replacements_are_not_rescanned() -> None:
    patterns = _patterns(
        credential_values=("secret", "[CAPSULE]"),
        capsule_roots=("/capsule",),
        source_roots=("[REDACTED]",),
    )

    result = sanitize_diagnostic("secret /capsule", patterns=patterns)

    assert result.text == "[REDACTED] [CAPSULE]"
    assert result.credential_replacement_count == 1


def test_matching_uses_utf8_boundaries_without_unicode_normalization() -> None:
    patterns = _patterns(credential_values=("é", "éé"))

    result = sanitize_diagnostic("éé e\u0301", patterns=patterns)

    assert result.text == "[REDACTED] e\u0301"
    assert result.credential_replacement_count == 1


def test_paths_require_end_or_separator_boundary() -> None:
    patterns = _patterns(
        capsule_roots=("/work/a",),
        source_roots=("/work/a-long",),
    )

    result = sanitize_diagnostic(
        "/work/a /work/a/file /work/ab /work/a-longer /work/a-long/file /work/a",
        patterns=patterns,
    )

    assert result.text == ("/work/a [CAPSULE]/file /work/ab /work/a-longer [SOURCE]/file [CAPSULE]")


def test_filesystem_root_is_the_only_path_boundary_exception() -> None:
    patterns = _patterns(capsule_roots=("/",), source_roots=("/longer",))

    result = sanitize_diagnostic("/a/b /longer/path", patterns=patterns)

    assert result.text == "[CAPSULE]a[CAPSULE]b [SOURCE][CAPSULE]path"


def test_lexical_and_descriptor_resolved_macos_aliases_share_a_class() -> None:
    patterns = _patterns(
        input_roots=(
            "/var/folders/ab/work/input",
            "/private/var/folders/ab/work/input",
        )
    )

    result = sanitize_diagnostic(
        "left=/var/folders/ab/work/input/cases right=/private/var/folders/ab/work/input/cases",
        patterns=patterns,
    )

    assert result.text == "left=[INPUT]/cases right=[INPUT]/cases"


def test_credentials_paths_and_usernames_are_case_sensitive() -> None:
    patterns = _patterns(
        credential_values=("Secret",),
        capsule_roots=("/Capsule",),
        local_usernames=("Alice",),
    )

    result = sanitize_diagnostic(
        "Secret secret /Capsule/file /capsule/file Alice alice",
        patterns=patterns,
    )

    assert result.text == "[REDACTED] secret [CAPSULE]/file /capsule/file [USER] alice"
    assert result.credential_replacement_count == 1


def test_hostname_and_fqdn_matching_is_ascii_case_insensitive() -> None:
    patterns = _patterns(
        local_fqdns=("Build.Example.Test",),
        local_hostnames=("Build",),
    )

    result = sanitize_diagnostic(
        "BUILD.EXAMPLE.TEST build Build.example.test",
        patterns=patterns,
    )

    assert result.text == "[HOST] [HOST] [HOST]"


def test_hostname_matching_does_not_apply_unicode_case_folding() -> None:
    result = sanitize_diagnostic(
        "Ä ä",
        patterns=_patterns(local_hostnames=("Ä",)),
    )

    assert result.text == "[HOST] ä"


def test_url_authorities_are_removed_first_and_never_rescanned() -> None:
    patterns = _patterns(
        credential_values=("secret", "[URL-AUTHORITY]"),
        local_hostnames=("host",),
    )

    result = sanitize_diagnostic(
        "HTTPS://user:secret@HOST:443/path http://host?q=1 https://host#fragment http://host",
        patterns=patterns,
    )

    assert result.text == (
        "HTTPS://[URL-AUTHORITY]/path http://[URL-AUTHORITY]?q=1 "
        "https://[URL-AUTHORITY]#fragment http://[URL-AUTHORITY]"
    )
    assert result.credential_replacement_count == 0


def test_url_authority_stops_at_whitespace_and_controls() -> None:
    result = sanitize_diagnostic(
        "http://one.test\ttail https://two.test\x00tail",
        patterns=_patterns(),
    )

    assert result.text == "http://[URL-AUTHORITY] tail https://[URL-AUTHORITY]tail"


@pytest.mark.parametrize(
    ("diagnostic", "expected"),
    [
        ("http://host€tail", "http://[URL-AUTHORITY]"),
        ("http://host\u0085tail", "http://[URL-AUTHORITY]tail"),
        ("http://hostĀtail", "http://[URL-AUTHORITY]"),
        ("http://host\u00a0tail", "http://[URL-AUTHORITY]\u00a0tail"),
        ("http://host\u2003tail", "http://[URL-AUTHORITY]\u2003tail"),
    ],
)
def test_url_authority_scans_unicode_scalars_without_splitting_utf8(
    diagnostic: str,
    expected: str,
) -> None:
    result = sanitize_diagnostic(diagnostic, patterns=_patterns())

    assert result.text == expected


def test_controls_are_removed_and_ascii_whitespace_runs_collapse() -> None:
    result = sanitize_diagnostic(
        "  alpha\t\r\n beta\x00\x08\x0e\x1f\x7f\x85   gamma  ",
        patterns=_patterns(),
    )

    assert result.text == " alpha beta gamma "
    assert result.credential_replacement_count == 0


def test_non_ascii_whitespace_is_not_collapsed() -> None:
    result = sanitize_diagnostic(
        "alpha\u00a0\u2003beta",
        patterns=_patterns(),
    )

    assert result.text == "alpha\u00a0\u2003beta"


def test_truncation_retains_the_longest_complete_utf8_prefix() -> None:
    suffix = "…[TRUNCATED]"
    suffix_bytes = suffix.encode("utf-8")
    prefix_budget = RESOURCE_LIMITS_V1.diagnostic_bytes - len(suffix_bytes)
    complete_prefix = "é" * (prefix_budget // len("é".encode()))
    result = sanitize_diagnostic("é" * 4096, patterns=_patterns())

    assert suffix == DIAGNOSTIC_TRUNCATION_SUFFIX
    assert result.text == complete_prefix + suffix
    assert len(result.text.encode("utf-8")) <= RESOURCE_LIMITS_V1.diagnostic_bytes
    assert len((complete_prefix + "é" + suffix).encode("utf-8")) > (
        RESOURCE_LIMITS_V1.diagnostic_bytes
    )


def test_exact_diagnostic_byte_limit_is_not_given_a_truncation_suffix() -> None:
    diagnostic = "x" * RESOURCE_LIMITS_V1.diagnostic_bytes

    result = sanitize_diagnostic(diagnostic, patterns=_patterns())

    assert result.text == diagnostic
    assert not result.text.endswith(DIAGNOSTIC_TRUNCATION_SUFFIX)


def test_credential_count_is_computed_before_truncation() -> None:
    patterns = _patterns(credential_values=("x",))

    result = sanitize_diagnostic("x" * 10_000, patterns=patterns)

    assert result.credential_replacement_count == 10_000
    assert result.text.endswith(DIAGNOSTIC_TRUNCATION_SUFFIX)
    assert len(result.text.encode("utf-8")) <= RESOURCE_LIMITS_V1.diagnostic_bytes


@pytest.mark.parametrize("value", [123, "\ud800"])
def test_invalid_diagnostic_input_fails_without_echoing_it(value: object) -> None:
    with pytest.raises(SanitizerError) as caught:
        sanitize_diagnostic(value, patterns=_patterns())  # type: ignore[arg-type]

    assert caught.value.code == "invalid_diagnostic"
    assert str(caught.value) == "diagnostic sanitization failed"


def test_diagnostic_requires_an_exact_builtin_string() -> None:
    class StringSubclass(str):
        pass

    with pytest.raises(SanitizerError) as caught:
        sanitize_diagnostic(StringSubclass("secret"), patterns=_patterns())

    assert caught.value.code == "invalid_diagnostic"
    assert str(caught.value) == "diagnostic sanitization failed"


def test_output_uses_only_credential_patterns_longest_first() -> None:
    patterns = _patterns(
        credential_values=("secret", "secret-long"),
        source_roots=("/workspace",),
        local_hostnames=("builder",),
    )
    expected_text = "[REDACTED] [REDACTED] /workspace builder"

    result = sanitizer_module.sanitize_output(
        "secret-long secret /workspace builder",
        patterns=patterns,
    )

    assert result == sanitizer_module.SanitizedOutput(
        text=expected_text,
        byte_length=len(expected_text.encode("utf-8")),
        sha256=hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
        credential_replacement_count=2,
    )
    assert result.was_redacted is True
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"  # type: ignore[misc]


def test_output_replacements_are_not_rescanned() -> None:
    result = sanitizer_module.sanitize_output(
        "secret",
        patterns=_patterns(credential_values=("secret", "[REDACTED]")),
    )

    assert result.text == "[REDACTED]"
    assert result.credential_replacement_count == 1


def test_output_redaction_count_precedes_size_decision() -> None:
    limit = RESOURCE_LIMITS_V1.output_utf8_bytes
    replacement_bytes = len(b"[REDACTED]")
    occurrences = (limit // replacement_bytes) + 1

    result = sanitizer_module.sanitize_output(
        "x" * occurrences,
        patterns=_patterns(credential_values=("x",)),
    )

    assert result.text is None
    assert result.byte_length == occurrences * replacement_bytes
    assert result.credential_replacement_count == occurrences
    assert result.was_redacted is True


def test_output_at_two_mib_is_retained_with_exact_hash() -> None:
    value = "x" * RESOURCE_LIMITS_V1.output_utf8_bytes

    result = sanitizer_module.sanitize_output(value, patterns=_patterns())

    assert result.text == value
    assert result.byte_length == RESOURCE_LIMITS_V1.output_utf8_bytes
    assert result.sha256 == hashlib.sha256(value.encode("utf-8")).hexdigest()
    assert result.credential_replacement_count == 0
    assert result.was_redacted is False


def test_output_over_two_mib_retains_only_sanitized_length_and_hash() -> None:
    value = "x" * (RESOURCE_LIMITS_V1.output_utf8_bytes + 1)

    result = sanitizer_module.sanitize_output(value, patterns=_patterns())

    assert result == sanitizer_module.SanitizedOutput(
        text=None,
        byte_length=RESOURCE_LIMITS_V1.output_utf8_bytes + 1,
        sha256=hashlib.sha256(value.encode("utf-8")).hexdigest(),
        credential_replacement_count=0,
    )


def test_output_never_hashes_or_retains_pre_redaction_secret_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sha256 = hashlib.sha256
    hashed_chunks: list[bytes] = []

    class RecordingHash:
        def __init__(self) -> None:
            self._inner = original_sha256()

        def update(self, value: bytes) -> None:
            hashed_chunks.append(bytes(value))
            self._inner.update(value)

        def hexdigest(self) -> str:
            return self._inner.hexdigest()

    monkeypatch.setattr(sanitizer_module.hashlib, "sha256", RecordingHash)
    secret = "top-secret-value"
    expected_text = "before [REDACTED] after"

    result = sanitizer_module.sanitize_output(
        f"before {secret} after",
        patterns=_patterns(credential_values=(secret,)),
    )

    hashed = b"".join(hashed_chunks)
    assert hashed == expected_text.encode("utf-8")
    assert secret.encode("utf-8") not in hashed
    assert result.text == expected_text
    assert result.sha256 == original_sha256(hashed).hexdigest()


def test_output_secret_crossing_stream_chunk_boundary_is_redacted() -> None:
    prefix = "a" * 4094
    secret = "secret-crossing-boundary"

    result = sanitizer_module.sanitize_output(
        prefix + secret + " tail",
        patterns=_patterns(credential_values=(secret,)),
    )

    assert result.text == prefix + "[REDACTED] tail"
    assert result.credential_replacement_count == 1


def test_output_multibyte_scalar_adjacent_to_chunk_boundary_is_preserved() -> None:
    value = ("a" * 4095) + "€" + "tail"

    result = sanitizer_module.sanitize_output(value, patterns=_patterns())

    assert result.text == value
    assert result.byte_length == len(value.encode("utf-8"))
    assert result.sha256 == hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_output_overlong_nonmatch_never_accumulates_a_raw_byte_carry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sha256 = hashlib.sha256
    hashed_chunks: list[bytes] = []

    class RecordingHash:
        def __init__(self) -> None:
            self._inner = original_sha256()

        def update(self, value: bytes) -> None:
            hashed_chunks.append(bytes(value))
            self._inner.update(value)

        def hexdigest(self) -> str:
            return self._inner.hexdigest()

    monkeypatch.setattr(sanitizer_module, "_OUTPUT_STREAM_CHUNK_CHARACTERS", 4)
    monkeypatch.setattr(sanitizer_module.hashlib, "sha256", RecordingHash)
    value = "x" * 32

    result = sanitizer_module.sanitize_output(
        value,
        patterns=_patterns(credential_values=("x" * 33,)),
    )

    assert max(map(len, hashed_chunks)) <= 4
    assert b"".join(hashed_chunks) == value.encode("utf-8")
    assert result == sanitizer_module.SanitizedOutput(
        text=value,
        byte_length=len(value.encode("utf-8")),
        sha256=original_sha256(value.encode("utf-8")).hexdigest(),
        credential_replacement_count=0,
    )


def test_invalid_blank_subclass_or_non_utf8_output_fails_content_free() -> None:
    class StringSubclass(str):
        pass

    invalid_values: tuple[object, ...] = (
        "",
        " \t\n",
        StringSubclass("answer"),
        "\ud800",
        123,
    )

    for value in invalid_values:
        with pytest.raises(SanitizerError) as caught:
            sanitizer_module.sanitize_output(value, patterns=_patterns())

        assert caught.value.code == "invalid_output"
        assert str(caught.value) == "output sanitization failed"


@pytest.mark.parametrize(
    "field_name",
    ("response_model", "request_id", "finish_reason", "error_kind"),
)
def test_provider_metadata_exact_one_kib_boundary_for_every_controlled_field(
    field_name: str,
) -> None:
    limit = RESOURCE_LIMITS_V1.bounded_string_bytes
    repeated = field_name * ((limit // len(field_name)) + 1)
    safe_value = repeated[:limit]

    assert len(safe_value.encode("utf-8")) == limit
    assert sanitizer_module.provider_metadata_is_safe(safe_value, patterns=_patterns()) is True
    assert (
        sanitizer_module.require_safe_provider_metadata(
            safe_value,
            patterns=_patterns(),
        )
        is safe_value
    )
    assert (
        sanitizer_module.provider_metadata_is_safe(
            safe_value + "x",
            patterns=_patterns(),
        )
        is False
    )


def test_provider_metadata_accepts_null_and_rejects_invalid_values_content_free() -> None:
    class StringSubclass(str):
        pass

    assert sanitizer_module.provider_metadata_is_safe(None, patterns=_patterns()) is True
    assert sanitizer_module.require_safe_provider_metadata(None, patterns=_patterns()) is None

    invalid_values: tuple[object, ...] = (
        "",
        " \t\n",
        123,
        StringSubclass("safe"),
        "\ud800",
        "before\x00after",
        "before\tafter",
        "before\u0085after",
    )
    for value in invalid_values:
        assert sanitizer_module.provider_metadata_is_safe(value, patterns=_patterns()) is False
        with pytest.raises(SanitizerError) as caught:
            sanitizer_module.require_safe_provider_metadata(value, patterns=_patterns())

        assert caught.value.code == "unsafe_provider_metadata"
        assert str(caught.value) == "unsafe_provider_metadata"


def test_provider_metadata_rejects_oversized_before_whitespace_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = " " * (RESOURCE_LIMITS_V1.bounded_string_bytes + 1)

    def fail_if_scanned(iterable: object) -> bool:
        del iterable
        raise AssertionError("oversized metadata must be rejected before iteration")

    with monkeypatch.context() as bounded_patch:
        bounded_patch.setattr(builtins, "any", fail_if_scanned)
        result = sanitizer_module.provider_metadata_is_safe(
            oversized,
            patterns=_patterns(),
        )

    assert result is False


def test_provider_metadata_rejects_credentials_paths_and_macos_aliases() -> None:
    patterns = _patterns(
        credential_values=("secret-token",),
        capsule_roots=("/capsule",),
        input_roots=(
            "/var/folders/ab/work/input",
            "/private/var/folders/ab/work/input",
        ),
    )

    for value in (
        "prefixsecret-tokensuffix",
        "/capsule",
        "/capsule/file",
        "/var/folders/ab/work/input/cases",
        "/private/var/folders/ab/work/input/cases",
    ):
        assert sanitizer_module.provider_metadata_is_safe(value, patterns=patterns) is False

    assert sanitizer_module.provider_metadata_is_safe("/capsule-other", patterns=patterns) is True


def test_provider_metadata_rejects_ascii_case_insensitive_url_authority() -> None:
    for value in (
        "HTTPS://user:secret@HOST:443/path",
        "prefix hTtP://host?q=1 suffix",
        "https://host",
    ):
        assert sanitizer_module.provider_metadata_is_safe(value, patterns=_patterns()) is False

    assert (
        sanitizer_module.provider_metadata_is_safe(
            "literal https token without authority",
            patterns=_patterns(),
        )
        is True
    )


@pytest.mark.parametrize(
    "value",
    (
        "BUILD.EXAMPLE.TEST",
        "(build)",
        "/Alice/",
        "éAliceé",
    ),
)
def test_provider_metadata_rejects_boundary_delimited_local_identities(value: str) -> None:
    patterns = _patterns(
        local_fqdns=("Build.Example.Test",),
        local_hostnames=("Build",),
        local_usernames=("Alice",),
    )

    assert sanitizer_module.provider_metadata_is_safe(value, patterns=patterns) is False


@pytest.mark.parametrize(
    ("patterns", "value"),
    (
        (_patterns(local_fqdns=("Build.Example.Test",)), "xBUILD.EXAMPLE.TEST"),
        (_patterns(local_fqdns=("Build.Example.Test",)), "BUILD.EXAMPLE.TEST9"),
        (_patterns(local_hostnames=("Build",)), "xbuild9"),
        (_patterns(local_usernames=("Alice",)), "xAlice9"),
        (_patterns(local_usernames=("Alice",)), "alice"),
    ),
)
def test_provider_metadata_allows_ascii_alphanumeric_local_identity_embedding(
    patterns: SanitizerPatterns,
    value: str,
) -> None:
    assert sanitizer_module.provider_metadata_is_safe(value, patterns=patterns) is True


def test_provider_metadata_matcher_does_not_rescan_replacement_tokens() -> None:
    patterns = _patterns(
        credential_values=("[HOST]",),
        local_hostnames=("build",),
    )

    assert sanitizer_module.provider_metadata_is_safe("xbuild9", patterns=patterns) is True
    assert (
        sanitizer_module.provider_metadata_is_safe("literal [REDACTED]", patterns=patterns) is True
    )


@pytest.mark.parametrize(
    ("patterns", "value"),
    (
        (
            _patterns(
                credential_values=("secret",),
                local_hostnames=("buildsecret",),
            ),
            "xbuildsecret9",
        ),
        (
            _patterns(
                capsule_roots=("/secret",),
                local_hostnames=("build/secret/path",),
            ),
            "xbuild/secret/path9",
        ),
        (
            _patterns(
                local_hostnames=("build-secret",),
                local_usernames=("build",),
            ),
            "build-secret9",
        ),
    ),
)
def test_provider_metadata_checks_each_pattern_without_longer_local_shielding(
    patterns: SanitizerPatterns,
    value: str,
) -> None:
    assert sanitizer_module.provider_metadata_is_safe(value, patterns=patterns) is False


def test_provider_metadata_multibyte_boundaries_and_byte_limit_are_exact() -> None:
    exact_limit = "é" * (RESOURCE_LIMITS_V1.bounded_string_bytes // 2)
    patterns = _patterns(local_usernames=("é",))

    assert len(exact_limit.encode("utf-8")) == RESOURCE_LIMITS_V1.bounded_string_bytes
    assert (
        sanitizer_module.provider_metadata_is_safe(exact_limit + "a", patterns=_patterns()) is False
    )
    assert sanitizer_module.provider_metadata_is_safe("aé9", patterns=patterns) is True
    assert sanitizer_module.provider_metadata_is_safe("€é€", patterns=patterns) is False


def test_require_safe_provider_metadata_returns_safe_value_without_rewriting() -> None:
    value = "returned-model-v1"

    result = sanitizer_module.require_safe_provider_metadata(value, patterns=_patterns())

    assert result is value


def test_compiled_patterns_are_globally_deduplicated_after_priority() -> None:
    compiled = sanitizer_module._compiled_patterns(  # type: ignore[attr-defined]
        _patterns(
            credential_values=("same",),
            capsule_roots=("same",),
            local_hostnames=("same",),
        )
    )
    matching = [pattern for pattern in compiled if pattern.value == b"same"]

    assert len(matching) == 1
    assert matching[0].replacement == b"[REDACTED]"
    assert matching[0].credential is True


@pytest.mark.parametrize("value", (123, "\ud800", "", " \t\n", "\x00\t\u0085"))
def test_diagnostic_constant_fallback_is_content_free(value: object) -> None:
    result = sanitizer_module.sanitize_diagnostic_or_constant(value, patterns=_patterns())

    assert result == SanitizedDiagnostic(
        text="diagnostic sanitization failed",
        credential_replacement_count=0,
    )


def test_diagnostic_constant_wrapper_delegates_valid_nonblank_bytes_exactly() -> None:
    patterns = _patterns(
        credential_values=("secret",),
        source_roots=("/workspace",),
    )
    value = " failed for secret at /workspace/file\x00 "

    assert sanitizer_module.sanitize_diagnostic_or_constant(
        value,
        patterns=patterns,
    ) == sanitize_diagnostic(value, patterns=patterns)


def test_diagnostic_constant_fallback_checks_blankness_before_truncation() -> None:
    result = sanitizer_module.sanitize_diagnostic_or_constant(
        "\u00a0" * 3000,
        patterns=_patterns(),
    )

    assert result == SanitizedDiagnostic(
        text="diagnostic sanitization failed",
        credential_replacement_count=0,
    )
