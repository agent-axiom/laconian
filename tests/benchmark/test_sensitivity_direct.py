"""Task 11 exact calculation contracts; synthetic inputs are not verified evidence."""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
from typing import Any, Literal

import numpy as np
import pytest
from pydantic import ValidationError

import laconian_eval.benchmark as benchmark_package
import laconian_eval.benchmark.sensitivity as sensitivity
from laconian_eval.benchmark.aggregation import (
    _build_aggregated_model_from_rows,
    median_visible_delta,
    paired_pass_rate_difference,
)
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.audit_metrics import ModelAuditMetricsV1
from laconian_eval.benchmark.sensitivity import (
    FalseFailCandidateV1,
    FalseFailLimitV1,
    SensitivityExtremumV1,
    SensitivityResultV1,
    derive_false_fail_limit,
    enumerate_sensitivity_exact,
)
from laconian_eval.capsule.canonical import stable_digest
from tests.benchmark.helpers import compact_sensitivity_aggregate, compact_sensitivity_vectors
from tests.benchmark.test_audit_metrics import _fixture, _Spec

IF_ID = "response-00-en-0-if"
CONCISE_ID = "response-11-ru-4-concise"
METRIC_DIGEST = "7" * 64
# Independent oracle: explicit block expansion, Fraction arithmetic, hashlib + JSON.
ASSIGNMENT_HASHES = (
    "c93fa489827d70aec556dc1cc71897e3e98b026ccd3eb5a3ecdc44e739e683c3",
    "deccb87a6566b4dae69c3c7dee5f3050553ad28451c75d02184f9bb930aaeaae",
    "63bfc96e68de9e59b00a09af34d692358fa2f902312535708a3dce7114aca062",
    "a502aaa8bd9fd7711dcf9f6447cfa8a9c036c3713c8d107170a9bf1ed94054f9",
)
ASSIGNMENT_ENDPOINTS = (
    (-0.1, 0.1, -5.0, 5.0),
    (-0.1, 0.0, -5.0, 5.5),
    (0.0, 0.1, -5.5, 5.0),
    (0.0, 0.0, -5.5, 5.5),
)


def _candidate(row: Any, *, known: bool = False) -> FalseFailCandidateV1:
    return FalseFailCandidateV1(
        response_id=row.response_id,
        generation_model=row.generation_model,
        arm=row.arm,
        scenario_uid=row.scenario_uid,
        planned_key=canonical_json_v1(
            {
                "scenario_uid": row.scenario_uid,
                "case_id": row.case_id,
                "locale": row.locale,
                "repetition": row.repetition,
            }
        ).decode("utf-8"),
        known_false_fail=known,
    )


def _candidates(aggregate: Any) -> tuple[FalseFailCandidateV1, ...]:
    return tuple(
        _candidate(row)
        for row in aggregate.rows
        if row.arm in ("if", "concise") and row.hard_pass and not row.semantic_success
    )


def _limit(arm: Literal["if", "concise"], **updates: Any) -> FalseFailLimitV1:
    return FalseFailLimitV1(
        **{
            "generation_model": "model-a",
            "arm": arm,
            "m_all_judge_fail": 1,
            "d_known_false_fail": 0,
            "optional_candidates": 1,
            "upper_false_fail": Decimal("0.75"),
            "model_audit_metric_sha256": METRIC_DIGEST,
            "k_max_reclassified": 1,
            "estimable": True,
            **updates,
        }
    )


def _metrics(*, unresolved: bool = False) -> ModelAuditMetricsV1:
    specs = tuple(
        spec
        for arm in ("if", "concise")
        for spec in (
            _Spec(judge=False, consensus=True, model="model-a", arm=arm, count=1, locale="ru"),
            _Spec(
                judge=False,
                consensus=None if unresolved else False,
                model="model-a",
                arm=arm,
                count=4,
            ),
            _Spec(judge=True, consensus=True, model="model-a", arm=arm, count=5),
        )
    )
    return _fixture(specs).metrics("model-a")


