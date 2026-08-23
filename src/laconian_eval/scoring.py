import json
import os
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from laconian_eval.models import CheckResult, RawAttempt, ResponseCase, ScoredAttempt

_SENTENCE_TERMINATORS = re.compile(r"[.?!\u3002\uff01\uff1f]+")


def count_sentences(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    count = len(_SENTENCE_TERMINATORS.findall(stripped))
    if not _SENTENCE_TERMINATORS.search(stripped[-1]):
        count += 1
    return count


def _validate_raw_identity(case: ResponseCase, raw: RawAttempt) -> None:
    if not raw.terminal:
        raise ValueError(f"raw attempt for {raw.case_id!r} must be terminal")
    if raw.case_id != case.id:
        raise ValueError(f"raw case_id {raw.case_id!r} does not match response case {case.id!r}")
    expected_prompt_sha256 = sha256(case.prompt.encode("utf-8")).hexdigest()
    if raw.prompt_sha256 != expected_prompt_sha256:
        raise ValueError(f"raw prompt_sha256 does not match response case {case.id!r} prompt")


def _literal_checks(case: ResponseCase, output: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for index, literal in enumerate(case.hard_constraints.required_literals):
        passed = literal in output
        checks.append(
            CheckResult(
                name=f"exact.required_literal[{index}]",
                passed=passed,
                detail=f"required literal {literal!r} {'found' if passed else 'missing'}",
            )
        )
    for index, literal in enumerate(case.hard_constraints.forbidden_literals):
        passed = literal not in output
        checks.append(
            CheckResult(
                name=f"exact.forbidden_literal[{index}]",
                passed=passed,
                detail=f"forbidden literal {literal!r} {'absent' if passed else 'present'}",
            )
        )
    return checks


def _json_checks(case: ResponseCase, output: str) -> list[CheckResult]:
    required_keys = case.hard_constraints.required_json_keys
    if not required_keys:
        return []

    parsed: object | None = None
    parsed_successfully = False
    parse_detail = "output is a top-level JSON object"
    try:
        parsed = json.loads(output.strip())
        parsed_successfully = True
    except json.JSONDecodeError as exc:
        parse_detail = f"output is not complete JSON: {exc.msg}"

    parsed_mapping = parsed if isinstance(parsed, dict) else None
    is_object = parsed_mapping is not None
    if parsed_successfully and not is_object:
        parse_detail = "parsed JSON is not a top-level object"
    checks = [CheckResult(name="format.json_object", passed=is_object, detail=parse_detail)]
    for key in required_keys:
        passed = parsed_mapping is not None and key in parsed_mapping
        checks.append(
            CheckResult(
                name=f"format.required_json_key[{key}]",
                passed=passed,
                detail=f"top-level JSON key {key!r} {'found' if passed else 'missing'}",
            )
        )
    return checks


def _sentence_checks(case: ResponseCase, output: str) -> list[CheckResult]:
    constraints = case.hard_constraints
    if constraints.min_sentences is None and constraints.max_sentences is None:
        return []

    sentences = count_sentences(output)
    checks: list[CheckResult] = []
    if constraints.min_sentences is not None:
        checks.append(
            CheckResult(
                name="format.min_sentences",
                passed=sentences >= constraints.min_sentences,
                detail=(f"counted {sentences} sentence(s); minimum is {constraints.min_sentences}"),
            )
        )
    if constraints.max_sentences is not None:
        checks.append(
            CheckResult(
                name="format.max_sentences",
                passed=sentences <= constraints.max_sentences,
                detail=(f"counted {sentences} sentence(s); maximum is {constraints.max_sentences}"),
            )
        )
    return checks


def score_attempt(case: ResponseCase, raw: RawAttempt) -> ScoredAttempt:
    _validate_raw_identity(case, raw)
    if raw.error is not None:
        error_checks = (
            CheckResult(
                name="provider.error",
                passed=False,
                detail=f"provider error: {raw.error.kind}",
            ),
        )
        return ScoredAttempt(raw=raw, checks=error_checks, hard_pass=False)

    assert raw.output_text is not None
    check_list = [
        *_literal_checks(case, raw.output_text),
        *_json_checks(case, raw.output_text),
        *_sentence_checks(case, raw.output_text),
    ]
    checks = tuple(check_list)
    return ScoredAttempt(
        raw=raw,
        checks=checks,
        hard_pass=all(check.passed for check in checks),
    )


def score_terminal_attempts(
    cases: Mapping[str, ResponseCase], raw: Sequence[RawAttempt]
) -> tuple[ScoredAttempt, ...]:
    scored: list[ScoredAttempt] = []
    for attempt in raw:
        if not attempt.terminal:
            continue
        case = cases.get(attempt.case_id)
        if case is None:
            raise ValueError(f"unknown case_id {attempt.case_id!r} in terminal raw attempt")
        scored.append(score_attempt(case, attempt))
    return tuple(scored)


def eligible_for_pairing(scored: ScoredAttempt, require_semantic: bool) -> bool:
    if not scored.hard_pass:
        return False
    return not require_semantic or scored.semantic_pass is True


def _append_scored(file: TextIO, scored: ScoredAttempt) -> None:
    file.write(f"{scored.model_dump_json()}\n")
    file.flush()
    os.fsync(file.fileno())


def write_scored_jsonl(scored: Sequence[ScoredAttempt], path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"{path}: refuse to overwrite existing path")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as output_file:
            for attempt in scored:
                _append_scored(output_file, attempt)
    except FileExistsError as exc:
        raise FileExistsError(f"{path}: refuse to overwrite existing path") from exc


def load_scored_jsonl(path: Path) -> tuple[ScoredAttempt, ...]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: unable to read scored attempts: {exc}") from exc

    if content and not content.endswith("\n"):
        line_number = content.count("\n") + 1
        raise ValueError(f"{path}:{line_number}: unterminated JSON line")

    attempts: list[ScoredAttempt] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"{path}:{line_number}: blank JSONL line")
        try:
            value = json.loads(line)
            attempts.append(ScoredAttempt.model_validate(value))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid scored attempt: {exc}") from exc
    return tuple(attempts)
