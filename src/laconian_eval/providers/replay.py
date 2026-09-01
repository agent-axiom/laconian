from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from yaml import YAMLError

from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    PublicBenchmarkRequestPolicyV1,
    PublicBenchmarkRequestV1,
    TokenUsage,
)
from laconian_eval.yaml_io import safe_load_unique, safe_load_unique_bytes

if TYPE_CHECKING:
    from laconian_eval.capsule.attempts import (
        AttemptUsageV2,
        PublicBenchmarkProviderErrorEvidenceV1,
        PublicBenchmarkProviderOutcomeV1,
        PublicBenchmarkRawResponsePathV1,
        PublicBenchmarkRawResponseSourceV1,
    )

_ENTRY_FIELDS = frozenset(
    {
        "output_text",
        "response_model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "request_id",
        "finish_reason",
    }
)
_REQUIRED_USAGE_FIELDS = frozenset({"input_tokens", "output_tokens", "total_tokens"})
_USAGE_FIELDS = _REQUIRED_USAGE_FIELDS | {"cached_input_tokens"}

_BENCHMARK_ROW_FIELDS = ("requested_model_id", "response")
_BENCHMARK_RESPONSE_FIELDS = (
    "id",
    "status",
    "error",
    "output",
    "model",
    "service_tier",
    "prompt_cache_options",
    "usage",
)
_BENCHMARK_CACHE_FIELDS = ("mode", "ttl")
_BENCHMARK_USAGE_FIELDS = (
    "input_tokens",
    "input_tokens_details",
    "output_tokens",
    "output_tokens_details",
    "total_tokens",
)
_BENCHMARK_INPUT_DETAIL_FIELDS = ("cached_tokens", "cache_write_tokens")
_BENCHMARK_OUTPUT_DETAIL_FIELDS = ("reasoning_tokens",)
_BENCHMARK_ERROR_FIELDS = ("code", "message")
_BENCHMARK_MESSAGE_FIELDS = ("type", "content")
_BENCHMARK_OUTPUT_TEXT_FIELDS = ("type", "text")
_BENCHMARK_RAW_RESPONSE_PATHS: "tuple[PublicBenchmarkRawResponsePathV1, ...]" = (
    "response.id",
    "response.status",
    "response.error",
    "response.output",
    "response.model",
    "response.service_tier",
    "response.prompt_cache_options.mode",
    "response.prompt_cache_options.ttl",
    "response.usage.input_tokens",
    "response.usage.input_tokens_details.cached_tokens",
    "response.usage.input_tokens_details.cache_write_tokens",
    "response.usage.output_tokens",
    "response.usage.output_tokens_details.reasoning_tokens",
    "response.usage.total_tokens",
)
_BENCHMARK_SOURCE_DIGEST_FIELDS = (
    "returned_model_source_sha256",
    "service_tier_source_sha256",
    "applied_cache_control_source_sha256",
    "cache_read_source_sha256",
    "cache_write_source_sha256",
    "usage_source_sha256",
    "reasoning_tokens_source_sha256",
)
_BENCHMARK_MODEL_IDS = frozenset({"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"})


def _entry_error(source: Path | str, key: str, message: str) -> ValueError:
    return ValueError(f"{source}: replay entry {key!r} {message}")


def _optional_string(
    path: Path | str,
    key: str,
    entry: Mapping[object, object],
    field: str,
) -> str | None:
    value = entry.get(field)
    if value is not None and not isinstance(value, str):
        raise _entry_error(path, key, f"field {field!r} must be a string or null")
    return value


def _parse_usage(
    path: Path | str,
    key: str,
    entry: Mapping[object, object],
) -> TokenUsage | None:
    present_fields = {field for field in _USAGE_FIELDS if field in entry}
    if not present_fields:
        return None
    if not _REQUIRED_USAGE_FIELDS.issubset(present_fields):
        missing = sorted(_REQUIRED_USAGE_FIELDS - present_fields)
        raise _entry_error(path, key, f"has partial token usage; missing {missing}")

    counts: dict[str, int] = {}
    for field in present_fields:
        value = entry[field]
        if type(value) is not int:
            raise _entry_error(path, key, f"field {field!r} must be an integer")
        if value < 0:
            raise _entry_error(path, key, f"field {field!r} must be nonnegative")
        counts[field] = value

    if counts["total_tokens"] != counts["input_tokens"] + counts["output_tokens"]:
        raise _entry_error(path, key, "total_tokens must equal input_tokens + output_tokens")
    cached_input_tokens = counts.get("cached_input_tokens")
    if cached_input_tokens is not None and cached_input_tokens > counts["input_tokens"]:
        raise _entry_error(path, key, "cached_input_tokens cannot exceed input_tokens")

    return TokenUsage(
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
        total_tokens=counts["total_tokens"],
        cached_input_tokens=cached_input_tokens,
    )


