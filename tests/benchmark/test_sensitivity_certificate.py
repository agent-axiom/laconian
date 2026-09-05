"""Exact sensitivity proof contracts over synthetic, externally unauthenticated inputs."""

from __future__ import annotations

import hashlib
from itertools import product
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

import laconian_eval.benchmark.sensitivity as sensitivity
from laconian_eval.benchmark.aggregation import _build_aggregated_model_from_rows
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from tests.benchmark.helpers import (
    compact_sensitivity_aggregate,
    compact_sensitivity_vectors,
    sensitivity_certificate_fixture,
)
from tests.benchmark.test_sensitivity_direct import _candidates, _limit, _result

EXTREMA = ("semantic_min_lower", "semantic_max_upper", "token_min_lower", "token_max_upper")


def _search(fixture: Any) -> Any:
    assert hasattr(sensitivity, "search_sensitivity_exact"), "certified search is not implemented"
    return sensitivity.search_sensitivity_exact(**vars(fixture))


def _verify(certificate: Any, fixture: Any) -> Any:
    return sensitivity.verify_sensitivity_certificate(
        certificate,
        aggregate=fixture.aggregate,
        candidates=fixture.candidates,
        vectors=fixture.vectors,
    )


def _reseal(certificate: Any, **updates: Any) -> Any:
    payload = certificate.model_dump(mode="json", exclude={"certificate_sha256"})
    payload.update(updates)
    payload["certificate_sha256"] = stable_digest("laconian-sensitivity-certificate-v1", payload)
    return sensitivity.SensitivityCertificateV1.model_validate_json(canonical_json(payload))


@pytest.mark.parametrize("mode", ["mixed", "wide"])
def test_certificate_verifies_cardinality_pruned_subtrees_and_every_feasible_leaf(
    mode: str,
) -> None:
    fixture = sensitivity_certificate_fixture(mode)
    result, certificate = _search(fixture)
    assert certificate is not None
    assert _verify(certificate, fixture) == result
    if mode == "wide":
        # 32760 prune owners exceed the generic audit preflight's 262144-node
        # graph budget, but this complete proof remains below both normative caps.
        assert result.assignment_count == result.evaluated_assignments == 1681
        assert result.visited_nodes == 68881
        assert len(certificate.pruned_subtrees) == 32760
        with pytest.raises(TypeError, match="node limit"):
            sensitivity._preflight_exact_model_owners_v1(
                certificate,
                sensitivity.SensitivityCertificateV1,
            )
        return
    assert certificate.candidate_order == ("a", "z", "é", "Ж")
    assert certificate.visited_nodes == result.visited_nodes == 27
    assert result.assignment_count == result.evaluated_assignments == 9
    assert [
        (prune.prefix_bits, prune.assignment_count) for prune in certificate.pruned_subtrees
    ] == [
        ("0101", 1),
        ("0111", 1),
        ("101", 2),
        ("1101", 1),
        ("111", 2),
    ]
    assert [
        (dict(prune.selected_by_arm), dict(prune.remaining_by_arm))
        for prune in certificate.pruned_subtrees
    ] == [
        ({"if": 0, "concise": 2}, {"if": 0, "concise": 0}),
        ({"if": 1, "concise": 2}, {"if": 0, "concise": 0}),
        ({"if": 2, "concise": 0}, {"if": 0, "concise": 1}),
        ({"if": 1, "concise": 2}, {"if": 0, "concise": 0}),
        ({"if": 2, "concise": 1}, {"if": 0, "concise": 1}),
    ]
    assert sum(prune.assignment_count for prune in certificate.pruned_subtrees) + 9 == 16
    expected = {
        tuple(sorted(("F-if", "F-concise", *left, *right), key=str.encode))
        for left, right in product(((), ("a",), ("é",)), ((), ("z",), ("Ж",)))
    }
    assert {leaf.selected_response_ids for leaf in certificate.evaluated_leaves} == expected
    for leaf in certificate.evaluated_leaves:
        selected = set(leaf.selected_response_ids)
        endpoint = (len(selected & {"a", "é"}) - len(selected & {"z", "Ж"})) / 120
        assert (leaf.semantic_lower, leaf.semantic_upper) == (endpoint, endpoint)
        assert (leaf.token_lower, leaf.token_upper) == (0.0, 0.0)
    # A complete partition also exists when there are no optional decisions.
    fixture.candidates = tuple(
        c.model_copy(update={"known_false_fail": True}) for c in fixture.candidates
    )
    fixture.limits = tuple(
        limit.model_copy(
            update={
                "d_known_false_fail": 3,
                "optional_candidates": 0,
                "k_max_reclassified": 3,
            }
        )
        for limit in fixture.limits
    )
    result, certificate = _search(fixture)
    assert certificate.candidate_order == ()
    assert (result.visited_nodes, result.evaluated_assignments) == (1, 1)
    assert _verify(certificate, fixture) == result


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "overlap",
        "count",
        "selected",
        "remaining",
        "feasible",
        "leaf_missing",
        "leaf_duplicate",
        "leaf_forced_omitted",
        "leaf_outside_pool",
        "visited",
        "order",
        "limit_counts",
        "metric_digest",
        "model",
    ],
)
def test_certificate_rejects_missing_overlapping_or_wrong_cardinality_subtree(
    mutation: str,
) -> None:
    fixture = sensitivity_certificate_fixture()
    _, certificate = _search(fixture)
    payload = certificate.model_dump(mode="json")
    prunes = payload["pruned_subtrees"]
    leaves = payload["evaluated_leaves"]
    if mutation == "missing":
        prunes.pop()
    elif mutation == "overlap":
        # Equal totals can hide an omitted subtree plus a duplicated different one.
        prunes[-1] = prunes[2]
    elif mutation == "count":
        prunes[0]["assignment_count"] = 2
    elif mutation == "selected":
        prunes[0]["selected_by_arm"]["if"] = 1
    elif mutation == "remaining":
        prunes[0]["remaining_by_arm"]["if"] = 1
    elif mutation == "feasible":
        prunes[0]["prefix_bits"] = "0000"
    elif mutation == "leaf_missing":
        leaves.pop()
    elif mutation == "leaf_duplicate":
        leaves[1] = leaves[0]
    elif mutation == "leaf_forced_omitted":
        leaves[0]["selected_response_ids"].remove("F-if")
    elif mutation == "leaf_outside_pool":
        leaves[0]["selected_response_ids"].append("unknown")
    elif mutation == "visited":
        payload["visited_nodes"] += 1
    elif mutation == "order":
        payload["candidate_order"].reverse()
    elif mutation == "limit_counts":
        payload["limits"][0].update(m_all_judge_fail=4, optional_candidates=3)
    elif mutation == "metric_digest":
        payload["model_audit_metric_sha256"] = "8" * 64
    else:
        payload["generation_model"] = "other"
    forged = _reseal(certificate, **{k: v for k, v in payload.items() if k != "certificate_sha256"})
    with pytest.raises((ValueError, TypeError)):
        _verify(forged, fixture)


