import json
import os
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from laconian_eval.models import CheckResult, RawAttempt, ResponseCase, ScoredAttempt

_SENTENCE_TERMINATORS = frozenset(".?!\u3002\uff01\uff1f")
_TRAILING_CLOSERS = frozenset("\"'\u2019\u201d\u00bb)]}`*_~")
_ALWAYS_NONTERMINAL_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "e.g",
        "i.e",
        "\u0433",
        "\u0438\u043c",
        "\u0442.\u0435",
        "\u0442.\u043a",
        "\u0442.\u0434",
        "\u0442.\u043f",
        "\u0443\u043b",
    }
)
_CONDITIONAL_ABBREVIATIONS = frozenset(
    {
        "etc",
        "vs",
        "no",
        "fig",
        "inc",
        "ltd",
        "\u0434\u0440",
        "\u0440\u0438\u0441",
        "\u0441\u0442\u0440",
    }
)
_URL = re.compile(r"https?://[^\s<>`]+", flags=re.IGNORECASE)


def _next_significant_index(text: str, start: int) -> int | None:
    index = start
    while index < len(text) and (text[index].isspace() or text[index] in _TRAILING_CLOSERS):
        index += 1
    return index if index < len(text) else None


def _preceding_dot_token(text: str, dot_index: int) -> tuple[int, str]:
    start = dot_index - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    return start + 1, text[start + 1 : dot_index].strip(".").casefold()


def _is_initialism(token: str) -> bool:
    parts = token.split(".")
    return len(parts) >= 2 and all(len(part) == 1 and part.isalpha() for part in parts)


def _is_list_marker(text: str, dot_index: int) -> bool:
    if dot_index + 1 >= len(text) or not text[dot_index + 1].isspace():
        return False
    end = dot_index
    start = end - 1
    while start >= 0 and text[start].isalnum():
        start -= 1
    token = text[start + 1 : end]
    if not (token.isdigit() or (len(token) == 1 and token.isascii() and token.isalpha())):
        return False
    previous = start
    while previous >= 0 and text[previous] in " \t":
        previous -= 1
    at_item_boundary = (
        previous < 0 or text[previous] in "\r\n:;([{" or text[previous] in _SENTENCE_TERMINATORS
    )
    return at_item_boundary and _next_significant_index(text, dot_index + 1) is not None


def _is_nonterminal_dot(text: str, dot_index: int) -> bool:
    previous = text[dot_index - 1] if dot_index > 0 else ""
    following = text[dot_index + 1] if dot_index + 1 < len(text) else ""
    if previous.isalnum() and following.isalnum():
        return True
    if _is_list_marker(text, dot_index):
        return True

    _, token = _preceding_dot_token(text, dot_index)
    next_index = _next_significant_index(text, dot_index + 1)
    if next_index is None:
        return False
    if token in _ALWAYS_NONTERMINAL_ABBREVIATIONS or _is_initialism(token):
        return True
    if len(token) == 1 and token.isalpha():
        return True
    return token in _CONDITIONAL_ABBREVIATIONS and not text[next_index].isupper()


def _protect_code_punctuation(text: str, protected: set[int]) -> None:
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        marker_end = index + 1
        while marker_end < len(text) and text[marker_end] == "`":
            marker_end += 1
        marker = text[index:marker_end]
        closing = text.find(marker, marker_end)
        span_end = len(text) if closing < 0 else closing + len(marker)
        protected.update(
            position
            for position in range(index, span_end)
            if text[position] in _SENTENCE_TERMINATORS
        )
        index = span_end


def _protected_punctuation(text: str) -> frozenset[int]:
    protected: set[int] = set()
    _protect_code_punctuation(text, protected)
    for match in _URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in _SENTENCE_TERMINATORS:
            end -= 1
        protected.update(
            position
            for position in range(match.start(), end)
            if text[position] in _SENTENCE_TERMINATORS
        )
    return frozenset(protected)


def _consume_boundary_cluster(text: str, start: int) -> int:
    index = start
    while True:
        while index < len(text) and text[index] in _SENTENCE_TERMINATORS:
            index += 1
        while index < len(text) and text[index] in _TRAILING_CLOSERS:
            index += 1
        if index >= len(text) or text[index] not in _SENTENCE_TERMINATORS:
            return index


def count_sentences(text: str) -> int:
    if not text.strip():
        return 0

    count = 0
    segment_has_content = False
    protected = _protected_punctuation(text)
    index = 0
    while index < len(text):
        character = text[index]
        if character not in _SENTENCE_TERMINATORS:
            if not character.isspace() and character not in _TRAILING_CLOSERS:
                segment_has_content = True
            index += 1
            continue

        if index in protected:
            segment_has_content = True
            index += 1
            continue

        run_end = index + 1
        while run_end < len(text) and text[run_end] in _SENTENCE_TERMINATORS:
            run_end += 1
        run = text[index:run_end]
        if run == "." and _is_nonterminal_dot(text, index):
            segment_has_content = True
            index = run_end
            continue

        if segment_has_content or count == 0:
            count += 1
        segment_has_content = False
        index = _consume_boundary_cluster(text, run_end)

    return max(1, count + int(segment_has_content))


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

    def reject_non_rfc_constant(value: str) -> object:
        raise ValueError(f"non-RFC JSON constant {value!r}")

    parse_detail = "output is a top-level JSON object"
    try:
        parsed = json.loads(output.strip(), parse_constant=reject_non_rfc_constant)
        parsed_successfully = True
    except (json.JSONDecodeError, ValueError) as exc:
        detail = exc.msg if isinstance(exc, json.JSONDecodeError) else str(exc)
        parse_detail = f"output is not strict complete JSON: {detail}"

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


def _revalidate_scored_attempt(scored: ScoredAttempt) -> ScoredAttempt:
    return ScoredAttempt.model_validate(scored.model_dump(mode="python"))


def _revalidate_scored_attempts(
    scored: Sequence[ScoredAttempt],
) -> tuple[ScoredAttempt, ...]:
    return tuple(_revalidate_scored_attempt(attempt) for attempt in scored)


def eligible_for_pairing(scored: ScoredAttempt, require_semantic: bool) -> bool:
    validated = _revalidate_scored_attempt(scored)
    if not validated.hard_pass:
        return False
    return not require_semantic or validated.semantic_pass is True


def _append_scored(file: TextIO, scored: ScoredAttempt) -> None:
    file.write(f"{scored.model_dump_json()}\n")
    file.flush()
    os.fsync(file.fileno())


def write_scored_jsonl(scored: Sequence[ScoredAttempt], path: Path) -> None:
    validated = _revalidate_scored_attempts(scored)
    if path.exists():
        raise FileExistsError(f"{path}: refuse to overwrite existing path")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as output_file:
            for attempt in validated:
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