def _parse_entry(path: Path | str, key: str, raw_entry: object) -> GenerationResult:
    if not isinstance(raw_entry, Mapping):
        raise _entry_error(path, key, "must be a mapping")

    unknown_fields = [field for field in raw_entry if field not in _ENTRY_FIELDS]
    if unknown_fields:
        raise _entry_error(path, key, f"has unknown fields: {unknown_fields}")

    output_text = raw_entry.get("output_text")
    if not isinstance(output_text, str):
        raise _entry_error(path, key, "field 'output_text' must be a string")
    response_model = raw_entry.get("response_model")
    if type(response_model) is not str or not response_model.strip():
        raise _entry_error(
            path,
            key,
            "field 'response_model' must be an exact nonblank string",
        )

    return GenerationResult(
        output_text=output_text,
        usage=_parse_usage(path, key, raw_entry),
        request_id=_optional_string(path, key, raw_entry, "request_id"),
        finish_reason=_optional_string(path, key, raw_entry, "finish_reason"),
        response_model=response_model,
    )


def _benchmark_mapping(
    source: Path | str,
    key: str,
    value: object,
    fields: tuple[str, ...],
    label: str,
) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise _entry_error(source, key, f"field {label!r} must be a mapping")
    if tuple(value) != fields:
        raise _entry_error(
            source,
            key,
            f"field {label!r} must have exact ordered members {fields}",
        )
    return value


def _benchmark_exact_string(
    source: Path | str,
    key: str,
    value: object,
    label: str,
) -> str:
    if type(value) is not str or not value.strip():
        raise _entry_error(source, key, f"field {label!r} must be an exact nonblank string")
    return value


def _benchmark_count(
    source: Path | str,
    key: str,
    value: object,
    label: str,
) -> int:
    if type(value) is not int or value < 0:
        raise _entry_error(source, key, f"field {label!r} must be a nonnegative integer")
    return value


def _benchmark_output_text(
    source: Path | str,
    key: str,
    value: object,
) -> str:
    if type(value) is not list:
        raise _entry_error(source, key, "field 'response.output' must be a list")
    pieces: list[str] = []
    for item in value:
        message = _benchmark_mapping(
            source,
            key,
            item,
            _BENCHMARK_MESSAGE_FIELDS,
            "response.output[]",
        )
        if message["type"] != "message":
            raise _entry_error(source, key, "response output type must be exactly 'message'")
        content = message["content"]
        if type(content) is not list:
            raise _entry_error(source, key, "response message content must be a list")
        for item_content in content:
            part = _benchmark_mapping(
                source,
                key,
                item_content,
                _BENCHMARK_OUTPUT_TEXT_FIELDS,
                "response.output[].content[]",
            )
            if part["type"] != "output_text":
                raise _entry_error(
                    source,
                    key,
                    "response content type must be exactly 'output_text'",
                )
            pieces.append(
                _benchmark_exact_string(
                    source,
                    key,
                    part["text"],
                    "response.output[].content[].text",
                )
            )
    output = "".join(pieces)
    if not output:
        raise _entry_error(source, key, "response output must be nonblank")
    return output