def _with_upper(metrics: ModelAuditMetricsV1, upper: str, **updates: Any) -> ModelAuditMetricsV1:
    payload = metrics.model_dump(mode="json", exclude={"model_audit_metric_sha256"})
    payload["false_fail_by_primary_arm"]["if"].update(upper=upper, **updates)
    payload["model_audit_metric_sha256"] = stable_digest("laconian-model-audit-metric-v1", payload)
    return ModelAuditMetricsV1.model_validate_json(canonical_json_v1(payload))


def _derive(metrics: ModelAuditMetricsV1, candidates: Any, arm: Any = "if") -> FalseFailLimitV1:
    return derive_false_fail_limit(model="model-a", arm=arm, candidates=candidates, metrics=metrics)


def _result(**updates: Any) -> SensitivityResultV1:
    return SensitivityResultV1(
        **{
            "generation_model": "model-a",
            "model_audit_metric_sha256": METRIC_DIGEST,
            "assignment_count": 4,
            "visited_nodes": 4,
            "evaluated_assignments": 4,
            "semantic_min_lower": None,
            "semantic_max_upper": None,
            "token_min_lower": None,
            "token_max_upper": None,
            "search_exhausted": False,
            "exhaustion_reason": None,
            "certificate_sha256": None,
            **updates,
        }
    )


def test_false_fail_limits_use_model_arm_m_d_u_and_closed_k_formula() -> None:
    aggregate = compact_sensitivity_aggregate()
    rows = tuple(row for row in aggregate.rows if row.arm == "if")[:10]
    candidates = (
        *(_candidate(row, known=i < 3) for i, row in enumerate(rows)),
        _candidates(aggregate)[1],
    )
    metrics = _with_upper(_metrics(), "0.25")
    limit = _derive(metrics, candidates)
    assert (
        limit.m_all_judge_fail,
        limit.d_known_false_fail,
        limit.optional_candidates,
        limit.k_max_reclassified,
    ) == (10, 3, 7, 3)
    assert limit.upper_false_fail == Decimal("0.25")
    assert _derive(_with_upper(metrics, "1"), candidates).k_max_reclassified == 10
    assert _derive(metrics, candidates, "concise").m_all_judge_fail == 1
    with pytest.raises(ValueError, match=r"duplicate.*planned"):
        _derive(
            metrics, (candidates[0], candidates[0].model_copy(update={"response_id": "second"}))
        )
    for update in (
        {"optional_candidates": 0},
        {"k_max_reclassified": 2},
        {"upper_false_fail": Decimal("1.01")},
        {"upper_false_fail": Decimal("NaN")},
        {"m_all_judge_fail": True},
        {"unexpected": True},
    ):
        with pytest.raises(ValidationError):
            FalseFailLimitV1.model_validate({**limit.model_dump(), **update})
    with pytest.raises(ValidationError):
        limit.arm = "concise"
    for owner in (
        FalseFailCandidateV1,
        FalseFailLimitV1,
        SensitivityExtremumV1,
        SensitivityResultV1,
    ):
        assert getattr(benchmark_package, owner.__name__) is owner
        assert owner.model_config["strict"] and owner.model_config["frozen"]
        assert owner.model_config["extra"] == "forbid"
    assert tuple(FalseFailCandidateV1.model_fields) == (
        "response_id",
        "generation_model",
        "arm",
        "scenario_uid",
        "planned_key",
        "known_false_fail",
    )
    assert tuple(FalseFailLimitV1.model_fields) == (
        "generation_model",
        "arm",
        "m_all_judge_fail",
        "d_known_false_fail",
        "optional_candidates",
        "upper_false_fail",
        "model_audit_metric_sha256",
        "k_max_reclassified",
        "estimable",
    )


