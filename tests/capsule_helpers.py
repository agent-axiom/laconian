"""Complete valid payloads shared by capsule schema tests."""

from __future__ import annotations

import hashlib
from typing import Any

from laconian_eval import __version__
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
UUID_A = "123e4567-e89b-42d3-a456-426614174000"
UUID_B = "223e4567-e89b-42d3-a456-426614174001"
CANONICAL_TIMESTAMP = "2026-08-27T12:34:56.123456Z"


def source_manifest_v2_payload() -> dict[str, Any]:
    source_url = "HTTPS://Pricing.Example.test:443/v1?b=2&a=1"
    effective_date = "2026-08-27"
    rates = {
        "ordinary_uncached_input_per_million": 1.25,
        "cache_read_input_per_million": 0.125,
        "cache_write_input_per_million": 1.5625,
        "visible_output_per_million": 10.0,
        "reasoning_output_per_million": 12.5,
    }
    evidence = []
    for dimension, rate in rates.items():
        evidence_payload = {
            "dimension": dimension,
            "source_url": source_url,
            "effective_date": effective_date,
            "usd_per_million": rate,
        }
        evidence.append(
            evidence_payload
            | {"source_sha256": hashlib.sha256(canonical_json(evidence_payload)).hexdigest()}
        )
    return {
        "schema_version": "2",
        "runner_version": __version__,
        "run_name": "schema-smoke",
        "provider": {
            "kind": "fake",
            "model": " fixture-v1 ",
            "api_key_env": None,
            "replay_file": None,
        },
        "case_files": ["cases/response-en.yaml", "cases/response-ru.yaml"],
        "arms": ["baseline", "concise", "if"],
        "repetitions": 2,
        "arm_order_seed": -17,
        "instruction_placement": "system_suffix",
        "generation": {
            "max_output_tokens": 2048,
            "temperature": 0.25,
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        },
        "retry": {"max_transient_retries": 2, "timeout_seconds": 60.0},
        "price_snapshot": {
            "currency": "USD",
            "effective_date": effective_date,
            "source_url": source_url,
            "service_tier": "default",
            **rates,
            "source_evidence": evidence,
        },
        "capsule": {
            "run_purpose": "integration_smoke",
            "claim_intent": "none",
            "datasets": [
                {
                    "dataset_id": "dataset-alpha",
                    "dataset_version": "2026-08-27",
                    "role": "smoke",
                    "case_schema_version": "1",
                    "case_file_ordinals": [0],
                },
                {
                    "dataset_id": "dataset-beta",
                    "dataset_version": "2026-08-27",
                    "role": "challenge",
                    "case_schema_version": "1",
                    "case_file_ordinals": [1],
                },
            ],
            "comparisons": [
                {
                    "comparison_id": "if-vs-concise",
                    "left_arm": "if",
                    "right_arm": "concise",
                    "role": "primary",
                }
            ],
            "protocol_bindings": [
                {
                    "binding_id": "rubric-v1",
                    "kind": "example.org/evaluation-rubric",
                    "schema_id": "example.org/evaluation-rubric/v1",
                    "media_type": "application/json",
                    "path": "protocols/rubric.json",
                    "scope": {
                        "dataset_ids": ["dataset-alpha"],
                        "comparison_ids": ["if-vs-concise"],
                    },
                    "bound_at_stage": "pre_generation",
                    "applies_at": ["scoring", "publication"],
                    "declared_requirement": "required_for_declared_claim",
                }
            ],
        },
    }


def resolved_manifest_v2_payload() -> dict[str, Any]:
    payload = source_manifest_v2_payload()
    payload["source_manifest_schema_version"] = "2"
    payload["schedule_algorithm_version"] = "laconian-schedule-v1"
    payload["case_files"] = ["inputs/cases/000.yaml", "inputs/cases/001.yaml"]
    capsule = payload["capsule"]
    assert isinstance(capsule, dict)
    datasets = capsule["datasets"]
    assert isinstance(datasets, list)
    datasets[0]["dataset_content_sha256"] = SHA_A
    datasets[1]["dataset_content_sha256"] = SHA_B
    bindings = capsule["protocol_bindings"]
    assert isinstance(bindings, list)
    bindings[0]["path"] = "inputs/protocols/000-2d87d3cff7414ba1.bin"
    bindings[0]["byte_length"] = 321
    bindings[0]["sha256"] = SHA_C
    return payload