def _benchmark_usage(
    source: Path | str,
    key: str,
    usage: Mapping[object, object],
) -> "AttemptUsageV2":
    from laconian_eval.capsule.attempts import AttemptUsageV2

    input_details = _benchmark_mapping(
        source,
        key,
        usage["input_tokens_details"],
        _BENCHMARK_INPUT_DETAIL_FIELDS,
        "response.usage.input_tokens_details",
    )
    output_details = _benchmark_mapping(
        source,
        key,
        usage["output_tokens_details"],
        _BENCHMARK_OUTPUT_DETAIL_FIELDS,
        "response.usage.output_tokens_details",
    )
    input_tokens = _benchmark_count(
        source, key, usage["input_tokens"], "response.usage.input_tokens"
    )
    cache_read_tokens = _benchmark_count(
        source,
        key,
        input_details["cached_tokens"],
        "response.usage.input_tokens_details.cached_tokens",
    )
    cache_write_tokens = _benchmark_count(
        source,
        key,
        input_details["cache_write_tokens"],
        "response.usage.input_tokens_details.cache_write_tokens",
    )
    output_tokens = _benchmark_count(
        source, key, usage["output_tokens"], "response.usage.output_tokens"
    )
    reasoning_tokens = _benchmark_count(
        source,
        key,
        output_details["reasoning_tokens"],
        "response.usage.output_tokens_details.reasoning_tokens",
    )
    total_tokens = _benchmark_count(
        source, key, usage["total_tokens"], "response.usage.total_tokens"
    )
    if total_tokens != input_tokens + output_tokens:
        raise _entry_error(source, key, "response usage total is inconsistent")
    if cache_read_tokens + cache_write_tokens > input_tokens:
        raise _entry_error(source, key, "response cache usage exceeds input tokens")
    if reasoning_tokens > output_tokens:
        raise _entry_error(source, key, "response reasoning usage exceeds output tokens")
    return AttemptUsageV2(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        ordinary_uncached_input_tokens=(input_tokens - cache_read_tokens - cache_write_tokens),
        reasoning_tokens=reasoning_tokens,
        availability="complete",
        source="provider",
        cache_read_status=("reported_zero" if cache_read_tokens == 0 else "reported_nonzero"),
        cache_write_status=("reported_zero" if cache_write_tokens == 0 else "reported_nonzero"),
        reasoning_token_accounting="reported",
    )


def _benchmark_raw_source(
    response: Mapping[object, object],
    cache: Mapping[object, object],
    usage: Mapping[object, object],
    input_details: Mapping[object, object],
    output_details: Mapping[object, object],
) -> "PublicBenchmarkRawResponseSourceV1":
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkRawResponseSourceEntryV1,
        PublicBenchmarkRawResponseSourceV1,
    )

    values = (
        response["id"],
        response["status"],
        response["error"],
        response["output"],
        response["model"],
        response["service_tier"],
        cache["mode"],
        cache["ttl"],
        usage["input_tokens"],
        input_details["cached_tokens"],
        input_details["cache_write_tokens"],
        usage["output_tokens"],
        output_details["reasoning_tokens"],
        usage["total_tokens"],
    )
    return PublicBenchmarkRawResponseSourceV1(
        schema_version="PublicBenchmarkRawResponseSourceV1",
        entries=tuple(
            PublicBenchmarkRawResponseSourceEntryV1(
                path=path,
                present=True,
                value=value,
            )
            for path, value in zip(
                _BENCHMARK_RAW_RESPONSE_PATHS,
                values,
                strict=True,
            )
        ),
    )


def _benchmark_error_evidence(
    *,
    requested_model_id: str,
    delivery_certainty: str,
    provider_request_id: str | None,
    response_id: str | None,
    raw_source: "PublicBenchmarkRawResponseSourceV1 | None",
    usage: "AttemptUsageV2",
    returned_model_id: str | None,
    returned_service_tier: str | None,
    service_tier_status: str,
    applied_prompt_cache_mode: str | None,
    applied_prompt_cache_ttl: str | None,
    applied_cache_control_status: str,
    structured_status: int | None,
) -> "PublicBenchmarkProviderErrorEvidenceV1":
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        public_benchmark_provider_error_source_sha256,
        public_benchmark_raw_response_sha256,
    )

    raw_digest = (
        public_benchmark_raw_response_sha256(raw_source) if raw_source is not None else None
    )
    payload: dict[str, object] = {
        "schema_version": "public-benchmark-provider-error-evidence-v1",
        "delivery_certainty": delivery_certainty,
        "provider_request_id": provider_request_id,
        "response_id": response_id,
        "raw_response_sha256": raw_digest,
        "raw_response_source": raw_source,
        "usage": usage,
        "requested_model_id": requested_model_id,
        "returned_model_id": returned_model_id,
        "returned_model_source_sha256": "0" * 64,
        "requested_service_tier": "default",
        "returned_service_tier": returned_service_tier,
        "service_tier_status": service_tier_status,
        "service_tier_source_sha256": "0" * 64,
        "applied_prompt_cache_mode": applied_prompt_cache_mode,
        "applied_prompt_cache_ttl": applied_prompt_cache_ttl,
        "applied_cache_control_status": applied_cache_control_status,
        "applied_cache_control_source_sha256": "0" * 64,
        "cache_read_source_sha256": "0" * 64,
        "cache_write_source_sha256": "0" * 64,
        "usage_source_sha256": "0" * 64,
        "reasoning_tokens_source_sha256": "0" * 64,
        "structured_status": structured_status,
        "error_source_sha256": "0" * 64,
    }
    error_digest = public_benchmark_provider_error_source_sha256(payload)
    payload["error_source_sha256"] = error_digest
    common_digest = raw_digest or error_digest
    for field in _BENCHMARK_SOURCE_DIGEST_FIELDS:
        payload[field] = common_digest
    return PublicBenchmarkProviderErrorEvidenceV1.model_validate(payload)


