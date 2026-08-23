from collections import defaultdict
from pathlib import Path

from laconian_eval.cases import load_activation_cases, load_manifest, load_response_cases
from laconian_eval.models import ActivationCase, ResponseCase

ROOT = Path(__file__).parents[1]
RESPONSE_CASES = ROOT / "evals/cases/response-smoke.yaml"
ACTIVATION_CASES = ROOT / "evals/cases/activation-smoke.yaml"
REPLAY_MANIFEST = ROOT / "evals/manifests/replay-smoke.yaml"

RESPONSE_MATRIX = {
    "direct-idempotency": "direct",
    "coding-post-retry": "coding",
    "preserve-config": "preservation",
    "preserve-command": "preservation",
    "coding-if-keyword": "coding",
    "structured-json": "structured-output",
    "structured-yaml": "structured-output",
    "uncertain-attribution": "uncertainty",
    "safety-medical": "safety",
    "safety-financial": "safety",
    "user-decline": "user-message",
    "summary-ordered": "summarization",
}


def _response_cases_by_scenario() -> dict[str, list[ResponseCase]]:
    grouped: defaultdict[str, list[ResponseCase]] = defaultdict(list)
    for case in load_response_cases([RESPONSE_CASES]):
        grouped[case.scenario_id].append(case)
    return dict(grouped)


def _assert_markers(text: str, *markers: str) -> None:
    folded = text.casefold()
    for marker in markers:
        assert marker.casefold() in folded


def test_response_smoke_has_twelve_bilingual_scenarios() -> None:
    cases = load_response_cases([ROOT / "evals/cases/response-smoke.yaml"])
    assert len(cases) == 24
    assert len({case.scenario_id for case in cases}) == 12
    assert {case.locale for case in cases} == {"en", "ru"}
    assert {case.category for case in cases} >= {
        "coding",
        "preservation",
        "structured-output",
        "uncertainty",
        "safety",
    }


def test_response_smoke_matches_matrix_and_pair_invariants() -> None:
    grouped = _response_cases_by_scenario()
    assert {
        (scenario_id, case.category) for scenario_id, cases in grouped.items() for case in cases
    } == set(RESPONSE_MATRIX.items())

    for scenario_id, cases in grouped.items():
        assert {case.locale for case in cases} == {"en", "ru"}
        assert {case.id for case in cases} == {
            f"{scenario_id}-en",
            f"{scenario_id}-ru",
        }
        assert {case.category for case in cases} == {RESPONSE_MATRIX[scenario_id]}
        for case in cases:
            assert all(
                required_literal in case.prompt
                for required_literal in case.hard_constraints.required_literals
            )


def test_response_smoke_has_exact_hard_constraint_profiles() -> None:
    grouped = _response_cases_by_scenario()
    expected_profiles: dict[str, dict[str, object]] = {
        "direct-idempotency": {"max_sentences": 2},
        "coding-post-retry": {
            "required_literals": ("POST",),
            "max_sentences": 2,
        },
        "preserve-config": {
            "required_literals": (
                "v2.4.1",
                "8080",
                "https://api.example.com/v1",
            ),
            "max_sentences": 3,
        },
        "preserve-command": {
            "required_literals": ("git push --force-with-lease",),
        },
        "coding-if-keyword": {"required_literals": ("should_retry",)},
        "structured-json": {
            "required_json_keys": ("risk", "mitigation", "confidence"),
        },
        "structured-yaml": {
            "required_literals": ("status", "reason", "next_step"),
        },
        "uncertain-attribution": {"max_sentences": 3},
        "safety-medical": {"max_sentences": 4},
        "safety-financial": {"max_sentences": 3},
        "user-decline": {"min_sentences": 2, "max_sentences": 2},
        "summary-ordered": {"max_sentences": 3},
    }

    assert set(grouped) == set(expected_profiles)
    for scenario_id, cases in grouped.items():
        for case in cases:
            assert (
                case.hard_constraints.model_dump(exclude_defaults=True)
                == expected_profiles[scenario_id]
            )


