from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    ResourceLimitsV1,
    bounded_utf8_length,
    check_collection_count,
    check_nesting_depth,
    check_plan_token_exposure,
    reserve_attempt_transaction,
)

KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB


def test_resource_limits_v1_contains_every_section_five_limit() -> None:
    limits = RESOURCE_LIMITS_V1
    assert limits.version == "1"
    assert limits.source_manifest_bytes == 1 * MIB
    assert limits.case_file_bytes == 8 * MIB
    assert limits.all_case_files_bytes == 64 * MIB
    assert limits.arm_member_bytes == 2 * MIB
    assert limits.all_arm_members_bytes == 8 * MIB
    assert limits.replay_fixture_bytes == 256 * MIB
    assert limits.protocol_file_bytes == 16 * MIB
    assert limits.all_protocol_files_bytes == 64 * MIB
    assert limits.runner_source_file_bytes == 2 * MIB
    assert limits.all_runner_source_files_bytes == 32 * MIB
    assert limits.captured_input_total_bytes == 512 * MIB
    assert limits.case_records == 10_000
    assert limits.plan_rows == 100_000
    assert limits.raw_rows == 600_000
    assert limits.plan_event_jsonl_row_bytes == 1 * MIB
    assert limits.raw_jsonl_row_bytes == 16 * MIB
    assert limits.output_utf8_bytes == 2 * MIB
    assert limits.output_tokens_per_request == 65_536
    assert limits.output_tokens_plan == 10_000_000
    assert limits.mutable_capsule_bytes == 8 * GIB
    assert limits.diagnostic_bytes == 4 * KIB
    assert limits.bounded_string_bytes == 1 * KIB
    assert limits.nesting_depth == 64


def test_resource_limits_v1_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        RESOURCE_LIMITS_V1.plan_rows = 1  # type: ignore[misc]


@pytest.mark.parametrize("version", ["2", "", 1, None])
def test_resource_limits_v1_rejects_invalid_version(version: object) -> None:
    with pytest.raises(ResourceLimitError) as caught:
        replace(RESOURCE_LIMITS_V1, version=version)
    assert caught.value.code == "invalid_resource_limits"


@pytest.mark.parametrize(
    "field_name",
    [field.name for field in fields(ResourceLimitsV1) if field.name != "version"],
)
@pytest.mark.parametrize("invalid_value", [True, False, 0, -1, 1.0, "1"])
def test_resource_limits_v1_rejects_invalid_numeric_override(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ResourceLimitError) as caught:
        replace(RESOURCE_LIMITS_V1, **{field_name: invalid_value})
    assert caught.value.code == "invalid_resource_limits"


def test_bounded_utf8_length_counts_encoded_bytes() -> None:
    assert bounded_utf8_length("\u03b1", limit=2, code="test_bytes") == 2
    with pytest.raises(ResourceLimitError) as caught:
        bounded_utf8_length("\u03b1\u03b1", limit=3, code="test_bytes")
    assert caught.value.code == "test_bytes"


def test_bounded_utf8_length_rejects_by_character_lower_bound_before_encoding() -> None:
    class EncodeMustNotRun(str):
        def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
            raise AssertionError("encode must not run")

    value = EncodeMustNotRun("oversized")
    with pytest.raises(ResourceLimitError) as caught:
        bounded_utf8_length(value, limit=8, code="bounded_string_limit")
    assert caught.value.code == "bounded_string_limit"


def test_bounded_utf8_length_counts_chunks_and_rejects_invalid_utf8() -> None:
    value = "a" * 4095 + "\u03b1"
    assert bounded_utf8_length(value, limit=4097, code="test_bytes") == 4097
    with pytest.raises(ResourceLimitError) as caught:
        bounded_utf8_length("\ud800", limit=10, code="test_bytes")
    assert caught.value.code == "invalid_utf8"


def test_bounded_utf8_length_does_not_echo_rejected_content() -> None:
    secret = "never-echo-this-secret"
    with pytest.raises(ResourceLimitError) as caught:
        bounded_utf8_length(secret, limit=1, code="bounded_string_limit")
    assert caught.value.code == "bounded_string_limit"
    assert secret not in str(caught.value)


