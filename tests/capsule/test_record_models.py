from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from capsule_helpers import (
    CANONICAL_TIMESTAMP,
    SHA_A,
    SHA_B,
    UUID_A,
    capsule_v1_payload,
    case_index_row_v1_payload,
    environment_v1_payload,
    input_index_v1_payload,
    plan_row_v1_payload,
    prepared_event_v1_payload,
    runner_source_index_v1_payload,
    session_environment_v1_payload,
    verify_result_v1_payload,
)
from pydantic import BaseModel, ValidationError

from laconian_eval import __version__
from laconian_eval.capsule import manifest_models, record_models, schema
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    CaseIndexRowV1,
    EnvironmentV1,
    InputIndexV1,
    PlanRowV1,
    PreparedEventV1,
    RunnerSourceIndexV1,
    SessionEnvironmentV1,
    VerifyResultV1,
)


def _set_nested(payload: dict[str, Any], path: tuple[str | int, ...], value: object) -> None:
    current: Any = payload
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def test_capsule_v1_complete_shape() -> None:
    payload = capsule_v1_payload()

    capsule = CapsuleV1.model_validate(payload)

    assert capsule.model_dump(mode="json") == payload
    assert list(capsule.model_dump().keys()) == [
        "capsule_schema_version",
        "attempt_schema_version",
        "event_schema_version",
        "resolved_manifest_schema_version",
        "resource_limits_version",
        "canonicalization_version",
        "sanitizer_version",
        "runner_version",
        "run_id",
        "created_at",
        "run_purpose",
        "claim_intent",
        "schedule_algorithm_version",
        "arm_order_seed",
        "source_manifest_commitment_sha256",
        "manifest_sha256",
        "input_index_sha256",
        "case_index_sha256",
        "plan_sha256",
        "environment_sha256",
        "runner_source_sha256",
    ]
    assert capsule.created_at == datetime(2026, 8, 27, 12, 34, 56, 123456, tzinfo=UTC)


def test_future_runner_version_is_readable() -> None:
    payload = capsule_v1_payload()
    payload["runner_version"] = "99.12.3-future+producer"

    capsule = CapsuleV1.model_validate(payload)

    assert capsule.runner_version == "99.12.3-future+producer"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "123e4567-e89b-12d3-a456-426614174000"),
        ("run_id", UUID_A.upper()),
        ("created_at", "2026-08-27T12:34:56Z"),
        ("created_at", "2026-08-27T12:34:56.123456+00:00"),
        ("created_at", "2026-08-27T12:34:56.123456z"),
        ("arm_order_seed", True),
        ("arm_order_seed", 2**63),
        ("run_purpose", "benchmark"),
        ("claim_intent", "confirmatory"),
        ("runner_version", " \t"),
        ("runner_version", "x" * 1025),
    ],
)
def test_capsule_rejects_invalid_identity_fields(field: str, value: object) -> None:
    payload = capsule_v1_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        CapsuleV1.model_validate(payload)


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64])
def test_capsule_rejects_noncanonical_hashes(digest: str) -> None:
    payload = capsule_v1_payload()
    payload["manifest_sha256"] = digest

    with pytest.raises(ValidationError, match="manifest_sha256"):
        CapsuleV1.model_validate(payload)


def test_static_index_rows_are_strict() -> None:
    input_payload = input_index_v1_payload()
    case_payload = case_index_row_v1_payload()
    plan_payload = plan_row_v1_payload()

    assert InputIndexV1.model_validate(input_payload).model_dump(mode="json") == input_payload
    assert CaseIndexRowV1.model_validate(case_payload).model_dump(mode="json") == case_payload
    assert PlanRowV1.model_validate(plan_payload).model_dump(mode="json") == plan_payload
    assert list(CaseIndexRowV1.model_validate(case_payload).model_dump().keys()) == [
        "dataset_id",
        "dataset_version",
        "dataset_role",
        "source_ordinal",
        "record_ordinal",
        "case_id",
        "case_uid",
        "scenario_id",
        "scenario_uid",
        "locale",
        "category",
        "case_definition_sha256",
        "prompt_sha256",
    ]
    assert list(PlanRowV1.model_validate(plan_payload).model_dump().keys()) == [
        "ordinal",
        "plan_item_id",
        "pairing_unit_id",
        "case_uid",
        "scenario_uid",
        "case_id",
        "locale",
        "repetition",
        "arm",
        "block_id",
        "arm_position",
        "prompt_sha256",
        "case_definition_sha256",
        "instruction_sha256",
        "request_config_sha256",
    ]