def _parse_benchmark_entry(
    source: Path | str,
    key: str,
    raw_entry: object,
) -> "tuple[str, PublicBenchmarkProviderOutcomeV1]":
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkResponseEvidenceV1,
        public_benchmark_raw_response_sha256,
    )

    entry = _benchmark_mapping(
        source,
        key,
        raw_entry,
        _BENCHMARK_ROW_FIELDS,
        "entry",
    )
    requested_model_id = _benchmark_exact_string(
        source,
        key,
        entry["requested_model_id"],
        "requested_model_id",
    )
    if requested_model_id not in _BENCHMARK_MODEL_IDS:
        raise _entry_error(source, key, "requested_model_id is not a benchmark model")
    response = _benchmark_mapping(
        source,
        key,
        entry["response"],
        _BENCHMARK_RESPONSE_FIELDS,
        "response",
    )
    response_id = _benchmark_exact_string(source, key, response["id"], "response.id")
    status = _benchmark_exact_string(source, key, response["status"], "response.status")
    if status not in {"completed", "failed"}:
        raise _entry_error(source, key, "response.status must be completed or failed")
    returned_model_id = _benchmark_exact_string(source, key, response["model"], "response.model")
    returned_service_tier = _benchmark_exact_string(
        source,
        key,
        response["service_tier"],
        "response.service_tier",
    )
    service_tier_status = "reported_default" if returned_service_tier == "default" else "mismatch"
    cache = _benchmark_mapping(
        source,
        key,
        response["prompt_cache_options"],
        _BENCHMARK_CACHE_FIELDS,
        "response.prompt_cache_options",
    )
    if cache["mode"] != "explicit" or cache["ttl"] != "30m":
        raise _entry_error(source, key, "response cache control must be explicit/30m")
    usage_mapping = _benchmark_mapping(
        source,
        key,
        response["usage"],
        _BENCHMARK_USAGE_FIELDS,
        "response.usage",
    )
    input_details = _benchmark_mapping(
        source,
        key,
        usage_mapping["input_tokens_details"],
        _BENCHMARK_INPUT_DETAIL_FIELDS,
        "response.usage.input_tokens_details",
    )
    output_details = _benchmark_mapping(
        source,
        key,
        usage_mapping["output_tokens_details"],
        _BENCHMARK_OUTPUT_DETAIL_FIELDS,
        "response.usage.output_tokens_details",
    )
    parsed_usage = _benchmark_usage(source, key, usage_mapping)
    raw_source = _benchmark_raw_source(
        response,
        cache,
        usage_mapping,
        input_details,
        output_details,
    )
    digest = public_benchmark_raw_response_sha256(raw_source)

    common: dict[str, object] = {
        "usage": parsed_usage,
        "requested_model_id": requested_model_id,
        "returned_model_id": returned_model_id,
        "returned_model_source_sha256": digest,
        "requested_service_tier": "default",
        "returned_service_tier": returned_service_tier,
        "service_tier_status": service_tier_status,
        "service_tier_source_sha256": digest,
        "applied_prompt_cache_mode": "explicit",
        "applied_prompt_cache_ttl": "30m",
        "applied_cache_control_status": "reported_exact",
        "applied_cache_control_source_sha256": digest,
        "cache_read_source_sha256": digest,
        "cache_write_source_sha256": digest,
        "usage_source_sha256": digest,
        "reasoning_tokens_source_sha256": digest,
    }
    if status == "completed":
        if response["error"] is not None:
            raise _entry_error(source, key, "completed response.error must be null")
        output_text = _benchmark_output_text(source, key, response["output"])
        outcome: PublicBenchmarkProviderOutcomeV1 = (
            PublicBenchmarkResponseEvidenceV1.model_validate(
                {
                    "schema_version": "public-benchmark-response-evidence-v1",
                    "response_id": response_id,
                    "raw_response_sha256": digest,
                    "output_text": output_text,
                    "raw_response_source": raw_source,
                    **common,
                }
            )
        )
        return requested_model_id, outcome

    error = _benchmark_mapping(
        source,
        key,
        response["error"],
        _BENCHMARK_ERROR_FIELDS,
        "response.error",
    )
    _benchmark_exact_string(source, key, error["code"], "response.error.code")
    _benchmark_exact_string(source, key, error["message"], "response.error.message")
    if response["output"] != []:
        raise _entry_error(source, key, "failed response.output must be an empty list")
    outcome = _benchmark_error_evidence(
        requested_model_id=requested_model_id,
        delivery_certainty="response_received",
        provider_request_id=response_id,
        response_id=response_id,
        raw_source=raw_source,
        usage=parsed_usage,
        returned_model_id=returned_model_id,
        returned_service_tier=returned_service_tier,
        service_tier_status=service_tier_status,
        applied_prompt_cache_mode="explicit",
        applied_prompt_cache_ttl="30m",
        applied_cache_control_status="reported_exact",
        structured_status=None,
    )
    return requested_model_id, outcome