@pytest.mark.parametrize(
    "forbidden",
    [
        "semantic-dominance",
        "token-dominance",
        "incumbent",
        *(
            f"extra_{storage}_{target}"
            for storage in ("dict", "slot")
            for target in ("certificate", "leaf", "prune", "limit", "extremum", "candidate")
        ),
    ],
)
def test_v1_schema_rejects_semantic_or_token_dominance_pruning(forbidden: str) -> None:
    fixture = sensitivity_certificate_fixture()
    _, certificate = _search(fixture)
    if forbidden.startswith("extra_"):
        _, storage, target = forbidden.split("_")
        instance = {
            "certificate": certificate,
            "leaf": certificate.evaluated_leaves[0],
            "prune": certificate.pruned_subtrees[0],
            "limit": certificate.limits[0],
            "extremum": certificate.semantic_min_lower,
            "candidate": fixture.candidates[0],
        }[target]
        for field, value in (("witness", {"objective_bound": 0.0}), ("objective_bound", 0.0)):
            forged_instance = instance.model_copy(
                update={field: value} if storage == "dict" else {}
            )
            if storage == "slot":
                object.__setattr__(forged_instance, "__pydantic_extra__", {field: value})
            if target == "candidate":
                fixture.candidates = (forged_instance, *fixture.candidates[1:])
                with pytest.raises((ValueError, TypeError)):
                    _search(fixture)
                continue
            nested_update = {
                "leaf": {"evaluated_leaves": (forged_instance, *certificate.evaluated_leaves[1:])},
                "prune": {"pruned_subtrees": (forged_instance, *certificate.pruned_subtrees[1:])},
                "limit": {"limits": (forged_instance, certificate.limits[1])},
                "extremum": {"semantic_min_lower": forged_instance},
            }
            forged = (
                forged_instance
                if target == "certificate"
                else certificate.model_copy(update=nested_update[target])
            )
            with pytest.raises((ValueError, TypeError)):
                _verify(forged, fixture)
        return
    prune = certificate.pruned_subtrees[0]
    with pytest.raises(ValidationError):
        type(prune).model_validate({**prune.model_dump(), "reason": forbidden})
    with pytest.raises((ValueError, TypeError)):
        _verify(
            certificate.model_copy(
                update={
                    "pruned_subtrees": (
                        prune.model_copy(update={"reason": forbidden}),
                        *certificate.pruned_subtrees[1:],
                    ),
                }
            ),
            sensitivity_certificate_fixture(),
        )
    for owner, instance, fields in (
        (
            sensitivity.PrunedSubtreeV1,
            prune,
            ("prefix_bits", "selected_by_arm", "remaining_by_arm", "assignment_count", "reason"),
        ),
        (
            sensitivity.EvaluatedLeafV1,
            certificate.evaluated_leaves[0],
            (
                "assignment_sha256",
                "selected_response_ids",
                "semantic_lower",
                "semantic_upper",
                "token_lower",
                "token_upper",
            ),
        ),
        (
            sensitivity.SensitivityCertificateV1,
            certificate,
            (
                "schema_version",
                "generation_model",
                "model_audit_metric_sha256",
                "candidate_order",
                "limits",
                "bootstrap_vectors_sha256",
                "visited_nodes",
                "evaluated_leaves",
                "pruned_subtrees",
                *EXTREMA,
                "certificate_sha256",
            ),
        ),
    ):
        assert tuple(owner.model_fields) == fields
        assert owner.model_config["strict"] and owner.model_config["frozen"]
        assert owner.model_config["extra"] == "forbid"
        with pytest.raises(ValidationError):
            owner.model_validate({**instance.model_dump(), "objective_bound": 0.0})
    for update in (
        {"prefix_bits": "012"},
        {"assignment_count": 0},
        {"selected_by_arm": {"if": 0}},
        {"remaining_by_arm": {"if": -1, "concise": 1}},
    ):
        with pytest.raises(ValidationError):
            type(prune).model_validate({**prune.model_dump(), **update})
    for field in ("semantic_lower", "semantic_upper", "token_lower", "token_upper"):
        with pytest.raises(ValidationError):
            sensitivity.EvaluatedLeafV1.model_validate(
                {
                    **certificate.evaluated_leaves[0].model_dump(),
                    field: float("nan"),
                }
            )