@pytest.mark.parametrize(
    ("model", "factory", "path"),
    [
        (CapsuleV1, capsule_v1_payload, ("arm_order_seed",)),
        (InputIndexV1, input_index_v1_payload, ("files", 0, "role_ordinal")),
        (InputIndexV1, input_index_v1_payload, ("files", 0, "byte_length")),
        (CaseIndexRowV1, case_index_row_v1_payload, ("source_ordinal",)),
        (CaseIndexRowV1, case_index_row_v1_payload, ("record_ordinal",)),
        (PlanRowV1, plan_row_v1_payload, ("ordinal",)),
        (PlanRowV1, plan_row_v1_payload, ("repetition",)),
        (PlanRowV1, plan_row_v1_payload, ("arm_position",)),
        (RunnerSourceIndexV1, runner_source_index_v1_payload, ("files", 0, "byte_length")),
        (PreparedEventV1, prepared_event_v1_payload, ("sequence",)),
    ],
)
def test_record_models_reject_boolean_integer_fields(
    model: type[BaseModel],
    factory: Any,
    path: tuple[str | int, ...],
) -> None:
    payload = factory()
    _set_nested(payload, path, True)

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("files", 0, "role_ordinal"), -1),
        (("files", 0, "byte_length"), -1),
        (("files", 1, "dataset_id"), None),
        (("files", 1, "binding_id"), "rubric-v1"),
        (("files", 2, "dataset_id"), "dataset-alpha"),
        (("files", 2, "binding_id"), None),
        (("files", 0, "dataset_id"), "dataset-alpha"),
        (("files", 0, "logical_locator"), "arm[missing]/SKILL.md"),
        (("files", 0, "capsule_path"), "inputs/arms/baseline/SKILL.md"),
        (("files", 1, "logical_locator"), "case_files[1]"),
        (("files", 2, "logical_locator"), "capsule.protocol_bindings[1].path"),
        (("files", 0, "capsule_path"), "../escape"),
    ],
)
def test_input_index_enforces_file_role_contracts(
    path: tuple[str | int, ...], value: object
) -> None:
    payload = input_index_v1_payload()
    _set_nested(payload, path, value)

    with pytest.raises(ValidationError):
        InputIndexV1.model_validate(payload)


def test_input_index_requires_sorted_unique_paths() -> None:
    payload = input_index_v1_payload()
    payload["files"] = list(reversed(payload["files"]))
    with pytest.raises(ValidationError):
        InputIndexV1.model_validate(payload)


def test_runner_source_role_ordinals_follow_sorted_inventory() -> None:
    payload = input_index_v1_payload()
    payload["files"][-1]["role_ordinal"] = 1
    payload["files"].append(
        {
            "role": "runner_source",
            "role_ordinal": 0,
            "logical_locator": "package[laconian_eval]/providers/fake.py",
            "capsule_path": "inputs/software/runner/laconian_eval/providers/fake.py",
            "byte_length": 900,
            "sha256": SHA_A,
            "dataset_id": None,
            "binding_id": None,
        }
    )

    with pytest.raises(ValidationError, match="runner_source role ordinals"):
        InputIndexV1.model_validate(payload)

    payload = input_index_v1_payload()
    payload["files"][1]["capsule_path"] = payload["files"][0]["capsule_path"]
    with pytest.raises(ValidationError):
        InputIndexV1.model_validate(payload)


@pytest.mark.parametrize("role", ["case", "arm", "runner_source"])
def test_input_index_requires_core_immutable_roles(role: str) -> None:
    payload = input_index_v1_payload()
    payload["files"] = [record for record in payload["files"] if record["role"] != role]

    with pytest.raises(ValidationError):
        InputIndexV1.model_validate(payload)


