from __future__ import annotations

# ruff: noqa: I001 -- direct module import preserves the Task 6 RED boundary.

from collections import Counter
from decimal import Decimal
from hashlib import sha256

import numpy as np
import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.bootstrap import (
    BOOTSTRAP_CLUSTER_COUNT,
    BOOTSTRAP_MIN_VALID,
    BOOTSTRAP_REPLICATES,
    BootstrapIntervalV1,
    BootstrapVectorsV1,
    _verify_cluster_vectors,
    cluster_percentile_interval,
    make_cluster_vectors,
    type7_quantile,
)
from laconian_eval.benchmark import (
    BootstrapIntervalV1 as PublicBootstrapIntervalV1,
)
from laconian_eval.benchmark import (
    BootstrapVectorsV1 as PublicBootstrapVectorsV1,
)
from laconian_eval.benchmark import (
    make_cluster_vectors as public_make_cluster_vectors,
)
from laconian_eval.benchmark.aggregation import (
    InferenceIntegrityError,
    PlannedObservationV1,
    arm_pass_proportion,
    median_visible_delta,
    paired_pass_rate_difference,
)


def _scenario_uid(ordinal: int) -> str:
    return sha256(f"scenario-{ordinal}".encode()).hexdigest()


def _observation(
    *, scenario: int, locale: str, repetition: int, arm: str
) -> PlannedObservationV1:
    visible = scenario + (10 if arm == "concise" else 1 if arm == "if" else 0)
    return PlannedObservationV1(
        generation_model="model-a",
        scenario_uid=_scenario_uid(scenario),
        case_id=f"case-{scenario:02d}-{locale}",
        locale=locale,
        repetition=repetition,
        arm=arm,
        response_id=f"response-{scenario}-{locale}-{repetition}-{arm}",
        hard_pass=True,
        semantic_success=True,
        terminal_zero_reason=None,
        input_tokens=20,
        output_tokens=visible,
        reasoning_tokens=0,
        cache_read_tokens=2,
        cache_write_tokens=0,
        ordinary_uncached_input_tokens=18,
        total_tokens=20 + visible,
        visible_output_tokens=visible,
        applied_cache_control_status="reported_exact",
        cache_read_status="reported_nonzero",
        cache_write_status="reported_zero",
        service_tier_status="reported_default",
        cache_policy_status="conformant_zero_write",
        analytical_cost_usd=Decimal("0.000012"),
        cost_availability="trusted_usage",
        latency_ms=25,
        output_characters=12,
    )


def _complete_rows() -> tuple[PlannedObservationV1, ...]:
    return tuple(
        _observation(
            scenario=scenario,
            locale=locale,
            repetition=repetition,
            arm=arm,
        )
        for scenario in range(12)
        for locale in ("en", "ru")
        for repetition in range(5)
        for arm in ("baseline", "caveman", "if", "concise")
    )


def _identity_indices() -> np.ndarray:
    return np.tile(
        np.arange(BOOTSTRAP_CLUSTER_COUNT, dtype=np.uint8),
        (BOOTSTRAP_REPLICATES, 1),
    )


