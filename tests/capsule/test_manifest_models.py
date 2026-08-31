from __future__ import annotations

import hashlib
from copy import deepcopy
from math import inf, nan
from typing import Any

import pytest
from capsule_helpers import SHA_A, resolved_manifest_v2_payload, source_manifest_v2_payload
from pydantic import BaseModel, ValidationError

from laconian_eval import __version__
from laconian_eval.capsule.canonical import canonical_json
from laconian_eval.capsule.manifest_models import (
    ResolvedManifestV2,
    ResolvedPriceSnapshotV1,
    SourceManifestV2,
    project_v1_manifest,
)
from laconian_eval.capsule.planning import request_config_sha256


def _set_nested(payload: dict[str, Any], path: tuple[str | int, ...], value: object) -> None:
    current: Any = payload
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def _replace_price_evidence_value(payload: dict[str, Any], dimension: str, value: float) -> None:
    snapshot = payload["price_snapshot"]
    snapshot[dimension] = value
    evidence = next(item for item in snapshot["source_evidence"] if item["dimension"] == dimension)
    evidence["usd_per_million"] = value
    evidence_payload = {key: evidence[key] for key in tuple(evidence)[:-1]}
    evidence["source_sha256"] = hashlib.sha256(canonical_json(evidence_payload)).hexdigest()


def _replace_price_evidence_url(payload: dict[str, Any], value: str) -> None:
    snapshot = payload["price_snapshot"]
    snapshot["source_url"] = value
    for evidence in snapshot["source_evidence"]:
        evidence["source_url"] = value
        evidence_payload = {key: evidence[key] for key in tuple(evidence)[:-1]}
        evidence["source_sha256"] = hashlib.sha256(canonical_json(evidence_payload)).hexdigest()


def test_source_manifest_v2_round_trips_complete_shape() -> None:
    payload = source_manifest_v2_payload()

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.model_dump(mode="json") == payload
    assert list(manifest.model_dump().keys()) == [
        "schema_version",
        "runner_version",
        "run_name",
        "provider",
        "case_files",
        "arms",
        "repetitions",
        "arm_order_seed",
        "instruction_placement",
        "generation",
        "retry",
        "price_snapshot",
        "capsule",
    ]
    assert manifest.provider.model == " fixture-v1 "
    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.source_url == payload["price_snapshot"]["source_url"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="frozen"):
        manifest.repetitions = 3


def test_resolved_manifest_v2_round_trips_complete_shape() -> None:
    payload = resolved_manifest_v2_payload()

    manifest = ResolvedManifestV2.model_validate(payload)

    assert manifest.model_dump(mode="json") == payload
    assert list(manifest.model_dump().keys()) == [
        "schema_version",
        "source_manifest_schema_version",
        "runner_version",
        "run_name",
        "provider",
        "case_files",
        "arms",
        "repetitions",
        "arm_order_seed",
        "instruction_placement",
        "schedule_algorithm_version",
        "generation",
        "retry",
        "price_snapshot",
        "capsule",
    ]


@pytest.mark.parametrize(
    ("kind", "api_key_env", "replay_file"),
    [
        ("fake", None, None),
        ("replay", None, "fixtures/replay.jsonl"),
        ("openai", "OPENAI_API_KEY", None),
    ],
)
def test_provider_cross_rules_accept_valid_configurations(
    kind: str,
    api_key_env: str | None,
    replay_file: str | None,
) -> None:
    payload = source_manifest_v2_payload()
    payload["provider"] = {
        "kind": kind,
        "model": "model-v1",
        "api_key_env": api_key_env,
        "replay_file": replay_file,
    }

    assert SourceManifestV2.model_validate(payload).provider.kind == kind


@pytest.mark.parametrize(
    ("kind", "api_key_env", "replay_file"),
    [
        ("fake", "OPENAI_API_KEY", None),
        ("fake", None, "fixtures/replay.jsonl"),
        ("openai", None, None),
        ("openai", "lowercase", None),
        ("openai", "1OPENAI_API_KEY", None),
        ("openai", "OPENAI-API-KEY", None),
        ("openai", "A" * 129, None),
        ("openai", "OPENAI_API_KEY", "fixtures/replay.jsonl"),
        ("replay", None, None),
        ("replay", "OPENAI_API_KEY", "fixtures/replay.jsonl"),
    ],
)
def test_provider_cross_rules(
    kind: str,
    api_key_env: str | None,
    replay_file: str | None,
) -> None:
    payload = source_manifest_v2_payload()
    payload["provider"] = {
        "kind": kind,
        "model": "model-v1",
        "api_key_env": api_key_env,
        "replay_file": replay_file,
    }

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("repetitions",),
        ("arm_order_seed",),
        ("generation", "max_output_tokens"),
        ("retry", "max_transient_retries"),
        ("capsule", "datasets", 0, "case_file_ordinals", 0),
    ],
)
def test_source_manifest_rejects_boolean_integer_fields(path: tuple[str | int, ...]) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, path, True)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize("seed", [-(2**63), 2**63 - 1])
def test_arm_order_seed_accepts_signed_64_bit_bounds(seed: int) -> None:
    payload = source_manifest_v2_payload()
    payload["arm_order_seed"] = seed

    assert SourceManifestV2.model_validate(payload).arm_order_seed == seed