@pytest.mark.parametrize(
    ("factory", "model", "field", "value"),
    [
        (case_index_row_v1_payload, CaseIndexRowV1, "case_id", "direct-001"),
        (case_index_row_v1_payload, CaseIndexRowV1, "scenario_id", "Direct-001"),
        (case_index_row_v1_payload, CaseIndexRowV1, "locale", "fr"),
        (case_index_row_v1_payload, CaseIndexRowV1, "category", "translation"),
        (case_index_row_v1_payload, CaseIndexRowV1, "case_uid", "A" * 64),
        (plan_row_v1_payload, PlanRowV1, "ordinal", -1),
        (plan_row_v1_payload, PlanRowV1, "repetition", -1),
        (plan_row_v1_payload, PlanRowV1, "arm_position", -1),
        (plan_row_v1_payload, PlanRowV1, "arm", "verbose"),
        (plan_row_v1_payload, PlanRowV1, "request_config_sha256", "1" * 63),
    ],
)
def test_case_and_plan_rows_reject_invalid_scalars(
    factory: Any, model: type[BaseModel], field: str, value: object
) -> None:
    payload = factory()
    payload[field] = value

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_runner_source_index_v1_round_trips_complete_shape() -> None:
    payload = runner_source_index_v1_payload()

    index = RunnerSourceIndexV1.model_validate(payload)

    assert index.model_dump(mode="json") == payload
    assert list(index.model_dump().keys()) == [
        "schema_version",
        "package_name",
        "files",
        "runner_source_sha256",
    ]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(files=[]),
        lambda payload: payload["files"].reverse(),
        lambda payload: payload["files"][1].update(path="__init__.py"),
        lambda payload: payload["files"][0].update(path="../__init__.py"),
        lambda payload: payload["files"][0].update(path="README.md"),
        lambda payload: payload["files"][0].update(byte_length=-1),
        lambda payload: payload["files"][0].update(sha256="A" * 64),
    ],
)
def test_runner_source_index_rejects_invalid_inventory(mutator: Any) -> None:
    payload = runner_source_index_v1_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        RunnerSourceIndexV1.model_validate(payload)


def test_environment_v1_round_trips_complete_shape() -> None:
    payload = environment_v1_payload()

    environment = EnvironmentV1.model_validate(payload)

    assert environment.model_dump(mode="json") == payload
    assert list(environment.model_dump().keys()) == [
        "schema_version",
        "canonical_repository_url",
        "checkout_binding",
        "git_commit",
        "git_state",
        "uv_lock",
        "package_name",
        "package_version",
        "runner_source_sha256",
        "runtime",
        "provider",
        "container_image_digest",
    ]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["uv_lock"].update(availability="present", sha256=None),
        lambda payload: payload["uv_lock"].update(availability="unavailable", sha256=SHA_A),
        lambda payload: payload.update(checkout_binding="unbound"),
        lambda payload: payload.update(checkout_binding="unavailable"),
        lambda payload: payload.update(git_state="unavailable"),
        lambda payload: payload["runtime"]["dependencies"].reverse(),
        lambda payload: payload["runtime"]["dependencies"].append(
            deepcopy(payload["runtime"]["dependencies"][0])
        ),
        lambda payload: payload["runtime"]["dependencies"][0].update(distribution="Packaging"),
        lambda payload: payload["runtime"]["import_environment"]["import_roots"].reverse(),
        lambda payload: payload["runtime"]["import_environment"]["import_roots"].append(
            deepcopy(payload["runtime"]["import_environment"]["import_roots"][0])
        ),
        lambda payload: payload["runtime"]["import_environment"].update(
            launcher_mode="console_script", launcher_template_sha256=None
        ),
        lambda payload: payload["runtime"]["import_environment"].update(
            launcher_mode="module", launcher_template_sha256=SHA_A
        ),
    ],
)
def test_environment_enforces_nested_provenance_relationships(mutator: Any) -> None:
    payload = environment_v1_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        EnvironmentV1.model_validate(payload)


def test_bound_checkout_allows_unavailable_git_and_lock_attribution() -> None:
    payload = environment_v1_payload()
    payload["git_state"] = "unavailable"
    payload["git_commit"] = None
    payload["uv_lock"] = {"availability": "unavailable", "sha256": None}

    environment = EnvironmentV1.model_validate(payload)

    assert environment.checkout_binding == "bound"
    assert environment.git_commit is None