def test_cluster_vectors_keep_locales_repetitions_and_matched_arms_together() -> None:
    class _Text(str):
        pass

    class _UIDTuple(tuple):
        pass

    scenario_uids = tuple(_scenario_uid(index) for index in reversed(range(12)))
    metadata, indices = make_cluster_vectors(
        seed=20260830, scenario_uids=scenario_uids
    )

    assert BOOTSTRAP_REPLICATES == 10_000
    assert BOOTSTRAP_CLUSTER_COUNT == 12
    assert BOOTSTRAP_MIN_VALID == 9_990
    assert metadata.scenario_uids == tuple(
        sorted(scenario_uids, key=lambda value: value.encode("utf-8"))
    )
    assert indices.dtype == np.dtype(np.uint8)
    assert indices.shape == (10_000, 12)
    assert indices.flags.c_contiguous
    assert indices[:4].tobytes(order="C").hex() == (
        "090a03020b02070107040a070b0b0b050707060306070004"
        "08010008020203070a080109040b010309020b0404010402"
    )
    assert metadata.indices_sha256 == (
        "70b0ac50e2a650b3fd65c3dbedfbd8407b72f81be989e576f044f9fdcb7cbecd"
    )
    assert _verify_cluster_vectors(metadata, indices) is indices

    rows = _complete_rows()
    zero_indices = np.zeros((10_000, 12), dtype=np.uint8)
    ordered_uids = sorted({row.scenario_uid for row in rows}, key=lambda uid: uid.encode())
    mixed_generation_uid = ordered_uids[0]
    mixed_generation_rows = tuple(
        row.model_copy(update={"generation_model": "model-b"})
        if row.scenario_uid == mixed_generation_uid
        else row
        for row in rows
    )

    def must_not_estimate(_: tuple[PlannedObservationV1, ...]) -> float:
        raise AssertionError("mixed-generation rows reached the estimator")

    with pytest.raises(InferenceIntegrityError, match="generation model"):
        cluster_percentile_interval(
            point=0.0,
            rows=mixed_generation_rows,
            indices=zero_indices,
            estimator=must_not_estimate,
        )

    changed = indices.copy(order="C")
    changed[0, 0] ^= np.uint8(1)
    unit_seed_metadata, unit_seed_indices = make_cluster_vectors(
        seed=1, scenario_uids=scenario_uids
    )
    for bad_metadata, bad_indices in (
        (unit_seed_metadata.model_copy(update={"seed": True}), unit_seed_indices),
        (unit_seed_metadata.model_copy(update={"seed": 1.0}), unit_seed_indices),
        (metadata.model_copy(update={"replicates": 10_000.0}), indices),
        (metadata.model_copy(update={"replicates": True}), indices),
        (
            metadata.model_copy(update={"scenario_uids": list(metadata.scenario_uids)}),
            indices,
        ),
        (
            metadata.model_copy(update={"scenario_uids": _UIDTuple(metadata.scenario_uids)}),
            indices,
        ),
        (
            metadata.model_copy(
                update={
                    "scenario_uids": tuple(_Text(uid) for uid in metadata.scenario_uids)
                }
            ),
            indices,
        ),
        (metadata.model_copy(update={"index_dtype": _Text("uint8")}), indices),
        (
            metadata.model_copy(
                update={"indices_sha256": _Text(metadata.indices_sha256)}
            ),
            indices,
        ),
        (metadata.model_copy(update={"replicates": 9_999}), indices),
        (metadata.model_copy(update={"index_dtype": "float64"}), indices),
        (metadata.model_copy(update={"seed": metadata.seed + 1}), indices),
        (
            metadata.model_copy(
                update={"scenario_uids": tuple(reversed(metadata.scenario_uids))}
            ),
            indices,
        ),
        (metadata.model_copy(update={"indices_sha256": "0" * 64}), indices),
        (metadata.model_copy(update={"unexpected": "extra-state"}), indices),
        (metadata, changed),
        (metadata, indices.astype(np.int16)),
        (metadata, indices[:-1]),
    ):
        with pytest.raises(ValueError):
            _verify_cluster_vectors(bad_metadata, bad_indices)

    calls = 0

    def inspect_complete_cluster(sampled: tuple[PlannedObservationV1, ...]) -> float:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert len(sampled) == 480
            assert {row.scenario_uid for row in sampled} == {ordered_uids[0]}
            assert {row.locale for row in sampled} == {"en", "ru"}
            assert {row.repetition for row in sampled} == set(range(5))
            assert {row.arm for row in sampled} == {
                "baseline",
                "caveman",
                "if",
                "concise",
            }
            multiplicities = Counter(
                (row.case_id, row.locale, row.repetition, row.arm) for row in sampled
            )
            assert set(multiplicities.values()) == {12}
        return 0.0

    interval = cluster_percentile_interval(
        point=0.0,
        rows=rows,
        indices=zero_indices,
        estimator=inspect_complete_cluster,
    )
    assert calls == 10_000
    assert interval.available
    assert (interval.lower, interval.upper) == (0.0, 0.0)


def test_type7_quantile_matches_frozen_golden_vector() -> None:
    values = np.array([-9.0, -4.0, -1.0, 0.0, 2.0, 7.0, 11.0, 40.0])
    assert type7_quantile(values, 0.025) == pytest.approx(-8.125)
    assert type7_quantile(values, 0.975) == pytest.approx(34.925)
    assert type7_quantile(np.array([7.0]), 0.025) == 7.0

    for unusable_values, q in (
        (np.array([], dtype=np.float64), 0.5),
        (np.array([1.0, np.nan]), 0.5),
        (np.array([1.0]), -0.1),
        (np.array([1.0]), 1.1),
        (np.array([1.0]), float("nan")),
    ):
        with pytest.raises(ValueError):
            type7_quantile(unusable_values, q)


