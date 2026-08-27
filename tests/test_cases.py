from pathlib import Path
from textwrap import dedent

import pytest

from laconian_eval.capsule.limits import ResourceLimitError
from laconian_eval.cases import (
    finalize_response_cases,
    load_activation_cases,
    load_manifest,
    load_response_cases,
    parse_response_case_bytes,
    response_case_sha256,
)
from laconian_eval.models import ActivationCase, ResponseCase, RunManifest


def write_yaml(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")


def test_duplicate_case_ids_across_files_are_rejected_with_source_paths(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    content = """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
    """
    write_yaml(first, content)
    write_yaml(second, content)

    with pytest.raises(ValueError, match="duplicate case id") as exc_info:
        load_response_cases([first, second])

    message = str(exc_info.value)
    assert str(first) in message
    assert str(second) in message


def test_duplicate_top_level_yaml_key_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-kind.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: activation
        kind: response
        cases: []
        """,
    )

    with pytest.raises(ValueError, match="duplicate mapping key") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_duplicate_nested_yaml_key_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-prompt.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: This value must not be silently overwritten.
            prompt: Answer briefly.
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )

    with pytest.raises(ValueError, match="duplicate mapping key") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_duplicate_case_id_within_one_file_is_rejected_with_source_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate-id.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Give a short answer.
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )

    with pytest.raises(ValueError, match="duplicate case id") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_duplicate_scenario_locale_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-locale.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
          - id: direct-alternate-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Give a short answer.
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )

    with pytest.raises(ValueError, match="exactly one en and one ru") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_response_scenario_missing_locale_mate_is_rejected_with_source_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
        """,
    )

    with pytest.raises(ValueError, match="exactly one en and one ru") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_activation_scenario_missing_locale_mate_is_rejected_with_source_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "activation.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: activation
        cases:
          - id: activation-explicit-en
            scenario_id: activation-explicit
            locale: en
            prompt: /if Explain retries.
            expected_activation: true
            rationale: The explicit trigger should activate the skill.
        """,
    )

    with pytest.raises(ValueError, match="exactly one en and one ru") as exc_info:
        load_activation_cases([path])

    assert str(path) in str(exc_info.value)


def test_invalid_top_level_kind_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "wrong-kind.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: activation
        cases: []
        """,
    )

    with pytest.raises(ValueError, match="kind") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_non_mapping_yaml_root_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "list-root.yaml"
    write_yaml(
        path,
        """
        - schema_version
        - kind
        - cases
        """,
    )

    with pytest.raises(ValueError, match="mapping") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_malformed_yaml_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases: [
        """,
    )

    with pytest.raises(ValueError) as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_empty_yaml_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_missing_required_top_level_key_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "missing-cases.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        """,
    )

    with pytest.raises(ValueError, match="cases") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_whitespace_prompt_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "blank-prompt.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: "   "
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )

    with pytest.raises(ValueError, match="prompt") as exc_info:
        load_response_cases([path])

    assert str(path) in str(exc_info.value)


def test_valid_bilingual_response_file_loads_in_source_order(tmp_path: Path) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
        """,
    )

    cases = load_response_cases([path])

    assert isinstance(cases, tuple)
    assert all(isinstance(case, ResponseCase) for case in cases)
    assert tuple(case.id for case in cases) == ("direct-001-ru", "direct-001-en")


def test_valid_bilingual_response_pair_split_across_files_preserves_input_order(
    tmp_path: Path,
) -> None:
    english = tmp_path / "english.yaml"
    russian = tmp_path / "russian.yaml"
    write_yaml(
        english,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
        """,
    )
    write_yaml(
        russian,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )

    cases = load_response_cases([english, russian])

    assert tuple(case.id for case in cases) == ("direct-001-en", "direct-001-ru")


def test_valid_bilingual_activation_file_loads_in_source_order(tmp_path: Path) -> None:
    path = tmp_path / "activation.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: activation
        cases:
          - id: activation-explicit-en
            scenario_id: activation-explicit
            locale: en
            prompt: /if Explain retries.
            expected_activation: true
            rationale: The explicit trigger should activate the skill.
          - id: activation-explicit-ru
            scenario_id: activation-explicit
            locale: ru
            prompt: /if Объясни повторы.
            expected_activation: true
            rationale: Явный триггер должен активировать навык.
        """,
    )

    cases = load_activation_cases([path])

    assert isinstance(cases, tuple)
    assert all(isinstance(case, ActivationCase) for case in cases)
    assert tuple(case.id for case in cases) == (
        "activation-explicit-en",
        "activation-explicit-ru",
    )


def test_valid_manifest_loads(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        runner_version: 0.1.0.dev0
        run_name: smoke
        provider:
          kind: fake
          model: fake-v1
        case_files:
          - evals/cases/response-smoke.yaml
        arms:
          - baseline
          - if
        """,
    )

    manifest = load_manifest(path)

    assert isinstance(manifest, RunManifest)
    assert manifest.run_name == "smoke"
    assert manifest.arms == ("baseline", "if")


