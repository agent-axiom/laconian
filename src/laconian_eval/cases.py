import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from yaml import YAMLError

from laconian_eval.models import (
    ActivationCase,
    ActivationCaseFile,
    ResponseCase,
    ResponseCaseFile,
    RunManifest,
)
from laconian_eval.yaml_io import safe_load_unique

_CASE_FILE_KEYS = ("schema_version", "kind", "cases")
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_CaseT = TypeVar("_CaseT", ResponseCase, ActivationCase)


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


def _finalize_cases(records: Sequence[tuple[_CaseT, Path]]) -> tuple[_CaseT, ...]:
    seen_ids: dict[str, Path] = {}
    scenarios: dict[str, list[tuple[str, Path]]] = {}

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


def load_response_cases(paths: Sequence[Path]) -> tuple[ResponseCase, ...]:
    records: list[tuple[ResponseCase, Path]] = []
    for path in paths:
        case_file = _load_model(path, ResponseCaseFile, required_keys=_CASE_FILE_KEYS)
        records.extend((case, path) for case in case_file.cases)
    return _finalize_cases(records)


def load_activation_cases(paths: Sequence[Path]) -> tuple[ActivationCase, ...]:
    records: list[tuple[ActivationCase, Path]] = []
    for path in paths:
        case_file = _load_model(path, ActivationCaseFile, required_keys=_CASE_FILE_KEYS)
        records.extend((case, path) for case in case_file.cases)
    return _finalize_cases(records)


def load_manifest(path: Path) -> RunManifest:
    return _load_model(path, RunManifest)