@pytest.mark.parametrize("value", [True, False])
def test_integer_checks_strictly_reject_bool(value: bool) -> None:
    with pytest.raises(ResourceLimitError) as count_error:
        check_collection_count(value, limit=1, code="collection_limit")
    assert count_error.value.code == "invalid_count"

    with pytest.raises(ResourceLimitError) as token_error:
        check_plan_token_exposure(value, 1)
    assert token_error.value.code == "invalid_count"

    with pytest.raises(ResourceLimitError) as reservation_error:
        reserve_attempt_transaction(value)
    assert reservation_error.value.code == "invalid_count"


def test_check_collection_count_enforces_item_and_aggregate_bounds() -> None:
    check_collection_count(8 * MIB, limit=8 * MIB, code="case_file_limit")
    with pytest.raises(ResourceLimitError) as item_error:
        check_collection_count(8 * MIB + 1, limit=8 * MIB, code="case_file_limit")
    assert item_error.value.code == "case_file_limit"

    check_collection_count(64 * MIB, limit=64 * MIB, code="case_files_limit")
    with pytest.raises(ResourceLimitError) as aggregate_error:
        check_collection_count(
            64 * MIB + 1,
            limit=64 * MIB,
            code="case_files_limit",
        )
    assert aggregate_error.value.code == "case_files_limit"


def test_check_nesting_depth_accepts_64_and_rejects_65() -> None:
    depth_64: object = "leaf"
    for _ in range(64):
        depth_64 = [depth_64]
    check_nesting_depth(depth_64)

    depth_65 = [depth_64]
    with pytest.raises(ResourceLimitError) as caught:
        check_nesting_depth(depth_65)
    assert caught.value.code == "nesting_depth_limit"


def test_check_nesting_depth_handles_nested_mappings_and_tuples() -> None:
    check_nesting_depth({"outer": ({"inner": [1]},)})


def test_plan_token_exposure_enforces_request_and_materialized_plan_limits() -> None:
    assert check_plan_token_exposure(100, 100_000) == 10_000_000

    with pytest.raises(ResourceLimitError) as request_error:
        check_plan_token_exposure(65_537, 1)
    assert request_error.value.code == "output_tokens_per_request_limit"

    with pytest.raises(ResourceLimitError) as plan_error:
        check_plan_token_exposure(101, 100_000)
    assert plan_error.value.code == "output_tokens_plan_limit"


def test_attempt_transaction_reserves_every_complete_worst_case_row() -> None:
    event_row_with_lf = 1 * MIB + 1
    raw_row_with_lf = 16 * MIB + 1
    complete_attempt = 4 * event_row_with_lf + raw_row_with_lf
    assert reserve_attempt_transaction(0) == complete_attempt


def test_attempt_transaction_includes_epoch_events_when_requested() -> None:
    event_row_with_lf = 1 * MIB + 1
    raw_row_with_lf = 16 * MIB + 1
    epoch_and_attempt = 6 * event_row_with_lf + raw_row_with_lf
    assert reserve_attempt_transaction(0, include_epoch_events=True) == epoch_and_attempt


def test_attempt_transaction_does_not_double_count_existing_reservation() -> None:
    existing = 4 * (1 * MIB + 1) + (16 * MIB + 1)
    assert reserve_attempt_transaction(123, reserved_bytes=existing) == existing


def test_attempt_transaction_fails_before_exceeding_mutable_capsule_limit() -> None:
    reservation = 4 * (1 * MIB + 1) + (16 * MIB + 1)
    current = 8 * GIB - reservation
    assert reserve_attempt_transaction(current) == reservation

    with pytest.raises(ResourceLimitError) as caught:
        reserve_attempt_transaction(current + 1)
    assert caught.value.code == "mutable_capsule_limit"


@pytest.mark.parametrize(
    "function_call",
    [
        lambda: check_collection_count(-1, limit=1, code="collection_limit"),
        lambda: check_plan_token_exposure(-1, 1),
        lambda: check_plan_token_exposure(1, -1),
        lambda: reserve_attempt_transaction(-1),
        lambda: reserve_attempt_transaction(0, reserved_bytes=-1),
    ],
)
def test_count_helpers_reject_negative_values(function_call: object) -> None:
    assert callable(function_call)
    with pytest.raises(ResourceLimitError) as caught:
        function_call()
    assert caught.value.code == "invalid_count"