def test_invalid_manifest_is_rejected_with_source_path(tmp_path: Path) -> None:
    path = tmp_path / "invalid-manifest.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        runner_version: 0.1.0.dev0
        run_name: smoke
        provider:
          kind: fake
          model: fake-v1
        case_files:
          - evals/cases/response-smoke.yaml
        arms:
          - baseline
          - baseline
        """,
    )

    with pytest.raises(ValueError, match="arms must be unique") as exc_info:
        load_manifest(path)

    assert str(path) in str(exc_info.value)


def test_response_case_bytes_parse_before_cross_file_finalization(tmp_path: Path) -> None:
    english_path = tmp_path / "english.yaml"
    russian_path = tmp_path / "russian.yaml"
    english = (
        dedent(
            """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
        """
        )
        .strip()
        .encode()
        + b"\n"
    )
    russian = (
        dedent(
            """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """
        )
        .strip()
        .encode()
        + b"\n"
    )

    english_cases = parse_response_case_bytes(english, source=english_path)
    russian_cases = parse_response_case_bytes(russian, source=russian_path)
    cases = finalize_response_cases(
        [(english_cases[0], english_path), (russian_cases[0], russian_path)]
    )

    assert tuple(case.id for case in cases) == ("direct-001-en", "direct-001-ru")


def test_response_case_path_loader_uses_one_captured_buffer_for_validation_and_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        """
        schema_version: "1"
        kind: response
        cases:
          - id: direct-001-en
            scenario_id: direct-001
            locale: en
            category: direct
            prompt: Answer briefly.
          - id: direct-001-ru
            scenario_id: direct-001
            locale: ru
            category: direct
            prompt: Ответь кратко.
        """,
    )
    from laconian_eval import cases as cases_module

    real_capture = cases_module.read_regular_file_once
    captures = 0

    def capture_then_poison(
        directory_fd: int,
        source_path: str,
        *,
        limit: int,
        code: str,
    ) -> bytes:
        nonlocal captures
        captures += 1
        if captures > 1:
            raise AssertionError("source path reopened after capture")
        captured = real_capture(
            directory_fd,
            source_path,
            limit=limit,
            code=code,
        )
        path.write_bytes(b"not valid YAML anymore\n")
        return captured

    monkeypatch.setattr(cases_module, "read_regular_file_once", capture_then_poison)

    parsed = load_response_cases([path])

    assert captures == 1
    assert tuple(case.id for case in parsed) == ("direct-001-en", "direct-001-ru")
    assert response_case_sha256(parsed[0]) == response_case_sha256(
        parse_response_case_bytes(
            dedent(
                """
                schema_version: "1"
                kind: response
                cases:
                  - id: direct-001-en
                    scenario_id: direct-001
                    locale: en
                    category: direct
                    prompt: Answer briefly.
                """
            )
            .strip()
            .encode()
            + b"\n",
            source=path,
        )[0]
    )


@pytest.mark.parametrize(
    "document",
    [
        "value: &shared secret\ncopy: plain\n",
        "value: &shared secret\ncopy: *shared\n",
        "base: {prompt: secret}\ncase: {<<: {prompt: overwritten}}\n",
    ],
)
def test_case_path_loader_rejects_yaml_references_and_merge_keys(
    tmp_path: Path, document: str
) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        load_response_cases([path])

    assert str(path) in str(caught.value)
    assert "secret" not in str(caught.value)


def test_response_case_bytes_preserve_stable_resource_limit_code(tmp_path: Path) -> None:
    document = b"[" * 65 + b"secret" + b"]" * 65

    with pytest.raises(ResourceLimitError) as caught:
        parse_response_case_bytes(document, source=tmp_path / "deep.yaml")

    assert caught.value.code == "nesting_depth_limit"
    assert "secret" not in str(caught.value)