@pytest.mark.parametrize("binding", ["unbound", "unavailable"])
def test_unbound_checkout_requires_null_unavailable_attribution(binding: str) -> None:
    payload = environment_v1_payload()
    payload["checkout_binding"] = binding
    payload["git_state"] = "unavailable"
    payload["git_commit"] = None
    payload["uv_lock"] = {"availability": "unavailable", "sha256": None}

    assert EnvironmentV1.model_validate(payload).checkout_binding == binding


@pytest.mark.parametrize(
    ("kind", "transport", "sdk_distribution", "sdk_version"),
    [
        ("fake", "offline", None, None),
        ("replay", "offline", None, None),
        ("openai", "openai-direct-v1", "openai", "3.3.1"),
    ],
)
def test_environment_provider_accepts_exact_transport_sdk_pairs(
    kind: str,
    transport: str,
    sdk_distribution: str | None,
    sdk_version: str | None,
) -> None:
    payload = environment_v1_payload()
    payload["provider"].update(
        kind=kind,
        transport_policy=transport,
        sdk_distribution=sdk_distribution,
        sdk_version=sdk_version,
    )
    if kind == "openai":
        payload["runtime"]["dependencies"].insert(
            0,
            {"distribution": "openai", "version": "3.3.1", "files_sha256": SHA_A},
        )
        payload["runtime"]["import_environment"]["import_roots"].insert(
            0,
            {
                "distribution": "openai",
                "module": "openai",
                "origin_member": "openai/__init__.py",
            },
        )

    assert EnvironmentV1.model_validate(payload).provider.kind == kind


@pytest.mark.parametrize(
    ("kind", "transport", "sdk_distribution", "sdk_version"),
    [
        ("fake", "openai-direct-v1", None, None),
        ("fake", "offline", "openai", "3.3.1"),
        ("replay", "offline", None, "3.3.1"),
        ("openai", "offline", "openai", "3.3.1"),
        ("openai", "openai-direct-v1", None, "3.3.1"),
        ("openai", "openai-direct-v1", "openai", None),
    ],
)
def test_environment_provider_rejects_invalid_transport_sdk_pairs(
    kind: str,
    transport: str,
    sdk_distribution: str | None,
    sdk_version: str | None,
) -> None:
    payload = environment_v1_payload()
    payload["provider"].update(
        kind=kind,
        transport_policy=transport,
        sdk_distribution=sdk_distribution,
        sdk_version=sdk_version,
    )

    with pytest.raises(ValidationError):
        EnvironmentV1.model_validate(payload)


def test_console_launcher_requires_exact_template_digest() -> None:
    payload = environment_v1_payload()
    payload["runtime"]["import_environment"].update(
        launcher_mode="console_script",
        launcher_template_sha256=(
            "afdb677819f87d2c8e8af0eb2461ea1856b13dec27768546af0175c376ee493d"
        ),
    )

    environment = EnvironmentV1.model_validate(payload)

    assert environment.runtime.import_environment.launcher_mode == "console_script"


def test_session_environment_v1_and_prepared_event_complete_shapes() -> None:
    session_payload = session_environment_v1_payload()
    event_payload = prepared_event_v1_payload()

    session = SessionEnvironmentV1.model_validate(session_payload)
    event = PreparedEventV1.model_validate(event_payload)

    assert session.model_dump(mode="json") == session_payload
    assert event.model_dump(mode="json") == event_payload
    assert list(event.model_dump().keys()) == [
        "schema_version",
        "sequence",
        "event_id",
        "run_id",
        "occurred_at",
        "kind",
        "operation_id",
        "execution_session_id",
        "payload",
    ]


@pytest.mark.parametrize(
    ("sdk_distribution", "sdk_version"),
    [(None, "3.3.1"), ("openai", None), ("other", "1.0")],
)
def test_session_environment_rejects_invalid_sdk_pairs(
    sdk_distribution: str | None, sdk_version: str | None
) -> None:
    payload = session_environment_v1_payload()
    payload["sdk_distribution"] = sdk_distribution
    payload["sdk_version"] = sdk_version

    with pytest.raises(ValidationError):
        SessionEnvironmentV1.model_validate(payload)