class ReplayProvider:
    __slots__ = ("_benchmark_entries", "_entries", "_source")

    def __init__(
        self,
        entries: Mapping[str, GenerationResult],
        source: Path | None = None,
    ) -> None:
        self._benchmark_entries: dict[
            str,
            tuple[str, PublicBenchmarkProviderOutcomeV1],
        ] = {}
        self._entries = dict(entries)
        self._source = source

    @classmethod
    def _from_mapping(
        cls,
        raw: object,
        *,
        error_source: Path | str,
        source: Path | None,
    ) -> "ReplayProvider":
        if not isinstance(raw, Mapping):
            raise ValueError(f"{error_source}: replay YAML root must be a mapping")

        entries: dict[str, GenerationResult] = {}
        for raw_key, raw_entry in raw.items():
            if raw_key == "description":
                if not isinstance(raw_entry, str):
                    raise ValueError(f"{error_source}: description must be a string")
                continue
            if not isinstance(raw_key, str):
                raise ValueError(f"{error_source}: replay keys must be strings")
            entries[raw_key] = _parse_entry(error_source, raw_key, raw_entry)
        return cls(entries, source=source)

    @classmethod
    def from_path(cls, path: Path) -> "ReplayProvider":
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls({}, source=path)
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{path}: unable to read replay YAML: {exc}") from exc

        try:
            raw = safe_load_unique(content)
        except YAMLError as exc:
            raise ValueError(f"{path}: unable to read replay YAML: {exc}") from exc
        return cls._from_mapping(raw, error_source=path, source=path)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ReplayProvider":
        collection_limit = RESOURCE_LIMITS_V1.plan_rows + 1
        raw = safe_load_unique_bytes(
            data,
            byte_limit=RESOURCE_LIMITS_V1.replay_fixture_bytes,
            byte_code="replay_fixture_limit",
            depth_limit=RESOURCE_LIMITS_V1.nesting_depth,
            collection_limit=collection_limit,
            collection_code="replay_collection_limit",
            node_limit=collection_limit * RESOURCE_LIMITS_V1.nesting_depth,
            node_code="replay_nodes_limit",
        )
        return cls._from_mapping(
            raw,
            error_source="captured replay",
            source=None,
        )

    @classmethod
    def _from_benchmark_mapping(
        cls,
        raw: object,
        *,
        error_source: Path | str,
        source: Path | None,
    ) -> "ReplayProvider":
        if not isinstance(raw, Mapping):
            raise ValueError(f"{error_source}: benchmark replay YAML root must be a mapping")

        entries: dict[str, tuple[str, PublicBenchmarkProviderOutcomeV1]] = {}
        for raw_key, raw_entry in raw.items():
            if raw_key == "description":
                if type(raw_entry) is not str:
                    raise ValueError(f"{error_source}: description must be an exact string")
                continue
            if type(raw_key) is not str:
                raise ValueError(f"{error_source}: benchmark replay keys must be strings")
            entries[raw_key] = _parse_benchmark_entry(error_source, raw_key, raw_entry)
        provider = cls({}, source=source)
        provider._benchmark_entries = entries
        return provider

    @classmethod
    def from_benchmark_path(cls, path: Path) -> "ReplayProvider":
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{path}: unable to read benchmark replay YAML: {exc}") from exc
        try:
            raw = safe_load_unique(content)
        except YAMLError as exc:
            raise ValueError(f"{path}: unable to read benchmark replay YAML: {exc}") from exc
        return cls._from_benchmark_mapping(raw, error_source=path, source=path)

    @classmethod
    def from_benchmark_bytes(cls, data: bytes) -> "ReplayProvider":
        collection_limit = RESOURCE_LIMITS_V1.plan_rows + 1
        raw = safe_load_unique_bytes(
            data,
            byte_limit=RESOURCE_LIMITS_V1.replay_fixture_bytes,
            byte_code="replay_fixture_limit",
            depth_limit=RESOURCE_LIMITS_V1.nesting_depth,
            collection_limit=collection_limit,
            collection_code="replay_collection_limit",
            node_limit=collection_limit * RESOURCE_LIMITS_V1.nesting_depth,
            node_code="replay_nodes_limit",
        )
        return cls._from_benchmark_mapping(
            raw,
            error_source="captured benchmark replay",
            source=None,
        )

    @staticmethod
    def _validate_benchmark_request(request: PublicBenchmarkRequestV1) -> None:
        if type(request) is not PublicBenchmarkRequestV1:
            raise ValueError("request must be an exact PublicBenchmarkRequestV1")
        if type(request.case_id) is not str or not request.case_id.strip():
            raise ValueError("benchmark replay case_id must be an exact nonblank string")
        if type(request.arm) is not str or request.arm not in {
            "baseline",
            "concise",
            "caveman",
            "if",
        }:
            raise ValueError("benchmark replay arm is invalid")
        if type(request.repetition) is not int or request.repetition < 0:
            raise ValueError("benchmark replay repetition is invalid")
        if (
            type(request.requested_model_id) is not str
            or request.requested_model_id not in _BENCHMARK_MODEL_IDS
        ):
            raise ValueError("benchmark replay requested model is invalid")
        policy = request.policy
        if type(policy) is not PublicBenchmarkRequestPolicyV1 or (
            policy.schema_version,
            policy.service_tier,
            policy.prompt_cache_mode,
            policy.prompt_cache_ttl,
            policy.reasoning_mode,
            policy.input_token_bound_version,
            policy.max_input_tokens,
        ) != (
            "PublicBenchmarkRequestPolicyV1",
            "default",
            "explicit",
            "30m",
            "omitted",
            "openai-utf8-envelope-v1",
            272000,
        ):
            raise ValueError("benchmark replay request policy is invalid")

    def generate_benchmark(
        self,
        request: PublicBenchmarkRequestV1,
    ) -> "PublicBenchmarkProviderOutcomeV1":
        from laconian_eval.capsule.attempts import AttemptUsageV2

        self._validate_benchmark_request(request)
        key = f"{request.case_id}:{request.arm}:{request.repetition}"
        entry = self._benchmark_entries.get(key)
        if entry is not None:
            requested_model_id, outcome = entry
            if requested_model_id != request.requested_model_id:
                raise ValueError("benchmark replay requested model does not match fixture")
            return outcome

        usage = AttemptUsageV2(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cache_read_tokens=None,
            cache_write_tokens=None,
            ordinary_uncached_input_tokens=None,
            reasoning_tokens=None,
            availability="unavailable",
            source="provider",
            cache_read_status="not_applicable_definitely_not_sent",
            cache_write_status="not_applicable_definitely_not_sent",
            reasoning_token_accounting="not_reported",
        )
        return _benchmark_error_evidence(
            requested_model_id=request.requested_model_id,
            delivery_certainty="definitely_not_sent",
            provider_request_id=None,
            response_id=None,
            raw_source=None,
            usage=usage,
            returned_model_id=None,
            returned_service_tier=None,
            service_tier_status="not_applicable_definitely_not_sent",
            applied_prompt_cache_mode=None,
            applied_prompt_cache_ttl=None,
            applied_cache_control_status="not_applicable_definitely_not_sent",
            structured_status=None,
        )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        key = f"{request.case_id}:{request.arm}:{request.repetition}"
        try:
            return self._entries[key]
        except KeyError:
            source = f" in {self._source}" if self._source is not None else ""
            raise ProviderError(
                kind="missing_replay_key",
                message=f"missing replay key: {key}{source}",
                retryable=False,
                delivery_certainty="definitely_not_sent",
            ) from None