@pytest.mark.parametrize("seed", [-(2**63) - 1, 2**63])
def test_arm_order_seed_rejects_values_outside_signed_64_bit(seed: int) -> None:
    payload = source_manifest_v2_payload()
    payload["arm_order_seed"] = seed

    with pytest.raises(ValidationError, match="arm_order_seed"):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("repetitions",), 0),
        (("repetitions",), 101),
        (("generation", "max_output_tokens"), 0),
        (("generation", "max_output_tokens"), 65_537),
        (("retry", "max_transient_retries"), -1),
        (("retry", "max_transient_retries"), 6),
        (("retry", "timeout_seconds"), 0),
        (("retry", "timeout_seconds"), 600.1),
        (("generation", "temperature"), -0.1),
        (("generation", "temperature"), 2.1),
    ],
)
def test_operational_ranges_are_exact(path: tuple[str | int, ...], value: object) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, path, value)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("generation", "temperature"),
        ("retry", "timeout_seconds"),
    ],
)
@pytest.mark.parametrize("value", [True, nan, inf, -inf, "1.0", 10**1000])
def test_operational_float_fields_reject_non_numeric_or_nonfinite_values(
    path: tuple[str | int, ...], value: object
) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, path, value)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_source_manifest_materializes_existing_v1_defaults() -> None:
    payload = source_manifest_v2_payload()
    payload["price_snapshot"] = None
    for field in (
        "repetitions",
        "arm_order_seed",
        "instruction_placement",
        "generation",
        "retry",
    ):
        del payload[field]

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.repetitions == 1
    assert manifest.arm_order_seed == 0
    assert manifest.instruction_placement == "system_suffix"
    assert manifest.generation.model_dump(mode="json") == {
        "max_output_tokens": 1024,
        "temperature": None,
        "reasoning_effort": None,
        "text_verbosity": None,
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }
    assert manifest.retry.model_dump(mode="json") == {
        "max_transient_retries": 2,
        "timeout_seconds": 60.0,
    }
    assert manifest.price_snapshot is None


def test_numeric_float_fields_accept_integer_spelling_and_dump_as_floats() -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, ("generation", "temperature"), 1)
    _set_nested(payload, ("retry", "timeout_seconds"), 60)
    _replace_price_evidence_value(payload, "ordinary_uncached_input_per_million", 1.0)

    dumped = SourceManifestV2.model_validate(payload).model_dump(mode="json")

    assert dumped["generation"]["temperature"] == 1.0
    assert dumped["retry"]["timeout_seconds"] == 60.0
    assert dumped["price_snapshot"]["ordinary_uncached_input_per_million"] == 1.0
    assert type(dumped["generation"]["temperature"]) is float


def test_numeric_float_fields_normalize_negative_zero() -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, ("generation", "temperature"), -0.0)
    _set_nested(payload, ("retry", "timeout_seconds"), 60.0)
    _replace_price_evidence_value(payload, "ordinary_uncached_input_per_million", -0.0)

    dumped = SourceManifestV2.model_validate(payload).model_dump(mode="json")

    assert dumped["generation"]["temperature"] == 0.0
    assert dumped["price_snapshot"]["ordinary_uncached_input_per_million"] == 0.0
    assert str(dumped["generation"]["temperature"]) == "0.0"


@pytest.mark.parametrize(
    "exact_url",
    [
        "HTTP://EXAMPLE.test:80/prices/%7Ecurrent?b=2&a=1",
        "https://pricing_api.example/prices",
        "https://foo!bar.example/prices",
        "https://-service.example/prices",
        "https://foo..bar/prices",
        "https://999.999.999.999/prices",
        "https://[2001:db8::1]/prices",
        "https://[v1.fe80]/prices",
        "http://192.0.2.1/prices",
    ],
)
def test_price_url_is_exact_and_bounded(exact_url: str) -> None:
    payload = source_manifest_v2_payload()
    _replace_price_evidence_url(payload, exact_url)

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.source_url == exact_url
    assert manifest.model_dump(mode="json")["price_snapshot"]["source_url"] == exact_url
    assert type(manifest.price_snapshot.source_url) is str