def test_session_environment_accepts_openai_sdk_pair() -> None:
    payload = session_environment_v1_payload()
    payload["sdk_distribution"] = "openai"
    payload["sdk_version"] = "3.3.1"

    assert SessionEnvironmentV1.model_validate(payload).sdk_distribution == "openai"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("sequence",), 1),
        (("execution_session_id",), UUID_A),
        (("run_id",), "123e4567-e89b-12d3-a456-426614174000"),
        (("occurred_at",), "2026-08-27T12:34:56Z"),
        (("payload", "manifest_sha256"), "A" * 64),
    ],
)
def test_prepared_event_enforces_sequence_zero_common_contract(
    path: tuple[str | int, ...], value: object
) -> None:
    payload = prepared_event_v1_payload()
    _set_nested(payload, path, value)

    with pytest.raises(ValidationError):
        PreparedEventV1.model_validate(payload)


def test_verify_result_v1_round_trips_complete_shape() -> None:
    payload = verify_result_v1_payload()

    result = VerifyResultV1.model_validate(payload)

    assert result.model_dump(mode="json") == payload
    assert list(result.model_dump().keys()) == [
        "schema_version",
        "status",
        "run_id",
        "state",
        "capsule_sha256",
        "missing_plan_item_ids",
        "operational_blocker_codes",
        "warnings",
        "first_error",
    ]


@pytest.mark.parametrize(
    "state",
    [
        "PREPARED",
        "INTERRUPTED",
        "AMBIGUOUS_INFLIGHT",
        "AUTHENTICATION_STOPPED",
        "GENERATION_COMPLETE",
        "SEALING_INTERRUPTED",
    ],
)
def test_valid_unsealed_verify_result_requires_null_capsule_hash(state: str) -> None:
    payload = verify_result_v1_payload()
    payload["state"] = state
    state_blockers = {
        "PREPARED": ["never_started"],
        "INTERRUPTED": ["interrupted"],
        "AMBIGUOUS_INFLIGHT": ["ambiguous_inflight"],
        "AUTHENTICATION_STOPPED": ["authentication_stopped"],
        "GENERATION_COMPLETE": [],
        "SEALING_INTERRUPTED": ["never_started"],
    }
    payload["operational_blocker_codes"] = state_blockers[state]
    if state == "GENERATION_COMPLETE":
        payload["missing_plan_item_ids"] = []

    assert VerifyResultV1.model_validate(payload).capsule_sha256 is None


@pytest.mark.parametrize("state", ["SEALED_COMPLETE", "SEALED_BLOCKED"])
def test_valid_sealed_verify_result_requires_capsule_hash(state: str) -> None:
    payload = verify_result_v1_payload()
    payload["state"] = state
    payload["capsule_sha256"] = SHA_A
    if state == "SEALED_COMPLETE":
        payload["missing_plan_item_ids"] = []
        payload["operational_blocker_codes"] = []

    assert VerifyResultV1.model_validate(payload).capsule_sha256 == SHA_A


@pytest.mark.parametrize(
    ("state", "blockers", "missing"),
    [
        ("PREPARED", ["interrupted"], [SHA_A]),
        ("INTERRUPTED", ["interrupted"], []),
        ("GENERATION_COMPLETE", ["never_started"], [SHA_A]),
        ("SEALED_BLOCKED", [], []),
        ("SEALED_BLOCKED", ["never_started", "interrupted"], [SHA_A]),
        ("SEALING_INTERRUPTED", ["interrupted"], []),
        ("SEALING_INTERRUPTED", ["never_started", "interrupted"], [SHA_A]),
    ],
)
def test_valid_verify_result_rejects_state_blocker_mismatches(
    state: str, blockers: list[str], missing: list[str]
) -> None:
    payload = verify_result_v1_payload()
    payload["state"] = state
    payload["operational_blocker_codes"] = blockers
    payload["missing_plan_item_ids"] = missing
    if state == "SEALED_BLOCKED":
        payload["capsule_sha256"] = SHA_A

    with pytest.raises(ValidationError):
        VerifyResultV1.model_validate(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(run_id=None),
        lambda payload: payload.update(state=None),
        lambda payload: payload.update(
            first_error={
                "code": "invalid_model",
                "path": None,
                "sequence": None,
                "explanation": "invalid model",
            }
        ),
        lambda payload: payload.update(capsule_sha256=SHA_A),
        lambda payload: payload.update(state="SEALED_COMPLETE", capsule_sha256=None),
        lambda payload: payload.update(missing_plan_item_ids=[SHA_B, SHA_A]),
        lambda payload: payload.update(missing_plan_item_ids=[SHA_A, SHA_A]),
        lambda payload: payload.update(operational_blocker_codes=["interrupted", "never_started"]),
        lambda payload: payload.update(
            operational_blocker_codes=["never_started", "never_started"]
        ),
        lambda payload: payload.update(
            warnings=["producer_runtime_differs", "broader_permissions"]
        ),
        lambda payload: payload.update(warnings=["broader_permissions", "broader_permissions"]),
    ],
)
def test_valid_verify_result_rejects_invalid_relations(mutator: Any) -> None:
    payload = verify_result_v1_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        VerifyResultV1.model_validate(payload)