@pytest.mark.parametrize(
    "mutation",
    [
        "leaf",
        "leaf_hash",
        "extremum",
        "vector_digest",
        "vectors",
        "instance_serializer",
        "search_limit_serializer",
        "search_candidate_serializer",
    ],
)
def test_certificate_rejects_wrong_leaf_extremum_or_bootstrap_vector_digest(mutation: str) -> None:
    fixture = sensitivity_certificate_fixture()
    _, certificate = _search(fixture)
    payload = certificate.model_dump(mode="json")
    if mutation in {"search_limit_serializer", "search_candidate_serializer"}:
        original = (
            fixture.limits[0] if mutation == "search_limit_serializer" else fixture.candidates[0]
        )

        class InputSubstituteSerializer:
            def to_python(self, *args: Any, **kwargs: Any) -> Any:
                return original.model_dump(mode="json")

        update = (
            {"m_all_judge_fail": 120}
            if mutation == "search_limit_serializer"
            else {"scenario_uid": "f" * 64}
        )
        forged_input = original.model_copy(
            update={
                **update,
                "__pydantic_serializer__": InputSubstituteSerializer(),
            }
        )
        if mutation == "search_limit_serializer":
            fixture.limits = (forged_input, fixture.limits[1])
        else:
            fixture.candidates = (forged_input, *fixture.candidates[1:])
        with pytest.raises((ValueError, TypeError)):
            _search(fixture)
        return
    if mutation == "instance_serializer":

        class SubstituteSerializer:
            def to_python(self, *args: Any, **kwargs: Any) -> Any:
                return payload

        forged = certificate.model_copy(
            update={
                "generation_model": "forged",
                "__pydantic_serializer__": SubstituteSerializer(),
            }
        )
        with pytest.raises((ValueError, TypeError)):
            _verify(forged, fixture)
        return
    if mutation == "leaf":
        payload["evaluated_leaves"][0]["semantic_lower"] = 0.25
    elif mutation == "leaf_hash":
        payload["evaluated_leaves"][0]["assignment_sha256"] = "0" * 64
    elif mutation == "extremum":
        payload["semantic_min_lower"]["value"] = 0.25
    elif mutation == "vector_digest":
        payload["bootstrap_vectors_sha256"] = "0" * 64
    else:
        fixture.vectors[0, 0] = 11
    forged = _reseal(certificate, **{k: v for k, v in payload.items() if k != "certificate_sha256"})
    with pytest.raises((ValueError, TypeError)):
        _verify(forged, fixture)