@pytest.mark.parametrize(
    "url",
    [
        " https://example.test/prices",
        "https://example.test/prices ",
        "https://example.test/a b",
        "https://example.test/\nprices",
        "https://éxample.test/prices",
        "https://user@example.test/prices",
        "https://example.test/prices#fragment",
        "ftp://example.test/prices",
        "//example.test/prices",
        "https:///prices",
        "https://example.test:99999/prices",
        "https://example.test:/prices",
        "https://example.test/%ZZ",
        "https://example.test/{bad|path}",
        "https://example.test/prices?[bad]",
        "https://[127.0.0.1]/prices",
        "https://[v.fe80]/prices",
        "https://[v1.]/prices",
        "https://example.test/" + "x" * 1024,
    ],
)
def test_price_url_rejects_non_exact_http_urls(url: str) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, ("price_snapshot", "source_url"), url)

    with pytest.raises(ValidationError, match="source_url"):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize("effective_date", ["2026-02-30", "27-08-2026", "2026-8-27"])
def test_price_snapshot_rejects_invalid_exact_dates(effective_date: str) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, ("price_snapshot", "effective_date"), effective_date)

    with pytest.raises(ValidationError, match="effective_date"):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize("value", [None, -0.01, inf, -inf, nan, True, "1.0"])
@pytest.mark.parametrize(
    "field",
    [
        "ordinary_uncached_input_per_million",
        "cache_read_input_per_million",
        "cache_write_input_per_million",
        "visible_output_per_million",
        "reasoning_output_per_million",
    ],
)
def test_price_snapshot_rejects_invalid_prices(field: str, value: object) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, ("price_snapshot", field), value)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reasoning_effort", "minimal"),
        ("reasoning_effort", "xhigh"),
        ("text_verbosity", "minimal"),
        ("text_verbosity", "verbose"),
        ("reasoning_mode", None),
        ("reasoning_mode", "auto"),
        ("prompt_cache_mode", None),
        ("prompt_cache_mode", "implicit"),
        ("prompt_cache_ttl", None),
        ("prompt_cache_ttl", "1h"),
        ("service_tier", None),
        ("service_tier", True),
        ("service_tier", 1),
        ("service_tier", "auto"),
        ("service_tier", "flex"),
        ("service_tier", "priority"),
        ("service_tier", "ultrafast"),
    ],
)
def test_generation_request_policy_fields_are_strict(field: str, value: object) -> None:
    payload = source_manifest_v2_payload()
    payload["generation"][field] = value
    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_native_v2_round_trips_generation_request_policy() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    assert manifest.generation.model_dump(mode="json") == {
        "max_output_tokens": 2048,
        "temperature": 0.25,
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }


def test_price_snapshot_requires_five_sourced_dimensions() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.service_tier == "default"
    assert manifest.price_snapshot.cache_read_input_per_million == 0.125
    assert manifest.price_snapshot.cache_write_input_per_million == 1.5625
    assert manifest.price_snapshot.ordinary_uncached_input_per_million > 0
    assert manifest.price_snapshot.visible_output_per_million > 0
    assert manifest.price_snapshot.reasoning_output_per_million >= 0
    assert len(manifest.price_snapshot.source_evidence) == 5


@pytest.mark.parametrize(
    "mutation",
    [
        lambda evidence: evidence.pop(),
        lambda evidence: evidence.append(deepcopy(evidence[-1])),
        lambda evidence: evidence.reverse(),
        lambda evidence: evidence[0].update(dimension="cache_read_input_per_million"),
        lambda evidence: evidence[0].update(source_url="https://other.example/prices"),
        lambda evidence: evidence[0].update(effective_date="2026-08-28"),
        lambda evidence: evidence[0].update(usd_per_million=9.0),
        lambda evidence: evidence[0].update(source_sha256="0" * 64),
    ],
)
def test_price_source_evidence_requires_exact_order_and_self_binding(mutation: Any) -> None:
    payload = source_manifest_v2_payload()
    mutation(payload["price_snapshot"]["source_evidence"])
    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_price_evidence_may_have_independent_self_digested_provenance() -> None:
    payload = source_manifest_v2_payload()
    evidence = payload["price_snapshot"]["source_evidence"][0]
    evidence["source_url"] = "https://independent.example/source"
    evidence["effective_date"] = "2026-08-26"
    evidence["source_sha256"] = hashlib.sha256(
        canonical_json({key: evidence[key] for key in tuple(evidence)[:-1]})
    ).hexdigest()

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.source_evidence[0].source_url == evidence["source_url"]