@pytest.mark.parametrize(
    ("status", "first_error"),
    [
        (
            "invalid",
            {
                "code": "invalid_model",
                "path": "manifest.json",
                "sequence": 0,
                "explanation": "schema validation failed",
            },
        ),
        ("busy", None),
        (
            "unsupported",
            {
                "code": "unsupported_filesystem",
                "path": None,
                "sequence": None,
                "explanation": "filesystem class is unsupported",
            },
        ),
    ],
)
def test_nonvalid_verify_statuses_accept_only_canonical_projection(
    status: str, first_error: dict[str, object] | None
) -> None:
    payload = {
        "schema_version": "1",
        "status": status,
        "run_id": None,
        "state": None,
        "capsule_sha256": None,
        "missing_plan_item_ids": [],
        "operational_blocker_codes": [],
        "warnings": [],
        "first_error": first_error,
    }

    assert VerifyResultV1.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    ("status", "first_error"),
    [
        ("invalid", None),
        (
            "invalid",
            {
                "code": "unsupported_filesystem",
                "path": None,
                "sequence": None,
                "explanation": "unsupported",
            },
        ),
        (
            "busy",
            {
                "code": "io_error",
                "path": None,
                "sequence": None,
                "explanation": "busy",
            },
        ),
        (
            "unsupported",
            {
                "code": "io_error",
                "path": None,
                "sequence": None,
                "explanation": "unsupported",
            },
        ),
        (
            "unsupported",
            {
                "code": "unsupported_filesystem",
                "path": "capsule.json",
                "sequence": None,
                "explanation": "unsupported",
            },
        ),
    ],
)
def test_nonvalid_verify_statuses_reject_wrong_error_relation(
    status: str, first_error: dict[str, object] | None
) -> None:
    payload = {
        "schema_version": "1",
        "status": status,
        "run_id": None,
        "state": None,
        "capsule_sha256": None,
        "missing_plan_item_ids": [],
        "operational_blocker_codes": [],
        "warnings": [],
        "first_error": first_error,
    }

    with pytest.raises(ValidationError):
        VerifyResultV1.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("first_error", "path"), "/host/manifest.json"),
        (("first_error", "path"), "../manifest.json"),
        (("first_error", "sequence"), True),
        (("first_error", "sequence"), -1),
        (("first_error", "explanation"), " \t"),
        (("first_error", "explanation"), "x" * 4097),
    ],
)
def test_verify_first_error_is_strict_and_bounded(
    path: tuple[str | int, ...], value: object
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "1",
        "status": "invalid",
        "run_id": None,
        "state": None,
        "capsule_sha256": None,
        "missing_plan_item_ids": [],
        "operational_blocker_codes": [],
        "warnings": [],
        "first_error": {
            "code": "invalid_model",
            "path": None,
            "sequence": None,
            "explanation": "schema validation failed",
        },
    }
    _set_nested(payload, path, value)

    with pytest.raises(ValidationError):
        VerifyResultV1.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "factory", "path"),
    [
        (CapsuleV1, capsule_v1_payload, ("unknown",)),
        (InputIndexV1, input_index_v1_payload, ("files", 0, "unknown")),
        (CaseIndexRowV1, case_index_row_v1_payload, ("unknown",)),
        (PlanRowV1, plan_row_v1_payload, ("unknown",)),
        (RunnerSourceIndexV1, runner_source_index_v1_payload, ("files", 0, "unknown")),
        (EnvironmentV1, environment_v1_payload, ("runtime", "unknown")),
        (SessionEnvironmentV1, session_environment_v1_payload, ("unknown",)),
        (PreparedEventV1, prepared_event_v1_payload, ("payload", "unknown")),
        (VerifyResultV1, verify_result_v1_payload, ("unknown",)),
    ],
)
def test_record_models_reject_unknown_fields(
    model: type[BaseModel], factory: Any, path: tuple[str | int, ...]
) -> None:
    payload = factory()
    _set_nested(payload, path, True)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate(payload)