def test_certificate_digest_precedes_result_reference_without_a_hash_cycle() -> None:
    fixture = sensitivity_certificate_fixture()
    result, certificate = _search(fixture)
    payload = certificate.model_dump(mode="json", exclude={"certificate_sha256"})
    assert "result" not in payload and "result_sha256" not in payload
    assert certificate.certificate_sha256 == stable_digest(
        "laconian-sensitivity-certificate-v1",
        payload,
    )
    assert (
        certificate.bootstrap_vectors_sha256
        == hashlib.sha256(
            fixture.vectors.tobytes(order="C"),
        ).hexdigest()
    )
    assert result.certificate_sha256 == certificate.certificate_sha256
    # Literal independently derived stdlib JSON/SHA256 oracle for the UTF-8 tree.
    assert certificate.certificate_sha256 == (
        "2b09fe8964a2545f55ff14127108dbba93c8e826dd34055a24793c797bcdd741"
    )
    assert certificate.bootstrap_vectors_sha256 == (
        "269a5f68e5c89146c71f6304e2f41facb3276ab3d10e058e664e84b5f832dce1"
    )
    assert result.model_audit_metric_sha256 == certificate.model_audit_metric_sha256 == "7" * 64
    with pytest.raises((ValueError, TypeError)):
        _verify(certificate.model_copy(update={"certificate_sha256": "0" * 64}), fixture)
    decoded = sensitivity.SensitivityCertificateV1.model_validate_json(
        canonical_json(certificate.model_dump(mode="json")),
    )
    assert _verify(decoded, fixture) == result


@pytest.mark.parametrize(
    "mode",
    [
        "mixed",
        "cardinality-tie",
        "compact",
        "unavailable",
        "scalar_subclass",
        "token_unavailable",
    ],
)
def test_direct_and_certified_search_return_identical_extrema_on_overlap_space(mode: str) -> None:
    fixture = sensitivity_certificate_fixture(mode if mode == "cardinality-tie" else "mixed")
    if mode not in {"mixed", "cardinality-tie"}:
        fixture.aggregate = compact_sensitivity_aggregate()
        fixture.candidates = _candidates(fixture.aggregate)
        fixture.limits = (_limit("if"), _limit("concise"))
        fixture.vectors = compact_sensitivity_vectors()
    if mode == "token_unavailable":
        rows = tuple(
            row
            if (row.scenario_uid, row.locale, row.repetition) == ("0" * 64, "en", 0)
            else row.model_copy(
                update={
                    "reasoning_tokens": None,
                    "visible_output_tokens": None,
                    "cost_availability": "retained_worst_case",
                }
            )
            for row in fixture.aggregate.rows
        )
        fixture.aggregate = _build_aggregated_model_from_rows(generation_model="model-a", rows=rows)
        fixture.vectors = np.zeros((10_000, 12), dtype=np.uint8)
    if mode == "unavailable":
        fixture.limits = tuple(
            limit.model_copy(
                update={
                    "estimable": False,
                    "upper_false_fail": None,
                    "k_max_reclassified": 0,
                }
            )
            for limit in fixture.limits
        )
    if mode == "scalar_subclass":

        class ShiftedInt(int):
            def __sub__(self, other: int) -> int:
                return int(self) - other + 1000

        fixture.aggregate = fixture.aggregate.model_copy(
            update={
                "rows": tuple(
                    row.model_copy(
                        update={"visible_output_tokens": ShiftedInt(row.visible_output_tokens)}
                    )
                    if row.arm == "concise"
                    else row
                    for row in fixture.aggregate.rows
                )
            }
        )
    direct = sensitivity.enumerate_sensitivity_exact(**vars(fixture))
    result, certificate = _search(fixture)
    assert {field: getattr(result, field) for field in EXTREMA} == {
        field: getattr(direct, field) for field in EXTREMA
    }
    assert result.assignment_count == direct.assignment_count
    if mode == "unavailable":
        assert result == direct and certificate is None
        assert result.visited_nodes == result.evaluated_assignments == 0
        assert not result.search_exhausted
    else:
        assert _verify(certificate, fixture) == result
        if mode == "token_unavailable":
            assert [leaf.token_lower for leaf in certificate.evaluated_leaves] == [
                None,
                None,
                -10.0,
                -10.0,
            ]
            assert result.token_min_lower is None and result.token_max_upper is None
        if mode == "cardinality-tie":
            assert result.visited_nodes == 19 and result.assignment_count == 7
            assert result.semantic_max_upper.assignment_sha256 == (
                "1f08e8436060502fe3e9d6acf3f233ee5bad618e74f02a7da072a5b62ac51f12"
            )
        if mode == "mixed":
            by_hash = {
                leaf.assignment_sha256: leaf.selected_response_ids
                for leaf in certificate.evaluated_leaves
            }
            assert by_hash[result.semantic_min_lower.assignment_sha256] == (
                "F-concise",
                "F-if",
                "z",
            )
            assert by_hash[result.semantic_max_upper.assignment_sha256] == (
                "F-concise",
                "F-if",
                "a",
            )
            assert by_hash[result.token_min_lower.assignment_sha256] == ("F-concise", "F-if")