def capsule_v1_payload() -> dict[str, Any]:
    return {
        "capsule_schema_version": "1",
        "attempt_schema_version": "2",
        "event_schema_version": "1",
        "resolved_manifest_schema_version": "2",
        "resource_limits_version": "1",
        "canonicalization_version": "laconian-json-v1",
        "sanitizer_version": "laconian-sanitizer-v1",
        "runner_version": __version__,
        "run_id": UUID_A,
        "created_at": CANONICAL_TIMESTAMP,
        "run_purpose": "integration_smoke",
        "claim_intent": "none",
        "schedule_algorithm_version": "laconian-schedule-v1",
        "arm_order_seed": -17,
        "source_manifest_commitment_sha256": SHA_A,
        "manifest_sha256": SHA_B,
        "input_index_sha256": SHA_C,
        "case_index_sha256": SHA_D,
        "plan_sha256": SHA_E,
        "environment_sha256": SHA_F,
        "runner_source_sha256": "0" * 64,
    }


def input_index_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "manifest_sha256": SHA_A,
        "files": [
            {
                "role": "arm",
                "role_ordinal": 0,
                "logical_locator": "arm[baseline]/baseline.txt",
                "capsule_path": "inputs/arms/baseline.txt",
                "byte_length": 0,
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "dataset_id": None,
                "binding_id": None,
            },
            {
                "role": "case",
                "role_ordinal": 0,
                "logical_locator": "case_files[0]",
                "capsule_path": "inputs/cases/000.yaml",
                "byte_length": 123,
                "sha256": SHA_B,
                "dataset_id": "dataset-alpha",
                "binding_id": None,
            },
            {
                "role": "protocol",
                "role_ordinal": 0,
                "logical_locator": "capsule.protocol_bindings[0].path",
                "capsule_path": "inputs/protocols/000-2d87d3cff7414ba1.bin",
                "byte_length": 321,
                "sha256": SHA_C,
                "dataset_id": None,
                "binding_id": "rubric-v1",
            },
            {
                "role": "runner_source",
                "role_ordinal": 0,
                "logical_locator": "package[laconian_eval]/__init__.py",
                "capsule_path": "inputs/software/runner/laconian_eval/__init__.py",
                "byte_length": 45,
                "sha256": SHA_D,
                "dataset_id": None,
                "binding_id": None,
            },
        ],
    }


def planning_input_records_v1_payload(
    parent_plan_bytes: bytes,
    shard_plan_bytes: bytes,
) -> list[dict[str, Any]]:
    """Return the exact optional planning-input pair for one shard capsule."""

    return [
        {
            "role": "parent_plan",
            "role_ordinal": 0,
            "logical_locator": "preflight.parent_plan",
            "capsule_path": "inputs/planning/parent-plan.jsonl",
            "byte_length": len(parent_plan_bytes),
            "sha256": sha256_bytes(parent_plan_bytes),
            "dataset_id": None,
            "binding_id": None,
        },
        {
            "role": "shard_plan",
            "role_ordinal": 0,
            "logical_locator": "preflight.shard_plan",
            "capsule_path": "inputs/planning/shard-plan.json",
            "byte_length": len(shard_plan_bytes),
            "sha256": sha256_bytes(shard_plan_bytes),
            "dataset_id": None,
            "binding_id": None,
        },
    ]


def case_index_row_v1_payload() -> dict[str, Any]:
    return {
        "dataset_id": "dataset-alpha",
        "dataset_version": "2026-08-27",
        "dataset_role": "smoke",
        "source_ordinal": 0,
        "record_ordinal": 0,
        "case_id": "direct-001-en",
        "case_uid": SHA_A,
        "scenario_id": "direct-001",
        "scenario_uid": SHA_B,
        "locale": "en",
        "category": "direct",
        "case_definition_sha256": SHA_C,
        "prompt_sha256": SHA_D,
        "prompt_utf8_bytes": 42,
    }


def plan_row_v1_payload() -> dict[str, Any]:
    return {
        "ordinal": 0,
        "plan_item_id": SHA_A,
        "pairing_unit_id": SHA_B,
        "case_uid": SHA_C,
        "scenario_uid": SHA_D,
        "case_id": "direct-001-en",
        "locale": "en",
        "repetition": 0,
        "arm": "baseline",
        "block_id": SHA_E,
        "arm_position": 0,
        "prompt_sha256": SHA_F,
        "case_definition_sha256": "0" * 64,
        "instruction_sha256": "1" * 64,
        "request_config_sha256": "2" * 64,
        "input_token_bound": 65_578,
    }