@pytest.mark.parametrize("value", [None, True, 1, "auto", "flex", "priority", "ultrafast"])
def test_price_snapshot_service_tier_is_strict(value: object) -> None:
    payload = source_manifest_v2_payload()
    payload["price_snapshot"]["service_tier"] = value
    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_price_snapshot_digest_binds_literal_default_service_tier() -> None:
    snapshot = resolved_manifest_v2_payload()["price_snapshot"]
    encoded = canonical_json(snapshot)
    assert b'"service_tier":"default"' in encoded
    baseline_digest = hashlib.sha256(encoded).hexdigest()

    for replacement in (None, "flex"):
        forged = deepcopy(snapshot)
        if replacement is None:
            del forged["service_tier"]
        else:
            forged["service_tier"] = replacement
        assert hashlib.sha256(canonical_json(forged)).hexdigest() != baseline_digest
        with pytest.raises(ValidationError):
            ResolvedPriceSnapshotV1.model_validate(forged)


def test_cache_write_price_changes_manifest_but_not_request_configuration() -> None:
    baseline_payload = resolved_manifest_v2_payload()
    changed_payload = deepcopy(baseline_payload)
    _replace_price_evidence_value(changed_payload, "cache_write_input_per_million", 1.75)
    baseline = ResolvedManifestV2.model_validate(baseline_payload)
    changed = ResolvedManifestV2.model_validate(changed_payload)

    baseline_bytes = canonical_json(baseline.model_dump(mode="json"))
    changed_bytes = canonical_json(changed.model_dump(mode="json"))
    assert changed_bytes != baseline_bytes
    assert hashlib.sha256(changed_bytes).digest() != hashlib.sha256(baseline_bytes).digest()
    assert request_config_sha256(changed) == request_config_sha256(baseline)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../cases/input.yaml",
        "cases/../input.yaml",
        "cases//input.yaml",
        "./cases/input.yaml",
        "C:/cases/input.yaml",
        "C:\\cases\\input.yaml",
        "cases\\input.yaml",
        "",
    ],
)
def test_source_manifest_v2_rejects_non_normalized_relative_paths(path: str) -> None:
    payload = source_manifest_v2_payload()
    payload["case_files"] = [path, "cases/response-ru.yaml"]

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_dataset_partition_and_locale_declarations() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())

    assert [dataset.case_file_ordinals for dataset in manifest.capsule.datasets] == [(0,), (1,)]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["capsule"].update(datasets=[]),
        lambda payload: payload["capsule"]["datasets"][0].update(case_file_ordinals=[]),
        lambda payload: payload["capsule"]["datasets"][1].update(case_file_ordinals=[0]),
        lambda payload: payload["capsule"]["datasets"][1].update(case_file_ordinals=[2]),
        lambda payload: payload["capsule"]["datasets"][0].update(case_file_ordinals=[0, 0]),
        lambda payload: payload["capsule"]["datasets"][1].update(dataset_id="dataset-alpha"),
        lambda payload: payload["capsule"]["datasets"][0].update(dataset_id=" \t"),
        lambda payload: payload["capsule"]["datasets"][0].update(dataset_id="x" * 1025),
    ],
)
def test_dataset_ordinals_form_one_nonempty_partition(mutator: Any) -> None:
    payload = source_manifest_v2_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_dataset_partition_accepts_and_retains_declaration_order() -> None:
    payload = source_manifest_v2_payload()
    payload["capsule"]["datasets"] = [
        {
            "dataset_id": "dataset-alpha",
            "dataset_version": "2026-08-27",
            "role": "smoke",
            "case_schema_version": "1",
            "case_file_ordinals": [1, 0],
        }
    ]

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.capsule.datasets[0].case_file_ordinals == (1, 0)


def test_comparison_and_protocol_references() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())

    assert manifest.capsule.comparisons[0].comparison_id == "if-vs-concise"
    assert manifest.capsule.protocol_bindings[0].applies_at == ("scoring", "publication")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "rubric"),
        ("kind", ":rubric"),
        ("kind", "rubric:"),
        ("kind", "https://"),
        ("kind", ".example.rubric"),
        ("kind", "example..rubric"),
        ("kind", "example.rubric."),
        ("schema_id", "rubric-v1"),
        ("media_type", "not a media type"),
        ("media_type", "application"),
    ],
)
def test_protocol_binding_rejects_malformed_semantic_scalars(field: str, value: str) -> None:
    payload = source_manifest_v2_payload()
    payload["capsule"]["protocol_bindings"][0][field] = value

    with pytest.raises(ValidationError, match=field):
        SourceManifestV2.model_validate(payload)