def test_m_equals_k_120_exhausts_at_exact_caps_and_discards_partial_extrema() -> None:
    fixture = sensitivity_certificate_fixture("bootstrap")
    result, certificate = _search(fixture)
    assert sensitivity.MAX_VISITED_NODES == 1_000_000
    assert sensitivity.MAX_BOOTSTRAP_LEAVES == 4096
    assert result.assignment_count == 2**240
    assert (result.visited_nodes, result.evaluated_assignments) == (8432, 4096)
    assert result.exhaustion_reason == "bootstrap_evaluation_cap"
    assert result.search_exhausted and certificate is None and result.certificate_sha256 is None
    assert all(getattr(result, field) is None for field in EXTREMA)
    # Exactly 4096 assignments complete without attempting a forbidden next operation.
    fixture = sensitivity_certificate_fixture("exact-cap")
    result, certificate = _search(fixture)
    assert (result.assignment_count, result.evaluated_assignments, result.visited_nodes) == (
        4096,
        4096,
        8191,
    )
    assert not result.search_exhausted and result.exhaustion_reason is None
    assert certificate is not None and _verify(certificate, fixture) == result


@pytest.mark.parametrize(
    "mode,reason,visited,evaluated,assignments",
    [
        ("bootstrap", "bootstrap_evaluation_cap", 8432, 4096, 2**240),
        ("visited", "visited_node_cap", 1_000_000, 3402, 7261),
    ],
)
def test_each_search_cap_emits_its_closed_reason_and_no_certificate(
    mode: str,
    reason: str,
    visited: int,
    evaluated: int,
    assignments: int,
) -> None:
    result, certificate = _search(sensitivity_certificate_fixture(mode))
    assert result.search_exhausted and result.exhaustion_reason == reason
    assert (result.visited_nodes, result.evaluated_assignments) == (visited, evaluated)
    assert result.assignment_count == assignments
    assert certificate is None and result.certificate_sha256 is None
    assert all(getattr(result, field) is None for field in EXTREMA)


def test_sensitivity_result_rejects_unknown_or_inconsistent_exhaustion_reason() -> None:
    _search(sensitivity_certificate_fixture())  # The new schema/caps belong to this feature.
    valid = dict(
        search_exhausted=True,
        exhaustion_reason="bootstrap_evaluation_cap",
        visited_nodes=8432,
        evaluated_assignments=4096,
        assignment_count=2**240,
    )
    assert _result(**valid).search_exhausted
    for update in (
        {"exhaustion_reason": "objective_bound"},
        {"exhaustion_reason": None},
        {"search_exhausted": False},
        {"evaluated_assignments": 4095},
        {"evaluated_assignments": 4097},
        {"visited_nodes": 1_000_000},
        {"certificate_sha256": "0" * 64},
        *(
            {field: sensitivity.SensitivityExtremumV1(value=0.0, assignment_sha256="0" * 64)}
            for field in EXTREMA
        ),
    ):
        with pytest.raises(ValidationError):
            _result(**{**valid, **update})
    for visited, evaluated in ((999_999, 3402), (1_000_001, 3402), (1_000_000, 4097)):
        with pytest.raises(ValidationError):
            _result(
                search_exhausted=True,
                exhaustion_reason="visited_node_cap",
                visited_nodes=visited,
                evaluated_assignments=evaluated,
            )
