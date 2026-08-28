from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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