def test_protocol_media_type_retains_exact_valid_parameters() -> None:
    payload = source_manifest_v2_payload()
    media_type = 'application/example+json; charset=utf-8; profile="v1"'
    payload["capsule"]["protocol_bindings"][0]["media_type"] = media_type

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.capsule.protocol_bindings[0].media_type == media_type


@pytest.mark.parametrize(
    ("kind", "schema_id"),
    [
        ("example:rubric", "example:rubric:v1"),
        ("urn:example:rubric", "urn:example:rubric:v1"),
        ("https://example.org/rubric", "https://example.org/rubric/v1"),
        ("org.example.rubric", "org.example.rubric.v1"),
    ],
)
def test_protocol_namespaces_accept_colon_and_uri_styles(kind: str, schema_id: str) -> None:
    payload = source_manifest_v2_payload()
    binding = payload["capsule"]["protocol_bindings"][0]
    binding["kind"] = kind
    binding["schema_id"] = schema_id

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.capsule.protocol_bindings[0].kind == kind
    assert manifest.capsule.protocol_bindings[0].schema_id == schema_id


@pytest.mark.parametrize("nested", ["provider", "protocol"])
def test_outer_manifest_revalidates_corrupted_nested_instances(nested: str) -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    payload = source_manifest_v2_payload()
    if nested == "provider":
        payload["provider"] = BaseModel.model_copy(
            manifest.provider,
            update={"model": 123},
        )
    else:
        binding = manifest.capsule.protocol_bindings[0]
        payload["capsule"]["protocol_bindings"][0] = BaseModel.model_copy(
            binding,
            update={"applies_at": ("publication", "scoring")},
        )

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_capsule_model_copy_validates_updates() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    corrupted_provider = BaseModel.model_copy(
        manifest.provider,
        update={"model": 123},
    )

    with pytest.raises(ValidationError, match="repetitions"):
        manifest.model_copy(update={"repetitions": True})
    with pytest.raises(ValidationError, match=r"provider\.model"):
        manifest.model_copy(update={"provider": corrupted_provider})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        manifest.model_copy(update={"unknown": "field"})

    copied = manifest.model_copy(update={"repetitions": 3})

    assert copied.repetitions == 3


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["capsule"]["comparisons"][0].update(right_arm="if"),
        lambda payload: payload["capsule"]["comparisons"][0].update(left_arm="caveman"),
        lambda payload: payload["capsule"]["comparisons"].append(
            {
                "comparison_id": "same-pair",
                "left_arm": "concise",
                "right_arm": "if",
                "role": "secondary",
            }
        ),
        lambda payload: payload["capsule"]["comparisons"].append(
            {
                "comparison_id": "second-primary",
                "left_arm": "baseline",
                "right_arm": "concise",
                "role": "primary",
            }
        ),
        lambda payload: payload["capsule"]["comparisons"].append(
            deepcopy(payload["capsule"]["comparisons"][0])
        ),
        lambda payload: payload["capsule"]["protocol_bindings"].append(
            deepcopy(payload["capsule"]["protocol_bindings"][0])
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0]["scope"].update(
            dataset_ids=[], comparison_ids=[]
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0]["scope"].update(
            dataset_ids=["missing-dataset"]
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0]["scope"].update(
            comparison_ids=["missing-comparison"]
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0].update(
            applies_at=["publication", "scoring"]
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0].update(
            applies_at=["scoring", "scoring"]
        ),
        lambda payload: payload["capsule"]["protocol_bindings"][0].update(applies_at=[]),
        lambda payload: payload["capsule"]["protocol_bindings"][0].update(
            bound_at_stage="post_generation"
        ),
    ],
)
def test_comparisons_and_protocols_reject_invalid_relationships(mutator: Any) -> None:
    payload = source_manifest_v2_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_v1_upgrade_defaults() -> None:
    legacy = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-smoke",
        "provider": {
            "kind": "fake",
            "model": "fixture-v1",
            "api_key_env": "IGNORED_API_KEY",
            "replay_file": "ignored/replay.jsonl",
        },
        "case_files": ["cases/en.yaml", "cases/ru.yaml"],
        "arms": ["if", "concise"],
    }

    upgraded = project_v1_manifest(legacy)

    assert upgraded.provider.api_key_env is None
    assert upgraded.provider.replay_file is None
    assert upgraded.repetitions == 1
    assert upgraded.arm_order_seed == 0
    assert upgraded.generation.model_dump(mode="json") == {
        "max_output_tokens": 1024,
        "temperature": None,
        "reasoning_effort": None,
        "text_verbosity": None,
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }
    assert upgraded.retry.model_dump(mode="json") == {
        "max_transient_retries": 2,
        "timeout_seconds": 60.0,
    }
    assert upgraded.capsule.model_dump(mode="json") == {
        "run_purpose": "integration_smoke",
        "claim_intent": "none",
        "datasets": [
            {
                "dataset_id": "legacy-smoke",
                "dataset_version": "unversioned",
                "role": "smoke",
                "case_schema_version": "1",
                "case_file_ordinals": [0, 1],
            }
        ],
        "comparisons": [
            {
                "comparison_id": "if-vs-concise",
                "left_arm": "if",
                "right_arm": "concise",
                "role": "contextual",
            }
        ],
        "protocol_bindings": [],
    }