def runner_source_index_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "package_name": "laconian-eval",
        "files": [
            {"path": "__init__.py", "byte_length": 45, "sha256": SHA_A},
            {"path": "providers/fake.py", "byte_length": 900, "sha256": SHA_B},
        ],
        "runner_source_sha256": SHA_C,
    }


def environment_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "canonical_repository_url": "https://github.com/agent-axiom/laconian",
        "checkout_binding": "bound",
        "git_commit": "a" * 40,
        "git_state": "clean",
        "uv_lock": {"availability": "present", "sha256": SHA_A},
        "package_name": "laconian-eval",
        "package_version": __version__,
        "runner_source_sha256": SHA_B,
        "runtime": {
            "python_implementation": "CPython",
            "python_version": "3.11.13 (main, Aug 27 2026, 12:00:00) [Clang 18.0.0]",
            "os_family": "Darwin",
            "os_release": "25.6.0",
            "architecture": "arm64",
            "filesystem_class": "apfs",
            "dependencies": [
                {"distribution": "packaging", "version": "26.0", "files_sha256": SHA_A},
                {"distribution": "pydantic", "version": "2.12.5", "files_sha256": SHA_B},
                {
                    "distribution": "pydantic-core",
                    "version": "2.41.5",
                    "files_sha256": SHA_C,
                },
                {"distribution": "pyyaml", "version": "6.0.2", "files_sha256": SHA_D},
            ],
            "import_environment": {
                "import_policy_version": "laconian-import-policy-v1",
                "stdlib_origin_policy": "interpreter-layout-v1",
                "stdlib_extension_policy": "destshared-v1",
                "platstdlib_mode": "same_as_stdlib",
                "guard_source_sha256": SHA_A,
                "audit_hook_source_sha256": SHA_A,
                "runner_import_mode": "wheel",
                "launcher_mode": "module",
                "launcher_template_sha256": None,
                "virtualenv_bootstrap_sha256": None,
                "import_roots": [
                    {
                        "distribution": "packaging",
                        "module": "packaging",
                        "origin_member": "packaging/__init__.py",
                    },
                    {
                        "distribution": "pydantic",
                        "module": "pydantic",
                        "origin_member": "pydantic/__init__.py",
                    },
                    {
                        "distribution": "pydantic-core",
                        "module": "pydantic_core",
                        "origin_member": "pydantic_core/__init__.py",
                    },
                    {
                        "distribution": "pyyaml",
                        "module": "yaml",
                        "origin_member": "yaml/__init__.py",
                    },
                ],
            },
            "runtime_fingerprint_sha256": SHA_E,
        },
        "provider": {
            "kind": "fake",
            "requested_model": "fixture-v1",
            "adapter_source_sha256": SHA_F,
            "transport_policy": "offline",
            "sdk_distribution": None,
            "sdk_version": None,
        },
        "container_image_digest": None,
    }


def session_environment_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "package_version": __version__,
        "runner_source_sha256": SHA_A,
        "runtime_fingerprint_sha256": SHA_B,
        "python_implementation": "CPython",
        "python_version": "3.11.13 (main, Aug 27 2026, 12:00:00) [Clang 18.0.0]",
        "os_family": "Darwin",
        "os_release": "25.6.0",
        "architecture": "arm64",
        "filesystem_class": "apfs",
        "adapter_source_sha256": SHA_C,
        "sdk_distribution": None,
        "sdk_version": None,
    }


def prepared_event_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "sequence": 0,
        "event_id": SHA_A,
        "run_id": UUID_A,
        "occurred_at": CANONICAL_TIMESTAMP,
        "kind": "prepared",
        "operation_id": UUID_B,
        "execution_session_id": None,
        "payload": {
            "manifest_sha256": SHA_B,
            "input_index_sha256": SHA_C,
            "case_index_sha256": SHA_D,
            "plan_sha256": SHA_E,
            "environment_sha256": SHA_F,
            "runner_source_sha256": "0" * 64,
        },
    }


def verify_result_v1_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "status": "valid",
        "run_id": UUID_A,
        "state": "PREPARED",
        "capsule_sha256": None,
        "missing_plan_item_ids": [SHA_A, SHA_B],
        "operational_blocker_codes": ["never_started"],
        "warnings": ["broader_permissions", "producer_runtime_differs"],
        "first_error": None,
    }
