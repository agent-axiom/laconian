import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError
from yaml import YAMLError

from laconian_eval.models import (
    JudgeProvenance,
    RawAttempt,
    ResponseCase,
    ScoredAttempt,
    SemanticRubric,
    StrictModel,
)
from laconian_eval.yaml_io import safe_load_unique

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class JudgeRequest(StrictModel):
    response_id: str = Field(pattern=_SHA256_PATTERN)
    prompt: str
    locale: Literal["en", "ru"]
    semantic_rubric: SemanticRubric
    response_text: str


class SemanticJudgment(StrictModel):
    response_id: str = Field(pattern=_SHA256_PATTERN)
    passed: bool
    defect_codes: tuple[str, ...]
    evidence: str = Field(min_length=1, max_length=500)
    judge_provider: str = Field(min_length=1)
    judge_model: str = Field(min_length=1)
    judge_prompt_sha256: str = Field(pattern=_SHA256_PATTERN)


class _JudgmentFile(StrictModel):
    schema_version: Literal["1"]
    description: str = Field(min_length=1)
    judgments: tuple[SemanticJudgment, ...]


def _validate_raw_identity(case: ResponseCase, raw: RawAttempt) -> None:
    if not raw.terminal:
        raise ValueError(f"raw attempt for {raw.case_id!r} must be terminal")
    if raw.case_id != case.id:
        raise ValueError(f"raw case_id {raw.case_id!r} does not match response case {case.id!r}")
    expected_prompt_sha256 = sha256(case.prompt.encode("utf-8")).hexdigest()
    if raw.prompt_sha256 != expected_prompt_sha256:
        raise ValueError(f"raw prompt_sha256 does not match response case {case.id!r} prompt")


def _response_id(raw: RawAttempt) -> str:
    if raw.output_text is None:
        raise ValueError("cannot create a response ID for a provider error")
    preimage = {
        "attempt": raw.attempt,
        "case_id": raw.case_id,
        "instruction_sha256": raw.instruction_sha256,
        "manifest_sha256": raw.manifest_sha256,
        "prompt_sha256": raw.prompt_sha256,
        "repetition": raw.repetition,
        "response_text": raw.output_text,
        "run_id": raw.run_id,
    }
    canonical = json.dumps(
        preimage,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def build_judge_request(case: ResponseCase, raw: RawAttempt) -> JudgeRequest:
    _validate_raw_identity(case, raw)
    if raw.error is not None:
        raise ValueError("cannot build a judge request for a provider error")
    assert raw.output_text is not None
    return JudgeRequest(
        response_id=_response_id(raw),
        prompt=case.prompt,
        locale=case.locale,
        semantic_rubric=case.semantic_rubric,
        response_text=raw.output_text,
    )


def load_judgments(path: Path) -> tuple[SemanticJudgment, ...]:
    try:
        loaded = safe_load_unique(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, YAMLError) as exc:
        raise ValueError(f"{path}: unable to read judgments: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(f"{path}: judgment YAML root must be a mapping")
    try:
        judgment_file = _JudgmentFile.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid judgment file: {exc}") from exc

    seen: set[str] = set()
    for judgment in judgment_file.judgments:
        if judgment.response_id in seen:
            raise ValueError(f"{path}: duplicate judgment response_id {judgment.response_id!r}")
        seen.add(judgment.response_id)
    return judgment_file.judgments


def attach_judgments(
    scored: Sequence[ScoredAttempt],
    judgments: Sequence[SemanticJudgment],
) -> tuple[ScoredAttempt, ...]:
    validated_scored = tuple(
        ScoredAttempt.model_validate(attempt.model_dump(mode="python")) for attempt in scored
    )
    scored_by_id: dict[str, ScoredAttempt] = {}
    for attempt in validated_scored:
        if attempt.raw.output_text is None:
            continue
        response_id = _response_id(attempt.raw)
        if response_id in scored_by_id:
            raise ValueError(f"duplicate scored response_id {response_id!r}")
        scored_by_id[response_id] = attempt

    judgments_by_id: dict[str, SemanticJudgment] = {}
    for judgment in judgments:
        if judgment.response_id in judgments_by_id:
            raise ValueError(f"duplicate judgment response_id {judgment.response_id!r}")
        if judgment.response_id not in scored_by_id:
            raise ValueError(f"unknown response_id {judgment.response_id!r} in judgments")
        if not scored_by_id[judgment.response_id].hard_pass:
            raise ValueError(
                f"judgment response_id {judgment.response_id!r} targets a hard-fail response"
            )
        judgments_by_id[judgment.response_id] = judgment

    attached: list[ScoredAttempt] = []
    for attempt in validated_scored:
        if attempt.raw.output_text is None:
            attached.append(attempt)
            continue
        response_id = _response_id(attempt.raw)
        attached_judgment = judgments_by_id.get(response_id)
        updated = attempt.model_dump(mode="python")
        updated.update(
            {
                "semantic_pass": (
                    attached_judgment.passed if attached_judgment is not None else None
                ),
                "judgment_id": response_id if attached_judgment is not None else None,
                "judge_provenance": (
                    JudgeProvenance(
                        provider=attached_judgment.judge_provider,
                        model=attached_judgment.judge_model,
                        prompt_sha256=attached_judgment.judge_prompt_sha256,
                    )
                    if attached_judgment is not None
                    else None
                ),
            }
        )
        attached.append(ScoredAttempt.model_validate(updated))
    return tuple(attached)