def test_v1_authored_manifest_rejects_benchmark_reasoning_fields() -> None:
    legacy = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-smoke",
        "provider": {"kind": "fake", "model": "fixture-v1"},
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
        "generation": {
            "max_output_tokens": 1024,
            "temperature": None,
            "reasoning_effort": "medium",
        },
    }
    with pytest.raises(ValidationError):
        project_v1_manifest(legacy)


@pytest.mark.parametrize(
    ("kind", "api_key_env", "replay_file", "expected_api", "expected_replay"),
    [
        ("fake", "IGNORED_KEY", "ignored.jsonl", None, None),
        ("replay", "IGNORED_KEY", "fixture.jsonl", None, "fixture.jsonl"),
        ("openai", "OPENAI_API_KEY", "ignored.jsonl", "OPENAI_API_KEY", None),
    ],
)
def test_v1_upgrade_normalizes_ignored_provider_fields(
    kind: str,
    api_key_env: str | None,
    replay_file: str | None,
    expected_api: str | None,
    expected_replay: str | None,
) -> None:
    legacy = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-smoke",
        "provider": {
            "kind": kind,
            "model": "fixture-v1",
            "api_key_env": api_key_env,
            "replay_file": replay_file,
        },
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
    }

    upgraded = project_v1_manifest(legacy)

    assert upgraded.provider.api_key_env == expected_api
    assert upgraded.provider.replay_file == expected_replay


@pytest.mark.parametrize("kind", ["fake", "replay"])
def test_v1_upgrade_validates_ignored_api_key_environment_name(kind: str) -> None:
    legacy = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-smoke",
        "provider": {
            "kind": kind,
            "model": "fixture-v1",
            "api_key_env": "lowercase-invalid",
            "replay_file": "fixture.jsonl" if kind == "replay" else None,
        },
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
    }

    with pytest.raises(ValidationError, match="api_key_env"):
        project_v1_manifest(legacy)


def test_v1_projection_preserves_absolute_and_traversing_locators_until_capture() -> None:
    payload = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-replay",
        "provider": {
            "kind": "replay",
            "model": "replay-v1",
            "replay_file": "../fixtures/replay.jsonl",
        },
        "case_files": ["/absolute/cases/en.yaml", "../cases/ru.yaml"],
        "arms": ["baseline"],
    }

    projected = project_v1_manifest(payload)

    assert projected.case_files == ("/absolute/cases/en.yaml", "../cases/ru.yaml")
    assert projected.provider.replay_file == "../fixtures/replay.jsonl"


def test_v1_projection_retains_exact_price_url_before_capture() -> None:
    exact_url = "HTTP://EXAMPLE.test:80/prices/%7Ecurrent?b=2&a=1"
    payload = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-price",
        "provider": {"kind": "fake", "model": "fixture-v1"},
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
        "price_snapshot": {
            "effective_date": "2026-08-27",
            "source_url": exact_url,
            "input_per_million": 1,
            "output_per_million": 2,
        },
    }

    projected = project_v1_manifest(payload)

    assert projected.price_snapshot is not None
    assert projected.price_snapshot.source_url == exact_url


def test_v1_projection_rejects_booleans_before_legacy_coercion() -> None:
    payload = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-bool",
        "provider": {"kind": "fake", "model": "fixture-v1"},
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
        "repetitions": True,
    }

    with pytest.raises(ValidationError):
        project_v1_manifest(payload)