def test_false_fail_limit_uses_authorizing_two_sided_design_weighted_wilson_upper() -> None:
    metrics = _metrics()
    candidates = _candidates(compact_sensitivity_aggregate())
    limit = _derive(metrics, candidates)
    assert limit.upper_false_fail == metrics.false_fail_by_primary_arm["if"].upper
    assert limit.upper_false_fail != metrics.false_fail_by_primary_arm["if"].point
    assert limit.model_audit_metric_sha256 == metrics.model_audit_metric_sha256
    for name, value in (
        ("authorization_use", "reported-only"),
        ("confidence_level", "one-sided-0.95"),
        ("interval_method", "binary-percentile"),
    ):
        proportion = metrics.false_fail_by_primary_arm["if"].model_copy(update={name: value})
        forged = metrics.model_copy(
            update={
                "false_fail_by_primary_arm": {**metrics.false_fail_by_primary_arm, "if": proportion}
            }
        )
        with pytest.raises((ValueError, TypeError)):
            _derive(forged, candidates)
    with pytest.raises(ValueError):
        derive_false_fail_limit(model="other", arm="if", candidates=candidates, metrics=metrics)
    with pytest.raises((ValueError, TypeError)):
        _derive(metrics.model_copy(update={"model_audit_metric_sha256": "0" * 64}), candidates)


def test_both_primary_arm_limits_require_the_same_model_audit_metric_digest() -> None:
    aggregate = compact_sensitivity_aggregate()
    candidates = _candidates(aggregate)
    metrics = _metrics()
    limits = (_derive(metrics, candidates), _derive(metrics, candidates, "concise"))
    result = enumerate_sensitivity_exact(
        aggregate=aggregate,
        limits=limits,
        candidates=candidates,
        vectors=compact_sensitivity_vectors(),
    )
    assert result.model_audit_metric_sha256 == metrics.model_audit_metric_sha256
    invalid = (
        limits[::-1],
        (limits[0], limits[1].model_copy(update={"model_audit_metric_sha256": "1" * 64})),
        (limits[0], limits[1].model_copy(update={"generation_model": "other"})),
        (limits[0], limits[1].model_copy(update={"model_audit_metric_sha256": ""})),
    )
    for bad_limits in invalid:
        with pytest.raises((ValueError, TypeError)):
            enumerate_sensitivity_exact(
                aggregate=aggregate,
                limits=bad_limits,
                candidates=candidates,
                vectors=compact_sensitivity_vectors(),
            )


def test_known_false_fails_are_forced_and_every_other_judge_fail_row_is_optional() -> None:
    aggregate = compact_sensitivity_aggregate()
    candidates = list(_candidates(aggregate))
    candidates[0] = candidates[0].model_copy(update={"known_false_fail": True})
    limits = (_limit("if", d_known_false_fail=1, optional_candidates=0), _limit("concise"))
    result = enumerate_sensitivity_exact(
        aggregate=aggregate,
        limits=limits,
        candidates=candidates,
        vectors=compact_sensitivity_vectors(),
    )
    assert result.assignment_count == result.evaluated_assignments == 2
    assert result.semantic_min_lower.value == 0.0
    assert list(sensitivity._assignment_choices(limits[0], candidates)) == [(IF_ID,)]
    # Includes audited consensus-fail rows: every non-forced judge-fail is optional.
    assert list(sensitivity._assignment_choices(limits[1], candidates)) == [(), (CONCISE_ID,)]
    for bad in (
        candidates[:1],
        [*candidates, candidates[0]],
        [candidates[0].model_copy(update={"planned_key": "wrong"}), candidates[1]],
        [candidates[0].model_copy(update={"scenario_uid": "f" * 64}), candidates[1]],
        [candidates[0].model_copy(update={"generation_model": "other"}), candidates[1]],
        [candidates[0].model_copy(update={"response_id": "not-a-failure"}), candidates[1]],
    ):
        with pytest.raises((ValueError, TypeError)):
            enumerate_sensitivity_exact(
                aggregate=aggregate,
                limits=limits,
                candidates=bad,
                vectors=compact_sensitivity_vectors(),
            )
    assert candidates[0].planned_key == (
        '{"case_id":"case-00-en","locale":"en","repetition":0,"scenario_uid":"' + "0" * 64 + '"}'
    )
    rows = list(aggregate.rows)
    rows[0] = rows[0].model_copy(update={"response_id": IF_ID})
    duplicate = _build_aggregated_model_from_rows(generation_model="model-a", rows=rows)
    with pytest.raises(ValueError, match=r"duplicate.*response"):
        enumerate_sensitivity_exact(
            aggregate=duplicate,
            limits=limits,
            candidates=candidates,
            vectors=compact_sensitivity_vectors(),
        )


