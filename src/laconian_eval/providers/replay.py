from collections.abc import Mapping
from pathlib import Path

import yaml

from laconian_eval.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    TokenUsage,
)

_ENTRY_FIELDS = frozenset(
    {
        "output_text",
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


def _entry_error(path: Path, key: str, message: str) -> ValueError:
    return ValueError(f"{path}: replay entry {key!r} {message}")


def _optional_string(
    path: Path,
    key: str,
    entry: Mapping[object, object],
    field: str,
) -> str | None:
    value = entry.get(field)
    if value is not None and not isinstance(value, str):
        raise _entry_error(path, key, f"field {field!r} must be a string or null")
    return value


def _parse_usage(
    path: Path,
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

    if counts["total_tokens"] < counts["input_tokens"] + counts["output_tokens"]:
        raise _entry_error(path, key, "total_tokens must cover input_tokens + output_tokens")
    cached_input_tokens = counts.get("cached_input_tokens")
    if cached_input_tokens is not None and cached_input_tokens > counts["input_tokens"]:
        raise _entry_error(path, key, "cached_input_tokens cannot exceed input_tokens")

    return TokenUsage(
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
        total_tokens=counts["total_tokens"],
        cached_input_tokens=cached_input_tokens,
    )


def _parse_entry(path: Path, key: str, raw_entry: object) -> GenerationResult:
    if not isinstance(raw_entry, Mapping):
        raise _entry_error(path, key, "must be a mapping")

    unknown_fields = [field for field in raw_entry if field not in _ENTRY_FIELDS]
    if unknown_fields:
        raise _entry_error(path, key, f"has unknown fields: {unknown_fields}")

    output_text = raw_entry.get("output_text")
    if not isinstance(output_text, str):
        raise _entry_error(path, key, "field 'output_text' must be a string")

    return GenerationResult(
        output_text=output_text,
        usage=_parse_usage(path, key, raw_entry),
        request_id=_optional_string(path, key, raw_entry, "request_id"),
        finish_reason=_optional_string(path, key, raw_entry, "finish_reason"),
    )


class ReplayProvider:
    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[str, GenerationResult]) -> None:
        self._entries = dict(entries)

    @classmethod
    def from_path(cls, path: Path) -> "ReplayProvider":
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls({})
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{path}: unable to read replay YAML: {exc}") from exc

        try:
            raw: object = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: unable to read replay YAML: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path}: replay YAML root must be a mapping")

        entries: dict[str, GenerationResult] = {}
        for raw_key, raw_entry in raw.items():
            if raw_key == "description":
                if not isinstance(raw_entry, str):
                    raise ValueError(f"{path}: description must be a string")
                continue
            if not isinstance(raw_key, str):
                raise ValueError(f"{path}: replay keys must be strings")
            entries[raw_key] = _parse_entry(path, raw_key, raw_entry)
        return cls(entries)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        key = f"{request.case_id}:{request.arm}:{request.repetition}"
        try:
            return self._entries[key]
        except KeyError:
            raise ProviderError(
                kind="missing_replay_key",
                message=f"missing replay key: {key}",
                retryable=False,
            ) from None