def test_source_manifest_v2_requires_current_runner_version() -> None:
    payload = source_manifest_v2_payload()
    payload["runner_version"] = "99.0.0"

    with pytest.raises(ValidationError, match="current runner version"):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("unknown",),
        ("provider", "unknown"),
        ("capsule", "datasets", 0, "unknown"),
        ("capsule", "protocol_bindings", 0, "scope", "unknown"),
    ],
)
def test_manifest_models_reject_unknown_fields(path: tuple[str | int, ...]) -> None:
    payload = source_manifest_v2_payload()
    _set_nested(payload, path, True)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        SourceManifestV2.model_validate(payload)


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64])
def test_resolved_manifest_rejects_noncanonical_hashes(digest: str) -> None:
    payload = resolved_manifest_v2_payload()
    payload["capsule"]["datasets"][0]["dataset_content_sha256"] = digest

    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)


def _resolved_v1_manifest_payload() -> dict[str, Any]:
    payload = resolved_manifest_v2_payload()
    payload["source_manifest_schema_version"] = "1"
    payload["generation"]["reasoning_effort"] = None
    payload["generation"]["text_verbosity"] = None
    payload["price_snapshot"] = None
    payload["capsule"]["datasets"] = [
        {
            "dataset_id": payload["run_name"],
            "dataset_version": "unversioned",
            "role": "smoke",
            "case_schema_version": "1",
            "case_file_ordinals": [0, 1],
            "dataset_content_sha256": SHA_A,
        }
    ]
    payload["capsule"]["comparisons"] = [
        {
            "comparison_id": "if-vs-concise",
            "left_arm": "if",
            "right_arm": "concise",
            "role": "contextual",
        }
    ]
    payload["capsule"]["protocol_bindings"] = []
    return payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("generation", "reasoning_effort"), "low"),
        (("generation", "text_verbosity"), "low"),
        (("price_snapshot",), resolved_manifest_v2_payload()["price_snapshot"]),
    ],
)
def test_resolved_v1_projection_rejects_native_v2_semantics(
    path: tuple[str, ...], value: object
) -> None:
    payload = _resolved_v1_manifest_payload()
    current = payload
    for component in path[:-1]:
        current = current[component]
    current[path[-1]] = value

    with pytest.raises(ValidationError, match="v1 source marker"):
        ResolvedManifestV2.model_validate(payload)


def _add_resolved_protocol_to_v1_projection(payload: dict[str, Any]) -> None:
    binding = deepcopy(resolved_manifest_v2_payload()["capsule"]["protocol_bindings"][0])
    binding["scope"]["dataset_ids"] = [payload["run_name"]]
    payload["capsule"]["protocol_bindings"] = [binding]


def test_resolved_manifest_accepts_exact_source_v1_projection_and_future_runner() -> None:
    payload = _resolved_v1_manifest_payload()
    payload["runner_version"] = "99.4.0-future"

    manifest = ResolvedManifestV2.model_validate(payload)

    assert manifest.source_manifest_schema_version == "1"
    assert manifest.runner_version == "99.4.0-future"


def test_resolved_v1_projection_omits_comparison_without_both_arms() -> None:
    payload = _resolved_v1_manifest_payload()
    payload["arms"] = ["baseline"]
    payload["capsule"]["comparisons"] = []

    manifest = ResolvedManifestV2.model_validate(payload)

    assert manifest.capsule.comparisons == ()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["capsule"].update(run_purpose="development"),
        lambda payload: payload["capsule"].update(claim_intent="exploratory"),
        lambda payload: payload["capsule"].update(
            datasets=deepcopy(resolved_manifest_v2_payload()["capsule"]["datasets"])
        ),
        lambda payload: payload["capsule"]["datasets"][0].update(dataset_id="other-dataset"),
        lambda payload: payload["capsule"]["datasets"][0].update(dataset_version="versioned"),
        lambda payload: payload["capsule"]["datasets"][0].update(role="development"),
        lambda payload: payload["capsule"].update(comparisons=[]),
        lambda payload: payload["capsule"]["comparisons"][0].update(role="primary"),
        lambda payload: payload["capsule"]["comparisons"].append(
            {
                "comparison_id": "baseline-vs-concise",
                "left_arm": "baseline",
                "right_arm": "concise",
                "role": "secondary",
            }
        ),
        _add_resolved_protocol_to_v1_projection,
    ],
)
def test_resolved_v1_marker_requires_exact_upgrade_projection(mutator: Any) -> None:
    payload = _resolved_v1_manifest_payload()
    mutator(payload)

    with pytest.raises(ValidationError, match="v1 source marker"):
        ResolvedManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("provider", "api_key_env"),
        ("provider", "replay_file"),
        ("generation", "temperature"),
        ("price_snapshot",),
        ("generation", "reasoning_effort"),
        ("generation", "text_verbosity"),
        ("generation", "reasoning_mode"),
        ("generation", "prompt_cache_mode"),
        ("generation", "prompt_cache_ttl"),
        ("generation", "service_tier"),
        ("price_snapshot", "service_tier"),
        ("price_snapshot", "ordinary_uncached_input_per_million"),
        ("price_snapshot", "cache_read_input_per_million"),
        ("price_snapshot", "cache_write_input_per_million"),
        ("price_snapshot", "visible_output_per_million"),
        ("price_snapshot", "reasoning_output_per_million"),
        ("price_snapshot", "source_evidence"),
    ],
)
def test_optional_serialized_resolved_fields_require_explicit_null(
    path: tuple[str, ...],
) -> None:
    payload = resolved_manifest_v2_payload()
    current = payload
    for part in path[:-1]:
        current = current[part]
    del current[path[-1]]

    with pytest.raises(ValidationError, match=path[-1]):
        ResolvedManifestV2.model_validate(payload)


