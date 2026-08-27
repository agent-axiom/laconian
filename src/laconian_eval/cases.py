import json
import os
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from yaml import YAMLError

from laconian_eval.capsule.bounded_io import (
    open_directory_no_follow,
    read_regular_file_once,
)
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
)
from laconian_eval.models import (
    ActivationCase,
    ActivationCaseFile,
    ResponseCase,
    ResponseCaseFile,
    RunManifest,
)
from laconian_eval.yaml_io import StrictYamlError, safe_load_unique, safe_load_unique_bytes

_CASE_FILE_KEYS = ("schema_version", "kind", "cases")
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_CaseT = TypeVar("_CaseT", ResponseCase, ActivationCase)
_Source = Path | str
_SAFE_CASE_VALIDATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "cases",
        "id",
        "scenario_id",
        "locale",
        "category",
        "prompt",
        "hard_constraints",
        "semantic_rubric",
        "required_literals",
        "forbidden_literals",
        "required_json_keys",
        "required_yaml_keys",
        "min_sentences",
        "max_sentences",
        "required_facts",
        "material_warning",
        "expected_activation",
        "rationale",
    }
)


def response_case_sha256(case: ResponseCase) -> str:
    canonical = json.dumps(
        case.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _read_yaml_mapping(path: Path) -> Mapping[object, object]:
    try:
        raw = safe_load_unique(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, YAMLError) as exc:
        raise ValueError(f"{path}: unable to read YAML: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return raw


def _read_yaml_mapping_bytes(
    data: bytes,
    *,
    source: _Source,
    remaining_case_records: int,
) -> Mapping[object, object]:
    check_collection_count(
        len(data),
        limit=RESOURCE_LIMITS_V1.case_file_bytes,
        code="case_file_limit",
    )
    try:
        raw = safe_load_unique_bytes(
            data,
            collection_limit=RESOURCE_LIMITS_V1.case_records,
            collection_code="case_records_limit",
            top_level_sequence_limits={"cases": (remaining_case_records, "case_records_limit")},
        )
    except StrictYamlError as exc:
        raise ValueError(f"{source}: unable to read YAML: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: YAML root must be a mapping")
    return raw


def _validation_location_summary(error: ValidationError) -> str:
    locations: list[str] = []
    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(
            component
            for component in item["loc"]
            if type(component) is str and component in _SAFE_CASE_VALIDATION_FIELDS
        )
        if location and location not in locations:
            locations.append(location)
    if not locations:
        return "validation failed"
    return f"validation failed at {', '.join(locations)}"


def _load_model(
    path: Path,
    model_type: type[_ModelT],
    *,
    required_keys: Sequence[str] = (),
) -> _ModelT:
    raw = _read_yaml_mapping(path)
    missing = [key for key in required_keys if key not in raw]
    if missing:
        joined_keys = ", ".join(missing)
        raise ValueError(f"{path}: missing required top-level key(s): {joined_keys}")

    try:
        return model_type.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path}: validation failed: {exc}") from exc


def _load_model_bytes(
    data: bytes,
    source: _Source,
    model_type: type[_ModelT],
    *,
    required_keys: Sequence[str] = (),
    remaining_case_records: int = RESOURCE_LIMITS_V1.case_records,
) -> _ModelT:
    raw = _read_yaml_mapping_bytes(
        data,
        source=source,
        remaining_case_records=remaining_case_records,
    )
    missing = [key for key in required_keys if key not in raw]
    if missing:
        joined_keys = ", ".join(missing)
        raise ValueError(f"{source}: missing required top-level key(s): {joined_keys}")

    raw_cases = raw.get("cases")
    if isinstance(raw_cases, Sequence) and not isinstance(raw_cases, (str, bytes, bytearray)):
        check_collection_count(
            len(raw_cases),
            limit=remaining_case_records,
            code="case_records_limit",
        )

    try:
        return model_type.model_validate(raw)
    except ValidationError as exc:
        detail = _validation_location_summary(exc)
        raise ValueError(f"{source}: {detail}") from None


def _finalize_cases(records: Sequence[tuple[_CaseT, _Source]]) -> tuple[_CaseT, ...]:
    check_collection_count(
        len(records),
        limit=RESOURCE_LIMITS_V1.case_records,
        code="case_records_limit",
    )
    seen_ids: dict[str, _Source] = {}
    scenarios: dict[str, list[tuple[str, _Source]]] = {}

    for case, path in records:
        first_path = seen_ids.get(case.id)
        if first_path is not None:
            raise ValueError(
                f"{path}: duplicate case id {case.id!r}; first defined in {first_path}"
            )
        seen_ids[case.id] = path
        scenarios.setdefault(case.scenario_id, []).append((case.locale, path))

    for scenario_id, localized_records in scenarios.items():
        locales = [locale for locale, _ in localized_records]
        if locales.count("en") != 1 or locales.count("ru") != 1:
            source_paths = dict.fromkeys(path for _, path in localized_records)
            joined_paths = ", ".join(str(path) for path in source_paths)
            raise ValueError(
                f"{joined_paths}: scenario {scenario_id!r} must have "
                "exactly one en and one ru case "
                f"(found en={locales.count('en')}, ru={locales.count('ru')})"
            )

    return tuple(case for case, _ in records)


def parse_response_case_bytes(
    data: bytes,
    *,
    source: _Source,
    remaining_case_records: int = RESOURCE_LIMITS_V1.case_records,
) -> tuple[ResponseCase, ...]:
    """Validate one captured response-case file without cross-file finalization."""

    case_file = _load_model_bytes(
        data,
        source,
        ResponseCaseFile,
        required_keys=_CASE_FILE_KEYS,
        remaining_case_records=remaining_case_records,
    )
    return case_file.cases


def parse_activation_case_bytes(
    data: bytes,
    *,
    source: _Source,
    remaining_case_records: int = RESOURCE_LIMITS_V1.case_records,
) -> tuple[ActivationCase, ...]:
    """Validate one captured activation-case file without cross-file finalization."""

    case_file = _load_model_bytes(
        data,
        source,
        ActivationCaseFile,
        required_keys=_CASE_FILE_KEYS,
        remaining_case_records=remaining_case_records,
    )
    return case_file.cases


def finalize_response_cases(
    records: Sequence[tuple[ResponseCase, _Source]],
) -> tuple[ResponseCase, ...]:
    """Enforce response-case invariants across captured source files."""

    return _finalize_cases(records)


def finalize_activation_cases(
    records: Sequence[tuple[ActivationCase, _Source]],
) -> tuple[ActivationCase, ...]:
    """Enforce activation-case invariants across captured source files."""

    return _finalize_cases(records)


def _read_case_path_once(path: Path, *, limit: int, code: str) -> bytes:
    try:
        directory_fd = open_directory_no_follow(path.parent)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError(f"{path}: unable to read YAML: source open failed") from exc
    try:
        try:
            return read_regular_file_once(
                directory_fd,
                path.name,
                limit=limit,
                code=code,
            )
        except ResourceLimitError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            raise ValueError(f"{path}: unable to read YAML: source read failed") from exc
    finally:
        os.close(directory_fd)


def load_response_cases(paths: Sequence[Path]) -> tuple[ResponseCase, ...]:
    records: list[tuple[ResponseCase, _Source]] = []
    captured_bytes = 0
    for path in paths:
        remaining_bytes = RESOURCE_LIMITS_V1.all_case_files_bytes - captured_bytes
        effective_limit = min(RESOURCE_LIMITS_V1.case_file_bytes, remaining_bytes)
        limit_code = (
            "case_file_limit"
            if effective_limit == RESOURCE_LIMITS_V1.case_file_bytes
            else "all_case_files_limit"
        )
        data = _read_case_path_once(path, limit=effective_limit, code=limit_code)
        captured_bytes += len(data)
        remaining_records = RESOURCE_LIMITS_V1.case_records - len(records)
        parsed = parse_response_case_bytes(
            data,
            source=path,
            remaining_case_records=remaining_records,
        )
        records.extend((case, path) for case in parsed)
    return finalize_response_cases(records)


def load_activation_cases(paths: Sequence[Path]) -> tuple[ActivationCase, ...]:
    records: list[tuple[ActivationCase, _Source]] = []
    captured_bytes = 0
    for path in paths:
        remaining_bytes = RESOURCE_LIMITS_V1.all_case_files_bytes - captured_bytes
        effective_limit = min(RESOURCE_LIMITS_V1.case_file_bytes, remaining_bytes)
        limit_code = (
            "case_file_limit"
            if effective_limit == RESOURCE_LIMITS_V1.case_file_bytes
            else "all_case_files_limit"
        )
        data = _read_case_path_once(path, limit=effective_limit, code=limit_code)
        captured_bytes += len(data)
        remaining_records = RESOURCE_LIMITS_V1.case_records - len(records)
        parsed = parse_activation_case_bytes(
            data,
            source=path,
            remaining_case_records=remaining_records,
        )
        records.extend((case, path) for case in parsed)
    return finalize_activation_cases(records)


def load_manifest(path: Path) -> RunManifest:
    return _load_model(path, RunManifest)