def test_zero_judge_fail_rows_produce_k_zero_without_an_interval() -> None:
    metrics = _fixture(
        (
            _Spec(judge=True, consensus=True, model="model-a", arm="if"),
            _Spec(judge=True, consensus=True, model="model-a", arm="concise"),
        )
    ).metrics("model-a")
    assert not metrics.false_fail_by_primary_arm["if"].available
    limit = _derive(metrics, ())
    assert (
        limit.m_all_judge_fail,
        limit.d_known_false_fail,
        limit.optional_candidates,
        limit.k_max_reclassified,
        limit.upper_false_fail,
        limit.estimable,
    ) == (0, 0, 0, 0, None, True)


def test_unestimable_upper_bound_makes_model_sensitivity_inconclusive() -> None:
    aggregate = compact_sensitivity_aggregate()
    candidates = _candidates(aggregate)
    metrics = _metrics(unresolved=True)
    limits = (_derive(metrics, candidates), _derive(metrics, candidates, "concise"))
    assert not limits[0].estimable and not limits[1].estimable
    result = enumerate_sensitivity_exact(
        aggregate=aggregate,
        limits=limits,
        candidates=candidates,
        vectors=compact_sensitivity_vectors(),
    )
    assert result.evaluated_assignments == result.visited_nodes == 0
    assert result.assignment_count == 0
    assert all(
        getattr(result, name) is None
        for name in (
            "semantic_min_lower",
            "semantic_max_upper",
            "token_min_lower",
            "token_max_upper",
        )
    )
    assert result.search_exhausted is False and result.exhaustion_reason is None
    # An unresolved sampled consensus anywhere makes both model arm limits inconclusive.
    assert not _derive(metrics, ()).estimable


def test_assignment_count_matches_literal_product_of_binomial_sums() -> None:
    # if: C(4,0)+C(4,1)+C(4,2)=11; concise: C(3,0)+C(3,1)=4.
    limits = (
        _limit(
            "if",
            m_all_judge_fail=6,
            d_known_false_fail=2,
            optional_candidates=4,
            upper_false_fail=Decimal("0.5"),
            k_max_reclassified=3,
        ),
        _limit(
            "concise",
            m_all_judge_fail=4,
            d_known_false_fail=1,
            optional_candidates=3,
            upper_false_fail=Decimal("0.5"),
            k_max_reclassified=2,
        ),
    )
    assert sensitivity._assignment_count(limits) == 20  # (1+4) * (1+3)
    limits = (
        limits[0].model_copy(update={"upper_false_fail": Decimal("0.6"), "k_max_reclassified": 4}),
        limits[1],
    )
    assert sensitivity._assignment_count(limits) == 44
    huge = (
        _limit(
            "if",
            m_all_judge_fail=120,
            d_known_false_fail=0,
            optional_candidates=120,
            upper_false_fail=Decimal("1"),
            k_max_reclassified=120,
        ),
        _limit(
            "concise",
            m_all_judge_fail=120,
            d_known_false_fail=0,
            optional_candidates=120,
            upper_false_fail=Decimal("1"),
            k_max_reclassified=120,
        ),
    )
    assert sensitivity._assignment_count(huge) == (
        1766847064778384329583297500742918515827483896875618958121606201292619776
    )


@pytest.mark.parametrize(
    ("upper", "m", "expected"),
    [
        ("0.07", 100, 7),
        ("0.14", 100, 14),
        ("0.28", 100, 28),
        ("0.56", 50, 28),
        (
            "0.083333333333333333333333333333333333333333333333333333333333333333333333333333334",
            120,
            11,
        ),
    ],
)
def test_decimal_wilson_upper_at_k_boundary_is_ceiled_without_binary_float_rounding(
    upper: str,
    m: int,
    expected: int,
) -> None:
    metrics = _fixture(
        (
            _Spec(judge=False, consensus=False, model="model-a", arm="if", count=100),
            _Spec(judge=False, consensus=False, model="model-a", arm="concise"),
            _Spec(judge=True, consensus=True, model="model-a", arm="if", locale="ru"),
            _Spec(judge=True, consensus=True, model="model-a", arm="concise", locale="ru"),
        )
    ).metrics("model-a")
    metrics = _with_upper(metrics, upper)
    candidates = tuple(
        _candidate(row) for row in compact_sensitivity_aggregate().rows if row.arm == "if"
    )[:m]
    with localcontext() as context:
        context.prec = 2
        assert _derive(metrics, candidates).k_max_reclassified == expected