def test_cluster_bootstrap_recomputes_complete_estimator_per_replicate() -> None:
    rows = _complete_rows()
    assert median_visible_delta(rows, gate="hard") == 9.0
    assert arm_pass_proportion(rows, arm="if", gate="semantic") == 1.0
    assert paired_pass_rate_difference(rows, gate="hard") == 0.0

    first_uid = min({row.scenario_uid for row in rows}, key=lambda uid: uid.encode())
    first_block = tuple(row for row in rows if row.scenario_uid == first_uid)
    sampled_duplicate = first_block * 12
    assert median_visible_delta(sampled_duplicate, gate="hard") == 9.0
    assert arm_pass_proportion(
        sampled_duplicate, arm="concise", gate="hard"
    ) == 1.0
    assert paired_pass_rate_difference(sampled_duplicate, gate="semantic") == 0.0

    mismatched = (*sampled_duplicate[:-1], sampled_duplicate[-2])
    with pytest.raises(InferenceIntegrityError, match=r"matched|multiplicit|block"):
        median_visible_delta(mismatched, gate="hard")
    with pytest.raises(InferenceIntegrityError):
        arm_pass_proportion(rows, arm="unknown", gate="hard")  # type: ignore[arg-type]
    with pytest.raises(InferenceIntegrityError):
        paired_pass_rate_difference(rows, gate="unknown")  # type: ignore[arg-type]

    indices = _identity_indices()
    indices[:300] = 0
    indices[300:600] = 11
    ordered_uids = tuple(
        sorted({row.scenario_uid for row in rows}, key=lambda uid: uid.encode())
    )
    rank_by_uid = {scenario_uid: rank for rank, scenario_uid in enumerate(ordered_uids)}
    calls = 0
    sampled_identity_sets: set[frozenset[str]] = set()
    replicate_results: set[float] = set()

    def recompute(sampled: tuple[PlannedObservationV1, ...]) -> float:
        nonlocal calls
        calls += 1
        assert len(sampled) == 480
        if calls == 1:
            indices[1:] = 0
        sampled_identity_sets.add(frozenset(row.scenario_uid for row in sampled))
        selected_ranks = [
            rank_by_uid[row.scenario_uid] for row in sampled if row.arm == "if"
        ]
        result = sum(selected_ranks) / 120
        replicate_results.add(result)
        return result

    interval = cluster_percentile_interval(
        point=5.5,
        rows=rows,
        indices=indices,
        estimator=recompute,
    )
    assert calls == 10_000
    assert interval.valid_replicates == 10_000
    assert interval.lower == 0.0
    assert interval.upper == 11.0
    assert replicate_results == {0.0, 5.5, 11.0}
    assert frozenset({ordered_uids[0]}) in sampled_identity_sets
    assert frozenset({ordered_uids[11]}) in sampled_identity_sets
    assert frozenset(ordered_uids) in sampled_identity_sets


def test_fewer_than_9990_valid_replicates_is_inconclusive() -> None:
    calls = 0

    def sometimes_invalid(_: tuple[PlannedObservationV1, ...]) -> float | None:
        nonlocal calls
        calls += 1
        if calls <= 5:
            return None
        if calls <= 8:
            return float("nan")
        if calls <= 11:
            return float("inf")
        return 1.0

    interval = cluster_percentile_interval(
        point=1.0,
        rows=_complete_rows(),
        indices=_identity_indices(),
        estimator=sometimes_invalid,
    )
    assert calls == 10_000
    assert interval.valid_replicates == 9_989
    assert not interval.available
    assert interval.lower is None
    assert interval.upper is None

    threshold_calls = 0

    def exactly_at_threshold(
        _: tuple[PlannedObservationV1, ...],
    ) -> float | None:
        nonlocal threshold_calls
        threshold_calls += 1
        return None if threshold_calls <= 10 else 2.0

    threshold_interval = cluster_percentile_interval(
        point=2.0,
        rows=_complete_rows(),
        indices=_identity_indices(),
        estimator=exactly_at_threshold,
    )
    assert threshold_calls == 10_000
    assert threshold_interval.valid_replicates == 9_990
    assert threshold_interval.available
    assert threshold_interval.lower == 2.0
    assert threshold_interval.upper == 2.0


def test_bootstrap_interval_names_the_fixed_campaign_conditional_scenario_target() -> None:
    interval = BootstrapIntervalV1(
        point=1.0,
        lower=0.5,
        upper=1.5,
        valid_replicates=10_000,
        available=True,
    )
    assert interval.inferential_target == (
        "scenario-superpopulation-conditional-on-fixed-campaign"
    )
    assert PublicBootstrapIntervalV1 is BootstrapIntervalV1
    assert PublicBootstrapVectorsV1 is BootstrapVectorsV1
    assert public_make_cluster_vectors is make_cluster_vectors

    with pytest.raises(ValidationError):
        BootstrapIntervalV1(
            point=1.0,
            lower=0.5,
            upper=1.5,
            valid_replicates=10_000,
            available=True,
            inferential_target="unconditional",  # type: ignore[arg-type]
        )


def test_twelve_cluster_percentile_coverage_is_labelled_nominal_and_approximate() -> None:
    interval = BootstrapIntervalV1(
        point=None,
        lower=None,
        upper=None,
        valid_replicates=9_989,
        available=False,
    )
    assert interval.coverage == (
        "nominal-95-percent-approximate-12-cluster-percentile"
    )

    inconsistent = (
        {
            "point": 1.0,
            "lower": None,
            "upper": 1.5,
            "valid_replicates": 10_000,
            "available": True,
        },
        {
            "point": 1.0,
            "lower": 0.5,
            "upper": 1.5,
            "valid_replicates": 9_989,
            "available": True,
        },
        {
            "point": 1.0,
            "lower": 0.5,
            "upper": 1.5,
            "valid_replicates": 10_000,
            "available": False,
        },
    )
    for fields in inconsistent:
        with pytest.raises(ValidationError):
            BootstrapIntervalV1(**fields)  # type: ignore[arg-type]