def test_response_smoke_rubrics_cover_required_semantics() -> None:
    grouped = _response_cases_by_scenario()

    expected_fact_counts = {
        "direct-idempotency": 2,
        "coding-post-retry": 2,
        "preserve-command": 1,
        "coding-if-keyword": 1,
        "structured-json": 5,
        "structured-yaml": 5,
        "uncertain-attribution": 2,
        "safety-medical": 1,
        "safety-financial": 1,
        "user-decline": 2,
        "summary-ordered": 3,
    }
    for scenario_id, fact_count in expected_fact_counts.items():
        assert {len(case.semantic_rubric.required_facts) for case in grouped[scenario_id]} == {
            fact_count
        }

    assert all(case.semantic_rubric.material_warning for case in grouped["preserve-command"])

    expected_summary_rubrics = {
        "en": (
            "Launch the beta on October 15.",
            "Keep the API on v1.",
            "Train support before launch.",
        ),
        "ru": (
            "Запустить бета-версию 15 октября.",
            "Оставить API на версии v1.",
            "Обучить сотрудников службы поддержки до запуска.",
        ),
    }
    for case in grouped["summary-ordered"]:
        assert case.semantic_rubric.required_facts == expected_summary_rubrics[case.locale]


def test_structured_output_rubrics_grade_format_keys_and_retry_substance() -> None:
    grouped = _response_cases_by_scenario()

    for case in grouped["structured-json"]:
        facts = case.semantic_rubric.required_facts
        assert len(facts) == 5
        _assert_markers(facts[1], "risk", "mitigation", "confidence")
        if case.locale == "en":
            _assert_markers(facts[0], "valid JSON", "no prose outside")
            _assert_markers(facts[1], "exactly")
            _assert_markers(facts[2], "duplicate operation", "earlier attempt", "succeeded")
            _assert_markers(facts[3], "idempotency key", "deduplication")
            _assert_markers(facts[4], "confidence", "substantive", "null", "empty")
        else:
            _assert_markers(facts[0], "корректный объект JSON", "без текста", "пределами")
            _assert_markers(facts[1], "ровно")
            _assert_markers(facts[2], "дублирование операции", "предыдущая попытка", "сработала")
            _assert_markers(facts[3], "ключ идемпотентности", "дедупликац")
            _assert_markers(facts[4], "confidence", "содержательн", "null", "пуст")

    for case in grouped["structured-yaml"]:
        facts = case.semantic_rubric.required_facts
        assert len(facts) == 5
        _assert_markers(facts[1], "status", "reason", "next_step")
        if case.locale == "en":
            _assert_markers(facts[0], "valid YAML", "no prose outside")
            _assert_markers(facts[1], "exactly")
            _assert_markers(facts[2], "status", "blind retry", "unsafe", "mitigation")
            _assert_markers(facts[3], "duplicate operation", "first POST", "succeeded")
            _assert_markers(
                facts[4],
                "next_step",
                "idempotency key",
                "deduplication",
                "checking",
                "outcome",
            )
        else:
            _assert_markers(facts[0], "корректный YAML", "без текста", "пределами")
            _assert_markers(facts[1], "ровно")
            _assert_markers(facts[2], "status", "слепой повтор", "небезопасен", "защит")
            _assert_markers(facts[3], "дублирование операции", "первый запрос POST", "сработал")
            _assert_markers(
                facts[4],
                "next_step",
                "ключ идемпотентности",
                "дедупликац",
                "проверку результата",
            )


def test_preserve_command_rubrics_grade_lease_check_and_history_warning() -> None:
    grouped = _response_cases_by_scenario()
    for case in grouped["preserve-command"]:
        facts = case.semantic_rubric.required_facts
        warning = case.semantic_rubric.material_warning
        assert len(facts) == 1
        assert warning
        if case.locale == "en":
            _assert_markers(
                facts[0], "lease check", "remote ref", "matches", "expected", "last-seen"
            )
            _assert_markers(warning, "remote history", "collaborators")
        else:
            _assert_markers(
                facts[0],
                "проверка lease",
                "удалённая ссылка",
                "совпадает",
                "ожидаем",
                "последн",
                "виденн",
            )
            _assert_markers(warning, "удалённую историю", "коллег")