def test_direct_enumeration_matches_literal_four_extrema_and_assignment_hashes() -> None:
    aggregate = compact_sensitivity_aggregate()
    limits = (_limit("if"), _limit("concise"))
    candidates = _candidates(aggregate)
    vectors = compact_sensitivity_vectors()
    result = enumerate_sensitivity_exact(
        aggregate=aggregate, limits=limits, candidates=candidates, vectors=vectors
    )
    assert (
        result.model_dump()
        == _result(
            semantic_min_lower=SensitivityExtremumV1(
                value=-0.1, assignment_sha256=ASSIGNMENT_HASHES[0]
            ),
            semantic_max_upper=SensitivityExtremumV1(
                value=0.1, assignment_sha256=ASSIGNMENT_HASHES[0]
            ),
            token_min_lower=SensitivityExtremumV1(
                value=-5.5, assignment_sha256=ASSIGNMENT_HASHES[2]
            ),
            token_max_upper=SensitivityExtremumV1(
                value=5.5, assignment_sha256=ASSIGNMENT_HASHES[1]
            ),
        ).model_dump()
    )
    for selected, digest in zip(
        ((), (CONCISE_ID,), (IF_ID,), (IF_ID, CONCISE_ID)), ASSIGNMENT_HASHES, strict=True
    ):
        assert sensitivity._assignment_digest("model-a", selected, limits, candidates) == digest
    reversed_result = enumerate_sensitivity_exact(
        aggregate=aggregate, limits=limits, candidates=candidates[::-1], vectors=vectors
    )
    assert reversed_result == result

    class ShiftedInt(int):
        def __sub__(self, other: int) -> int:
            return int(self) - other + 1000

    forged_rows = tuple(
        row.model_copy(update={"visible_output_tokens": ShiftedInt(row.visible_output_tokens)})
        if row.arm == "concise"
        else row
        for row in aggregate.rows
    )
    forged = aggregate.model_copy(update={"rows": forged_rows})
    assert median_visible_delta(forged.rows, gate="semantic") == 0.0
    assert (
        enumerate_sensitivity_exact(
            aggregate=forged, limits=limits, candidates=candidates, vectors=vectors
        )
        == result
    )
    # Consumer normalization must neither retain the overloaded arithmetic nor
    # mutate the caller's rows while forming the validated calculation snapshot.
    assert all(
        type(row.visible_output_tokens) is ShiftedInt for row in forged.rows if row.arm == "concise"
    )
    assert all(type(row.visible_output_tokens) is int for row in aggregate.rows)
    assert tuple(SensitivityResultV1.model_fields) == (
        "generation_model",
        "model_audit_metric_sha256",
        "assignment_count",
        "visited_nodes",
        "evaluated_assignments",
        "semantic_min_lower",
        "semantic_max_upper",
        "token_min_lower",
        "token_max_upper",
        "search_exhausted",
        "exhaustion_reason",
        "certificate_sha256",
    )