def test_nullable_source_fields_materialize_v1_defaults() -> None:
    payload = source_manifest_v2_payload()
    del payload["price_snapshot"]
    del payload["provider"]["api_key_env"]
    del payload["provider"]["replay_file"]
    del payload["generation"]["temperature"]

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.price_snapshot is None
    assert manifest.provider.api_key_env is None
    assert manifest.provider.replay_file is None
    assert manifest.generation.temperature is None
    dumped = manifest.model_dump(mode="json")
    assert dumped["price_snapshot"] is None
    assert dumped["provider"]["api_key_env"] is None
    assert dumped["provider"]["replay_file"] is None
    assert dumped["generation"]["temperature"] is None


def test_source_generation_policy_materializes_literal_defaults() -> None:
    payload = source_manifest_v2_payload()
    for field in ("prompt_cache_mode", "prompt_cache_ttl", "service_tier"):
        del payload["generation"][field]

    dumped = SourceManifestV2.model_validate(payload).model_dump(mode="json")

    assert dumped["generation"]["prompt_cache_mode"] == "explicit"
    assert dumped["generation"]["prompt_cache_ttl"] == "30m"
    assert dumped["generation"]["service_tier"] == "default"


def test_source_price_snapshot_materializes_default_service_tier() -> None:
    payload = source_manifest_v2_payload()
    del payload["price_snapshot"]["service_tier"]

    manifest = SourceManifestV2.model_validate(payload)

    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.service_tier == "default"


def test_resolved_manifest_rejects_host_paths() -> None:
    payload = resolved_manifest_v2_payload()
    payload["case_files"][0] = "/host/cases/000.yaml"

    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "inputs/cases/001.yaml",
        "captured/cases/000.yaml",
        "inputs/cases/000.yml",
    ],
)
def test_resolved_manifest_requires_fixed_case_destinations(path: str) -> None:
    payload = resolved_manifest_v2_payload()
    payload["case_files"][0] = path

    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)


def test_resolved_manifest_requires_fixed_protocol_destination() -> None:
    payload = resolved_manifest_v2_payload()
    payload["capsule"]["protocol_bindings"][0]["path"] = "inputs/protocols/000.bin"

    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)


def test_resolved_replay_manifest_uses_fixed_capsule_path() -> None:
    payload = resolved_manifest_v2_payload()
    payload["provider"] = {
        "kind": "replay",
        "model": "replay-v1",
        "api_key_env": None,
        "replay_file": "inputs/provider/replay.yaml",
    }

    manifest = ResolvedManifestV2.model_validate(payload)

    assert manifest.provider.replay_file == "inputs/provider/replay.yaml"


def test_public_price_dimensions_are_never_nullable() -> None:
    payload = source_manifest_v2_payload()
    payload["price_snapshot"]["cache_read_input_per_million"] = None

    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_zero_price_is_allowed_only_with_exact_evidence() -> None:
    payload = source_manifest_v2_payload()
    _replace_price_evidence_value(payload, "reasoning_output_per_million", 0.0)
    manifest = SourceManifestV2.model_validate(payload)
    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.reasoning_output_per_million == 0.0


def test_resolved_protocol_integrity_fields_are_strict() -> None:
    payload = resolved_manifest_v2_payload()
    payload["capsule"]["protocol_bindings"][0]["byte_length"] = True

    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)

    payload = resolved_manifest_v2_payload()
    payload["capsule"]["protocol_bindings"][0]["sha256"] = SHA_A.upper()
    with pytest.raises(ValidationError):
        ResolvedManifestV2.model_validate(payload)
