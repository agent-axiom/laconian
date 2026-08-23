import json
import os
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, TextIO, cast

from pydantic import ValidationError

from laconian_eval.arms import Arm
from laconian_eval.models import (
    ErrorInfo,
    RawAttempt,
    ResponseCase,
    RunManifest,
    TokenUsageModel,
)
from laconian_eval.providers import GenerationRequest, GenerationResult, Provider, ProviderError

ArmName = Literal["baseline", "concise", "caveman", "if"]


@dataclass(frozen=True, slots=True)
class RunPlanItem:
    case: ResponseCase
    arm: Arm
    repetition: int

    @property
    def key(self) -> str:
        return f"{self.case.id}:{self.arm.name}:{self.repetition}"


def manifest_sha256(manifest: RunManifest) -> str:
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def build_run_plan(
    cases: Sequence[ResponseCase],
    arms: Sequence[Arm],
    repetitions: int,
    seed: int,
) -> tuple[RunPlanItem, ...]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    randomizer = random.Random(seed)
    plan: list[RunPlanItem] = []
    for case in cases:
        for repetition in range(repetitions):
            shuffled_arms = list(arms)
            randomizer.shuffle(shuffled_arms)
            plan.extend(
                RunPlanItem(case=case, arm=arm, repetition=repetition) for arm in shuffled_arms
            )
    return tuple(plan)


def load_raw_attempts(path: Path) -> tuple[RawAttempt, ...]:
    if not path.exists():
        return ()

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: unable to read raw attempts: {exc}") from exc

    if content and not content.endswith("\n"):
        line_number = content.count("\n") + 1
        raise ValueError(f"{path}:{line_number}: unterminated JSON line")

    attempts: list[RawAttempt] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"{path}:{line_number}: blank JSONL line")
        try:
            value = json.loads(line)
            attempts.append(RawAttempt.model_validate(value))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"{path}:{line_number}: invalid raw attempt: {exc}") from exc
    return tuple(attempts)


def _raw_key(attempt: RawAttempt) -> str:
    return f"{attempt.case_id}:{attempt.arm}:{attempt.repetition}"


def _is_terminal_authentication(attempt: RawAttempt) -> bool:
    return attempt.terminal and attempt.error is not None and attempt.error.kind == "authentication"


def _redactor(secret_values: Sequence[str]) -> Callable[[str | None], str | None]:
    secrets = tuple(
        sorted(
            dict.fromkeys(secret for secret in secret_values if secret),
            key=len,
            reverse=True,
        )
    )

    def redact(value: str | None) -> str | None:
        if value is None:
            return None
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value

    return redact


def _request(item: RunPlanItem, manifest: RunManifest) -> GenerationRequest:
    return GenerationRequest(
        case_id=item.case.id,
        arm=item.arm.name,
        repetition=item.repetition,
        model=manifest.provider.model,
        instructions=item.arm.instruction,
        prompt=item.case.prompt,
        max_output_tokens=manifest.generation.max_output_tokens,
        temperature=manifest.generation.temperature,
        timeout_seconds=manifest.retry.timeout_seconds,
    )


def _usage(result: GenerationResult) -> TokenUsageModel | None:
    if result.usage is None:
        return None
    return TokenUsageModel(
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        total_tokens=result.usage.total_tokens,
        cached_input_tokens=result.usage.cached_input_tokens,
    )


def _validate_existing(
    attempts: Sequence[RawAttempt],
    *,
    expected_manifest_sha256: str,
    run_id: str,
    path: Path,
) -> dict[str, list[RawAttempt]]:
    by_key: dict[str, list[RawAttempt]] = {}
    for attempt in attempts:
        if attempt.manifest_sha256 != expected_manifest_sha256:
            raise ValueError(f"{path}: existing record has a different manifest_sha256")
        if attempt.run_id != run_id:
            raise ValueError(f"{path}: existing record has a different run_id")
        by_key.setdefault(_raw_key(attempt), []).append(attempt)
    return by_key


def _resume_position(
    existing: Sequence[RawAttempt],
    *,
    max_attempts: int,
    path: Path,
    key: str,
) -> tuple[int, int | None] | None:
    if not existing:
        return 1, None

    expected_attempt = 1
    terminal_seen = False
    for attempt in existing:
        expected_retry = None if expected_attempt == 1 else expected_attempt - 1
        if (
            terminal_seen
            or attempt.attempt != expected_attempt
            or attempt.retry_of_attempt != expected_retry
            or (not attempt.terminal and (attempt.error is None or not attempt.error.retryable))
        ):
            raise ValueError(f"{path}: impossible historical retry chain for {key}")
        terminal_seen = attempt.terminal
        expected_attempt += 1

    previous_attempt = existing[-1].attempt
    if previous_attempt > max_attempts:
        raise ValueError(f"{path}: historical retry chain exceeds retry budget for {key}")
    if terminal_seen:
        terminal_error = existing[-1].error
        if (
            terminal_error is not None
            and terminal_error.retryable
            and previous_attempt < max_attempts
        ):
            raise ValueError(f"{path}: premature retryable terminal for {key}")
        return None
    if previous_attempt >= max_attempts:
        raise ValueError(f"{path}: exhausted nonterminal retry chain for {key}")
    return previous_attempt + 1, previous_attempt