def test_each_assignment_recomputes_s_eligibility_and_both_bootstrap_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregate = compact_sensitivity_aggregate()
    vectors = compact_sensitivity_vectors()
    original = aggregate.model_dump()
    selections = ((), (CONCISE_ID,), (IF_ID,), (IF_ID, CONCISE_ID))
    for index, selected in enumerate(selections):
        prepared = sensitivity._prepare_assignment(aggregate.rows, frozenset(selected))
        assert prepared.eligible_pairs == (118, 119, 119, 120)[index]
        assert prepared.token_pairs == (118, 119, 119, 120)[index]
        semantic, token = sensitivity._intervals_for_assignment(prepared, vectors)
        assert (semantic.lower, semantic.upper, token.lower, token.upper) == ASSIGNMENT_ENDPOINTS[
            index
        ]
        assert (
            semantic.point == (0.0, float(Fraction(-1, 120)), float(Fraction(1, 120)), 0.0)[index]
        )
        assert token.point == 0.0 and semantic.valid_replicates == token.valid_replicates == 10_000
        rows = tuple(
            row.model_copy(update={"semantic_success": True})
            if row.response_id in selected
            else row
            for row in aggregate.rows
        )
        blocks = tuple(
            tuple(row for row in rows if row.scenario_uid == f"{i:064x}") for i in range(12)
        )
        samples = np.asarray(
            [
                list(range(12)),
                [0] * 12,
                [11] * 12,
                [0, 11] * 6,
                [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11],
            ],
            dtype=np.uint8,
        )
        semantic_estimates, token_estimates = sensitivity._estimate_prepared(prepared, samples)
        for position, sample in enumerate(samples):
            sampled = tuple(row for i in sample for row in blocks[int(i)])
            assert semantic_estimates[position] == paired_pass_rate_difference(
                sampled, gate="semantic"
            )
            assert token_estimates[position] == median_visible_delta(sampled, gate="semantic")
    assert aggregate.model_dump() == original
    # Missing accounting removes token pairs, but never semantic successes.
    sparse = tuple(
        row.model_copy(
            update={
                "reasoning_tokens": None,
                "visible_output_tokens": None,
                "cost_availability": "retained_worst_case",
            }
        )
        if row.scenario_uid != "0" * 64
        else row
        for row in aggregate.rows
    )
    sparse_aggregate = _build_aggregated_model_from_rows(generation_model="model-a", rows=sparse)
    prepared = sensitivity._prepare_assignment(sparse_aggregate.rows, frozenset())
    assert prepared.eligible_pairs == 118 and prepared.token_pairs == 9
    sampled = tuple(row for _ in range(12) for row in sparse if row.scenario_uid == f"{11:064x}")
    estimates = sensitivity._estimate_prepared(prepared, np.full((1, 12), 11, dtype=np.uint8))
    assert median_visible_delta(sampled, gate="semantic") is None and np.isnan(estimates[1][0])
    result = enumerate_sensitivity_exact(
        aggregate=sparse_aggregate,
        limits=(_limit("if"), _limit("concise")),
        candidates=_candidates(sparse_aggregate),
        vectors=vectors,
    )
    assert result.token_min_lower is None and result.token_max_upper is None
    assert result.semantic_min_lower is not None and result.evaluated_assignments == 4
    mixed_rows = tuple(
        row
        if (row.scenario_uid, row.locale, row.repetition) == ("0" * 64, "en", 0)
        else row.model_copy(
            update={
                "reasoning_tokens": None,
                "visible_output_tokens": None,
                "cost_availability": "retained_worst_case",
            }
        )
        for row in aggregate.rows
    )
    mixed = _build_aggregated_model_from_rows(generation_model="model-a", rows=mixed_rows)
    zero_vectors = np.zeros((10_000, 12), dtype=np.uint8)
    for selected, expected_valid in zip(selections, (0, 0, 10_000, 10_000), strict=True):
        prepared = sensitivity._prepare_assignment(mixed.rows, frozenset(selected))
        _, interval = sensitivity._intervals_for_assignment(prepared, zero_vectors)
        assert interval.valid_replicates == expected_valid
    mixed_result = enumerate_sensitivity_exact(
        aggregate=mixed,
        limits=(_limit("if"), _limit("concise")),
        candidates=_candidates(mixed),
        vectors=zero_vectors,
    )
    assert mixed_result.evaluated_assignments == 4
    assert mixed_result.token_min_lower is None and mixed_result.token_max_upper is None

    # Mutation probe changes only the caller's vector buffer after input validation;
    # every estimator and all bootstrap mathematics still execute normally.
    expected = enumerate_sensitivity_exact(
        aggregate=aggregate,
        limits=(_limit("if"), _limit("concise")),
        candidates=_candidates(aggregate),
        vectors=vectors,
    )
    caller_vectors = vectors.copy()
    prepare = sensitivity._prepare_assignment

    def mutate_caller_buffer(rows: Any, selected: Any) -> Any:
        caller_vectors[:] = 0
        return prepare(rows, selected)

    with monkeypatch.context() as patch:
        patch.setattr(sensitivity, "_prepare_assignment", mutate_caller_buffer)
        actual = enumerate_sensitivity_exact(
            aggregate=aggregate,
            limits=(_limit("if"), _limit("concise")),
            candidates=_candidates(aggregate),
            vectors=caller_vectors,
        )
    assert actual == expected and not np.array_equal(caller_vectors, vectors)
    for bad_vectors in (
        vectors.astype(np.int64),
        vectors[:100],
        vectors[:, ::-1],
        np.full((10_000, 12), 12, dtype=np.uint8),
    ):
        with pytest.raises(ValueError):
            enumerate_sensitivity_exact(
                aggregate=aggregate,
                limits=(_limit("if"), _limit("concise")),
                candidates=_candidates(aggregate),
                vectors=bad_vectors,
            )


