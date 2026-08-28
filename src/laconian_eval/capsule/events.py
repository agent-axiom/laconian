"""Canonical initial capsule event construction."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ValidationError

from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.record_models import (
    PreparedEventV1,
    PreparedPayloadV1,
)

_GENERIC_EVENT_ERROR = "capsule event rejected"


class EventError(ValueError):
    """A content-free event failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_EVENT_ERROR)


def _strict_event(value: object) -> PreparedEventV1:
    try:
        if type(value) is not PreparedEventV1:
            raise TypeError
        payload = value.model_dump(mode="python", round_trip=True, warnings=False)
        return PreparedEventV1.model_validate(payload)
    except (AttributeError, TypeError, ValueError, ValidationError):
        raise EventError("invalid_event") from None


def make_prepared_event(
    *,
    run_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    manifest_sha256: str,
    input_index_sha256: str,
    case_index_sha256: str,
    plan_sha256: str,
    environment_sha256: str,
    runner_source_sha256: str,
) -> PreparedEventV1:
    """Build the sequence-zero prepared event and its canonical identity."""

    try:
        payload = PreparedPayloadV1.model_validate(
            {
                "manifest_sha256": manifest_sha256,
                "input_index_sha256": input_index_sha256,
                "case_index_sha256": case_index_sha256,
                "plan_sha256": plan_sha256,
                "environment_sha256": environment_sha256,
                "runner_source_sha256": runner_source_sha256,
            }
        )
        identity_payload = {
            "schema_version": "1",
            "sequence": 0,
            "run_id": run_id,
            "occurred_at": occurred_at,
            "kind": "prepared",
            "operation_id": operation_id,
            "execution_session_id": None,
            "payload": payload.model_dump(mode="json"),
        }
        event_id = stable_digest("laconian-event-v1", identity_payload)
        return PreparedEventV1.model_validate(identity_payload | {"event_id": event_id})
    except (AttributeError, TypeError, ValueError, ValidationError, UnicodeError):
        raise EventError("invalid_event") from None


def event_jsonl(event: PreparedEventV1) -> bytes:
    """Strictly revalidate and encode one canonical LF-framed event."""

    checked = _strict_event(event)
    payload = checked.model_dump(mode="json", round_trip=True, warnings=False)
    identity_payload = dict(payload)
    event_id = identity_payload.pop("event_id")
    try:
        expected = stable_digest("laconian-event-v1", identity_payload)
        encoded = canonical_json(payload) + b"\n"
    except (TypeError, ValueError, UnicodeError):
        raise EventError("invalid_event") from None
    if event_id != expected:
        raise EventError("event_id_mismatch")
    return encoded