def _append_attempt(file: TextIO, attempt: RawAttempt) -> None:
    line = f"{attempt.model_dump_json()}\n"
    file.write(line)
    file.flush()
    os.fsync(file.fileno())


def run_to_jsonl(
    *,
    manifest: RunManifest,
    cases: Sequence[ResponseCase],
    arms: Sequence[Arm],
    provider: Provider,
    output_path: Path,
    run_id: str,
    secret_values: Sequence[str] = (),
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[RawAttempt, ...]:
    existing = load_raw_attempts(output_path)
    current_manifest_sha256 = manifest_sha256(manifest)
    by_key = _validate_existing(
        existing,
        expected_manifest_sha256=current_manifest_sha256,
        run_id=run_id,
        path=output_path,
    )
    plan = build_run_plan(
        cases,
        arms,
        repetitions=manifest.repetitions,
        seed=manifest.arm_order_seed,
    )
    redact = _redactor(secret_values)
    max_attempts = 1 + manifest.retry.max_transient_retries
    for key, key_attempts in by_key.items():
        _resume_position(
            key_attempts,
            max_attempts=max_attempts,
            path=output_path,
            key=key,
        )
    if any(_is_terminal_authentication(attempt) for attempt in existing):
        return existing

    attempts = list(existing)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output_file:
        for item in plan:
            position = _resume_position(
                by_key.get(item.key, ()),
                max_attempts=max_attempts,
                path=output_path,
                key=item.key,
            )
            if position is None:
                continue
            attempt_number, retry_of_attempt = position
            request = _request(item, manifest)

            while True:
                started_at = datetime.now(UTC)
                monotonic_start = time.monotonic()
                try:
                    result = provider.generate(request)
                except ProviderError as error:
                    elapsed_ms = max(0, int((time.monotonic() - monotonic_start) * 1000))
                    is_authentication = error.kind == "authentication"
                    effective_retryable = error.retryable and not is_authentication
                    will_retry = effective_retryable and attempt_number < max_attempts
                    backoff_ms = 100 * (2 ** (attempt_number - 1)) if will_retry else None
                    attempt = RawAttempt(
                        run_id=run_id,
                        manifest_sha256=current_manifest_sha256,
                        case_id=item.case.id,
                        arm=cast(ArmName, item.arm.name),
                        repetition=item.repetition,
                        attempt=attempt_number,
                        terminal=not will_retry,
                        retry_of_attempt=retry_of_attempt,
                        backoff_ms=backoff_ms,
                        prompt_sha256=sha256(item.case.prompt.encode("utf-8")).hexdigest(),
                        instruction_sha256=item.arm.sha256,
                        provider=manifest.provider.kind,
                        model=manifest.provider.model,
                        started_at=started_at,
                        elapsed_ms=elapsed_ms,
                        error=ErrorInfo(
                            kind=error.kind,
                            message=cast(str, redact(error.message)),
                            retryable=effective_retryable,
                            request_id=redact(error.request_id),
                        ),
                    )
                    _append_attempt(output_file, attempt)
                    attempts.append(attempt)
                    by_key.setdefault(item.key, []).append(attempt)
                    if is_authentication:
                        return tuple(attempts)
                    if not will_retry:
                        break
                    assert backoff_ms is not None
                    sleep(backoff_ms / 1000)
                    retry_of_attempt = attempt_number
                    attempt_number += 1
                    continue

                elapsed_ms = max(0, int((time.monotonic() - monotonic_start) * 1000))
                attempt = RawAttempt(
                    run_id=run_id,
                    manifest_sha256=current_manifest_sha256,
                    case_id=item.case.id,
                    arm=cast(ArmName, item.arm.name),
                    repetition=item.repetition,
                    attempt=attempt_number,
                    terminal=True,
                    retry_of_attempt=retry_of_attempt,
                    prompt_sha256=sha256(item.case.prompt.encode("utf-8")).hexdigest(),
                    instruction_sha256=item.arm.sha256,
                    provider=manifest.provider.kind,
                    model=manifest.provider.model,
                    started_at=started_at,
                    elapsed_ms=elapsed_ms,
                    output_text=cast(str, redact(result.output_text)),
                    usage=_usage(result),
                    request_id=redact(result.request_id),
                    finish_reason=redact(result.finish_reason),
                )
                _append_attempt(output_file, attempt)
                attempts.append(attempt)
                by_key.setdefault(item.key, []).append(attempt)
                break

    return tuple(attempts)