def test_assignment_space_above_4096_refuses_direct_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregate = compact_sensitivity_aggregate()
    fail_ids = {
        row.response_id
        for row in aggregate.rows
        if row.arm == "if" and row.scenario_uid == "0" * 64
    }
    fail_ids.update(
        row.response_id
        for row in aggregate.rows
        if row.arm == "concise" and row.scenario_uid == "0" * 64 and row.locale == "en"
    )
    rows = tuple(
        row.model_copy(update={"semantic_success": row.response_id not in fail_ids})
        for row in aggregate.rows
    )
    aggregate = _build_aggregated_model_from_rows(generation_model="model-a", rows=rows)
    limits = (
        _limit(
            "if",
            m_all_judge_fail=10,
            optional_candidates=10,
            upper_false_fail=Decimal("1"),
            k_max_reclassified=10,
        ),
        _limit(
            "concise",
            m_all_judge_fail=5,
            optional_candidates=5,
            upper_false_fail=Decimal("1"),
            k_max_reclassified=5,
        ),
    )
    assert sensitivity._assignment_count(limits) == 32768

    # The cap must reject before any bootstrap work begins.
    def forbidden_bootstrap(*args: Any, **kwargs: Any) -> None:
        pytest.fail("oversized assignment space reached bootstrap")

    monkeypatch.setattr(sensitivity, "_intervals_for_assignment", forbidden_bootstrap)
    with pytest.raises(ValueError, match="4096"):
        enumerate_sensitivity_exact(
            aggregate=aggregate,
            limits=limits,
            candidates=_candidates(aggregate),
            vectors=compact_sensitivity_vectors(),
        )


def test_nonexhausted_sensitivity_result_forbids_an_exhaustion_reason() -> None:
    for reason in ("visited_node_cap", "bootstrap_evaluation_cap"):
        with pytest.raises(ValidationError):
            _result(exhaustion_reason=reason)
    for reason, visited, evaluated in (
        ("visited_node_cap", 1_000_000, 12),
        ("bootstrap_evaluation_cap", 5000, 4096),
    ):
        valid = dict(
            search_exhausted=True,
            exhaustion_reason=reason,
            visited_nodes=visited,
            evaluated_assignments=evaluated,
        )
        assert _result(**valid).search_exhausted
        for update in (
            {"exhaustion_reason": None},
            {"certificate_sha256": "0" * 64},
            {"semantic_min_lower": SensitivityExtremumV1(value=0.0, assignment_sha256="0" * 64)},
        ):
            with pytest.raises(ValidationError):
                _result(**{**valid, **update})
    for reason, visited, evaluated in product(
        ("visited_node_cap", "bootstrap_evaluation_cap"),
        (999_999, 1_000_000, 1_000_001),
        (4095, 4096),
    ):
        if (reason == "visited_node_cap" and visited == 1_000_000) or (
            reason == "bootstrap_evaluation_cap" and visited < 1_000_000 and evaluated == 4096
        ):
            continue
        with pytest.raises(ValidationError):
            _result(
                search_exhausted=True,
                exhaustion_reason=reason,
                visited_nodes=visited,
                evaluated_assignments=evaluated,
            )
    for value, digest in ((float("nan"), "0" * 64), (float("inf"), "0" * 64), (0.0, "F" * 64)):
        with pytest.raises(ValidationError):
            SensitivityExtremumV1(value=value, assignment_sha256=digest)