def test_every_capsule_model_is_frozen_and_extra_forbid() -> None:
    model_classes: list[type[BaseModel]] = []
    for module in (schema, manifest_models, record_models):
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            ):
                model_classes.append(value)

    assert model_classes
    for model in model_classes:
        assert model.model_config.get("frozen") is True, model.__name__
        assert model.model_config.get("extra") == "forbid", model.__name__


def test_models_are_actually_frozen() -> None:
    capsule = CapsuleV1.model_validate(capsule_v1_payload())

    with pytest.raises(ValidationError, match="frozen"):
        capsule.runner_version = __version__


@pytest.mark.parametrize(
    ("model", "factory", "path"),
    [
        (InputIndexV1, input_index_v1_payload, ("files", 0, "dataset_id")),
        (InputIndexV1, input_index_v1_payload, ("files", 0, "binding_id")),
        (EnvironmentV1, environment_v1_payload, ("git_commit",)),
        (EnvironmentV1, environment_v1_payload, ("uv_lock", "sha256")),
        (
            EnvironmentV1,
            environment_v1_payload,
            ("runtime", "import_environment", "launcher_template_sha256"),
        ),
        (
            EnvironmentV1,
            environment_v1_payload,
            ("runtime", "import_environment", "virtualenv_bootstrap_sha256"),
        ),
        (EnvironmentV1, environment_v1_payload, ("provider", "sdk_distribution")),
        (EnvironmentV1, environment_v1_payload, ("provider", "sdk_version")),
        (EnvironmentV1, environment_v1_payload, ("container_image_digest",)),
        (
            SessionEnvironmentV1,
            session_environment_v1_payload,
            ("sdk_distribution",),
        ),
        (SessionEnvironmentV1, session_environment_v1_payload, ("sdk_version",)),
        (PreparedEventV1, prepared_event_v1_payload, ("execution_session_id",)),
        (VerifyResultV1, verify_result_v1_payload, ("run_id",)),
        (VerifyResultV1, verify_result_v1_payload, ("state",)),
        (VerifyResultV1, verify_result_v1_payload, ("capsule_sha256",)),
        (VerifyResultV1, verify_result_v1_payload, ("first_error",)),
    ],
)
def test_required_nullable_fields_cannot_be_silently_omitted(
    model: type[BaseModel],
    factory: Any,
    path: tuple[str | int, ...],
) -> None:
    payload = factory()
    current: Any = payload
    for part in path[:-1]:
        current = current[part]
    del current[path[-1]]

    with pytest.raises(ValidationError, match=str(path[-1])):
        model.model_validate(payload)


@pytest.mark.parametrize("field", ["path", "sequence"])
def test_verify_error_nullable_fields_require_explicit_null(field: str) -> None:
    payload: dict[str, Any] = {
        "schema_version": "1",
        "status": "invalid",
        "run_id": None,
        "state": None,
        "capsule_sha256": None,
        "missing_plan_item_ids": [],
        "operational_blocker_codes": [],
        "warnings": [],
        "first_error": {
            "code": "invalid_model",
            "path": None,
            "sequence": None,
            "explanation": "schema validation failed",
        },
    }
    del payload["first_error"][field]

    with pytest.raises(ValidationError, match=field):
        VerifyResultV1.model_validate(payload)


def test_canonical_timestamp_accepts_datetime_and_serializes_exactly() -> None:
    payload = capsule_v1_payload()
    payload["created_at"] = datetime(2026, 8, 27, 15, 34, 56, 123456, tzinfo=UTC)

    dumped = CapsuleV1.model_validate(payload).model_dump(mode="json")

    assert dumped["created_at"] == "2026-08-27T15:34:56.123456Z"
    assert CANONICAL_TIMESTAMP.endswith(".123456Z")
