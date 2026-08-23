from collections import defaultdict
from pathlib import Path

from laconian_eval.cases import load_activation_cases, load_manifest, load_response_cases
from laconian_eval.models import ResponseCase

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
        (scenario_id, case.category)
        for scenario_id, cases in grouped.items()
        for case in cases
    } == set(RESPONSE_MATRIX.items())

    for scenario_id, cases in grouped.items():
        assert {case.locale for case in cases} == {"en", "ru"}
        assert {case.id for case in cases} == {
            f"{scenario_id}-en",
            f"{scenario_id}-ru",
        }
        assert {case.category for case in cases} == {RESPONSE_MATRIX[scenario_id]}
        assert cases[0].hard_constraints == cases[1].hard_constraints
        for case in cases:
            assert all(
                required_literal in case.prompt
                for required_literal in case.hard_constraints.required_literals
            )


def test_response_smoke_has_exact_hard_constraint_profiles() -> None:
    grouped = _response_cases_by_scenario()

    expected_max_sentences = {
        "direct-idempotency": 2,
        "coding-post-retry": 2,
        "preserve-config": 3,
        "uncertain-attribution": 3,
        "safety-medical": 4,
        "safety-financial": 3,
    }
    for scenario_id, max_sentences in expected_max_sentences.items():
        assert {
            case.hard_constraints.max_sentences for case in grouped[scenario_id]
        } == {max_sentences}

    for case in grouped["user-decline"]:
        assert case.hard_constraints.min_sentences == 2
        assert case.hard_constraints.max_sentences == 2

    for case in grouped["structured-json"]:
        assert case.hard_constraints.required_json_keys == (
            "risk",
            "mitigation",
            "confidence",
        )

    expected_literals = {
        "coding-post-retry": ("POST",),
        "preserve-config": ("v2.4.1", "8080", "https://api.example.com/v1"),
        "preserve-command": ("git push --force-with-lease",),
        "coding-if-keyword": ("should_retry",),
        "structured-yaml": ("status", "reason", "next_step"),
    }
    for scenario_id, required_literals in expected_literals.items():
        assert {
            case.hard_constraints.required_literals for case in grouped[scenario_id]
        } == {required_literals}


def test_response_smoke_rubrics_cover_required_semantics() -> None:
    grouped = _response_cases_by_scenario()

    expected_fact_counts = {
        "direct-idempotency": 2,
        "coding-post-retry": 2,
        "coding-if-keyword": 1,
        "structured-json": 2,
        "structured-yaml": 2,
        "uncertain-attribution": 2,
        "safety-medical": 2,
        "safety-financial": 2,
        "user-decline": 2,
        "summary-ordered": 3,
    }
    for scenario_id, fact_count in expected_fact_counts.items():
        assert {
            len(case.semantic_rubric.required_facts) for case in grouped[scenario_id]
        } == {fact_count}

    assert all(
        case.semantic_rubric.material_warning
        for case in grouped["preserve-command"]
    )

    expected_summary_rubrics = {
        "en": (
            "Launch the beta on October 15.",
            "Keep the API on v1.",
            "Train support before launch.",
        ),
        "ru": (
            "Запустить бета-версию 15 октября.",
            "Оставить API на версии v1.",
            "Обучить службу поддержки до запуска.",
        ),
    }
    for case in grouped["summary-ordered"]:
        assert case.semantic_rubric.required_facts == expected_summary_rubrics[case.locale]


def test_activation_smoke_has_four_bilingual_scenarios() -> None:
    cases = load_activation_cases([ROOT / "evals/cases/activation-smoke.yaml"])
    assert len(cases) == 8
    assert len({case.scenario_id for case in cases}) == 4
    expected = {
        case.scenario_id: case.expected_activation
        for case in cases
        if case.locale == "en"
    }
    assert expected == {
        "activation-explicit": True,
        "activation-concise": True,
        "activation-code-if": False,
        "activation-detailed": False,
    }


def test_activation_smoke_pairs_agree_and_have_rationales() -> None:
    cases = load_activation_cases([ACTIVATION_CASES])
    grouped: defaultdict[str, list[tuple[str, bool, str]]] = defaultdict(list)
    for case in cases:
        grouped[case.scenario_id].append(
            (case.locale, case.expected_activation, case.rationale)
        )

    assert set(grouped) == {
        "activation-explicit",
        "activation-concise",
        "activation-code-if",
        "activation-detailed",
    }
    for localized_cases in grouped.values():
        assert {locale for locale, _, _ in localized_cases} == {"en", "ru"}
        assert len({expected for _, expected, _ in localized_cases}) == 1
        assert all(rationale.strip() for _, _, rationale in localized_cases)


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