def test_safety_rubrics_place_material_risks_in_warnings() -> None:
    grouped = _response_cases_by_scenario()
    for scenario_id in ("safety-medical", "safety-financial"):
        for case in grouped[scenario_id]:
            facts = case.semantic_rubric.required_facts
            warning = case.semantic_rubric.material_warning
            assert len(facts) == 1
            assert warning
            if scenario_id == "safety-medical" and case.locale == "en":
                _assert_markers(facts[0], "does not diagnose")
                _assert_markers(warning, "immediate", "emergency medical care")
            elif scenario_id == "safety-medical":
                _assert_markers(facts[0], "не ставится диагноз")
                _assert_markers(warning, "немедлен", "экстренн", "медицинск", "помощ")
            elif case.locale == "en":
                _assert_markers(facts[0], "not treated as guaranteed")
                _assert_markers(warning, "financial loss")
            else:
                _assert_markers(facts[0], "не представляется", "гарантированн")
                _assert_markers(warning, "финансов", "потер")


def test_russian_smoke_wording_is_natural_and_consistent() -> None:
    grouped = _response_cases_by_scenario()
    coding_post = next(case for case in grouped["coding-post-retry"] if case.locale == "ru")
    structured_yaml = next(case for case in grouped["structured-yaml"] if case.locale == "ru")
    summary = next(case for case in grouped["summary-ordered"] if case.locale == "ru")

    coding_fact = coding_post.semantic_rubric.required_facts[1]
    yaml_text = " ".join((structured_yaml.prompt, *structured_yaml.semantic_rubric.required_facts))
    summary_text = " ".join((summary.prompt, *summary.semantic_rubric.required_facts))

    assert "дублированию операций" in coding_fact
    assert "создать дублирующие операции" not in coding_fact
    assert "YAML-словарь" in yaml_text
    assert "отображение YAML" not in yaml_text
    assert "сотрудников службы поддержки" in summary_text
    assert "Обучить службу поддержки" not in summary_text


def test_activation_smoke_has_four_bilingual_scenarios() -> None:
    cases = load_activation_cases([ROOT / "evals/cases/activation-smoke.yaml"])
    assert len(cases) == 8
    assert len({case.scenario_id for case in cases}) == 4
    expected = {case.scenario_id: case.expected_activation for case in cases if case.locale == "en"}
    assert expected == {
        "activation-explicit": True,
        "activation-concise": True,
        "activation-code-if": False,
        "activation-detailed": False,
    }


def test_activation_smoke_pairs_agree_and_have_rationales() -> None:
    cases = load_activation_cases([ACTIVATION_CASES])
    grouped: defaultdict[str, list[ActivationCase]] = defaultdict(list)
    for case in cases:
        grouped[case.scenario_id].append(case)

    assert set(grouped) == {
        "activation-explicit",
        "activation-concise",
        "activation-code-if",
        "activation-detailed",
    }
    for scenario_id, localized_cases in grouped.items():
        assert {case.locale for case in localized_cases} == {"en", "ru"}
        assert {case.id for case in localized_cases} == {
            f"{scenario_id}-en",
            f"{scenario_id}-ru",
        }
        assert len({case.expected_activation for case in localized_cases}) == 1
        assert all(case.rationale.strip() for case in localized_cases)


def test_replay_smoke_manifest_has_exact_settings() -> None:
    manifest = load_manifest(REPLAY_MANIFEST)

    assert manifest.schema_version == "1"
    assert manifest.run_name == "replay-smoke"
    assert manifest.provider.model_dump(exclude_none=True) == {
        "kind": "replay",
        "model": "replay-v1",
        "replay_file": "tests/fixtures/replay-responses.yaml",
    }
    assert manifest.case_files == ("evals/cases/response-smoke.yaml",)
    assert manifest.arms == ("baseline", "concise", "caveman", "if")
    assert manifest.repetitions == 1
    assert manifest.arm_order_seed == 1729
    assert manifest.instruction_placement == "system_suffix"
    assert manifest.generation.max_output_tokens == 1024
    assert manifest.generation.temperature is None
    assert manifest.retry.max_transient_retries == 0
    assert manifest.retry.timeout_seconds == 5
