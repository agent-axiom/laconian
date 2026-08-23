import json
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

import laconian_eval.runner as runner_module
from laconian_eval.arms import Arm
from laconian_eval.models import (
    ErrorInfo,
    GenerationSettings,
    ProviderConfig,
    RawAttempt,
    ResponseCase,
    RetryPolicy,
    RunManifest,
    TokenUsageModel,
)
from laconian_eval.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    TokenUsage,
)
from laconian_eval.runner import (
    build_run_plan,
    load_raw_attempts,
    manifest_sha256,
    run_to_jsonl,
)


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def response_case(case_id: str = "case-001-en") -> ResponseCase:
    return ResponseCase(
        id=case_id,
        scenario_id=case_id.removesuffix("-en").removesuffix("-ru"),
        locale="ru" if case_id.endswith("-ru") else "en",
        category="direct",
        prompt=f"Prompt for {case_id}.",
    )


def arm(name: str, instruction: str | None) -> Arm:
    return Arm(
        name=name,
        instruction=instruction,
        sha256=digest(instruction or ""),
    )


ARMS = (
    arm("baseline", None),
    arm("concise", "Answer concisely."),
    arm("caveman", "Caveman instructions."),
    arm("if", "If instructions."),
)


def run_manifest(
    *,
    retries: int = 2,
    repetitions: int = 1,
    seed: int = 17,
    run_name: str = "runner-test",
    model: str = "fixture-v1",
) -> RunManifest:
    return RunManifest(
        schema_version="1",
        run_name=run_name,
        provider=ProviderConfig(kind="fake", model=model),
        case_files=("cases.yaml",),
        arms=("baseline", "concise", "caveman", "if"),
        repetitions=repetitions,
        arm_order_seed=seed,
        generation=GenerationSettings(max_output_tokens=77, temperature=0.25),
        retry=RetryPolicy(max_transient_retries=retries, timeout_seconds=4.5),
    )


class ScriptedProvider:
    def __init__(self, outcomes: Sequence[GenerationResult | BaseException]) -> None:
        self.outcomes = tuple(outcomes)
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        outcome = self.outcomes[len(self.requests) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def write_attempts(path: Path, attempts: Sequence[RawAttempt]) -> None:
    path.write_text(
        "".join(f"{attempt.model_dump_json()}\n" for attempt in attempts),
        encoding="utf-8",
    )


def existing_attempt(
    *,
    manifest_hash: str,
    run_id: str = "run-1",
    arm_name: str = "baseline",
    attempt: int = 1,
    terminal: bool = True,
    retry_of_attempt: int | None = None,
    backoff_ms: int | None = None,
    error_retryable: bool = True,
    terminal_error: bool = False,
) -> RawAttempt:
    error = None
    output_text: str | None = "Done."
    if not terminal or terminal_error:
        error = ErrorInfo(kind="rate_limit", message="Retry.", retryable=error_retryable)
        output_text = None
    return RawAttempt(
        run_id=run_id,
        manifest_sha256=manifest_hash,
        case_id="case-001-en",
        arm=arm_name,
        repetition=0,
        attempt=attempt,
        terminal=terminal,
        retry_of_attempt=retry_of_attempt,
        backoff_ms=backoff_ms,
        prompt_sha256=digest("Prompt for case-001-en."),
        instruction_sha256=digest(""),
        provider="fake",
        model="fixture-v1",
        started_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        elapsed_ms=5,
        output_text=output_text,
        error=error,
    )


def test_four_arms_write_four_terminal_successes_and_exact_requests(tmp_path: Path) -> None:
    manifest = run_manifest(retries=0)
    case = response_case()
    provider = ScriptedProvider(
        [
            GenerationResult(
                output_text=f"Output {index}.",
                usage=TokenUsage(
                    input_tokens=10 + index,
                    output_tokens=2,
                    total_tokens=12 + index,
                    cached_input_tokens=index,
                ),
                request_id=f"request-{index}",
                finish_reason="stop",
            )
            for index in range(4)
        ]
    )
    path = tmp_path / "raw.jsonl"

    attempts = run_to_jsonl(
        manifest=manifest,
        cases=(case,),
        arms=ARMS,
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=lambda _: None,
    )

    plan = build_run_plan((case,), ARMS, repetitions=1, seed=manifest.arm_order_seed)
    assert provider.requests == [
        GenerationRequest(
            case_id=case.id,
            arm=item.arm.name,
            repetition=0,
            model="fixture-v1",
            instructions=item.arm.instruction,
            prompt=case.prompt,
            max_output_tokens=77,
            temperature=0.25,
            timeout_seconds=4.5,
        )
        for item in plan
    ]
    assert len(attempts) == 4
    assert all(attempt.terminal for attempt in attempts)
    assert all(attempt.error is None for attempt in attempts)
    assert [attempt.output_text for attempt in attempts] == [
        "Output 0.",
        "Output 1.",
        "Output 2.",
        "Output 3.",
    ]
    assert [attempt.arm for attempt in attempts] == [item.arm.name for item in plan]
    assert [attempt.instruction_sha256 for attempt in attempts] == [
        item.arm.sha256 for item in plan
    ]
    assert {attempt.prompt_sha256 for attempt in attempts} == {digest(case.prompt)}
    assert {attempt.provider for attempt in attempts} == {"fake"}
    assert {attempt.model for attempt in attempts} == {"fixture-v1"}
    assert all(attempt.started_at.tzinfo is not None for attempt in attempts)
    assert all(attempt.elapsed_ms >= 0 for attempt in attempts)
    assert load_raw_attempts(path) == attempts


def test_build_run_plan_only_shuffles_arms_within_case_repetition_groups() -> None:
    cases = (response_case("case-001-en"), response_case("case-002-ru"))
    original_arms = tuple(ARMS)
    global_state = random.getstate()

    first = build_run_plan(cases, ARMS, repetitions=3, seed=12345)
    second = build_run_plan(cases, ARMS, repetitions=3, seed=12345)

    assert first == second
    assert random.getstate() == global_state
    assert original_arms == ARMS
    expected_groups = [
        (case.id, repetition) for case in cases for repetition in range(3) for _ in ARMS
    ]
    assert [(item.case.id, item.repetition) for item in first] == expected_groups
    for offset in range(0, len(first), len(ARMS)):
        group = first[offset : offset + len(ARMS)]
        assert {item.arm.name for item in group} == {item.name for item in ARMS}
    assert any(
        tuple(item.arm.name for item in first[offset : offset + len(ARMS)])
        != tuple(item.name for item in ARMS)
        for offset in range(0, len(first), len(ARMS))
    )


def test_build_run_plan_rejects_nonpositive_repetitions() -> None:
    with pytest.raises(ValueError, match="repetitions"):
        build_run_plan((response_case(),), ARMS, repetitions=0, seed=1)


def test_retryable_error_then_success_records_retry_chain_and_backoff(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        [
            ProviderError(
                kind="rate_limit",
                message="Try again.",
                retryable=True,
                request_id="error-request",
            ),
            GenerationResult(output_text="Recovered.", request_id="success-request"),
        ]
    )
    sleeps: list[float] = []

    attempts = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=tmp_path / "raw.jsonl",
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert len(attempts) == 2
    first, second = attempts
    assert (first.attempt, first.terminal, first.retry_of_attempt, first.backoff_ms) == (
        1,
        False,
        None,
        100,
    )
    assert first.error == ErrorInfo(
        kind="rate_limit",
        message="Try again.",
        retryable=True,
        request_id="error-request",
    )
    assert (second.attempt, second.terminal, second.retry_of_attempt, second.backoff_ms) == (
        2,
        True,
        1,
        None,
    )
    assert second.output_text == "Recovered."
    assert second.request_id == "success-request"
    assert {(attempt.case_id, attempt.arm, attempt.repetition) for attempt in attempts} == {
        ("case-001-en", "baseline", 0)
    }
    assert provider.requests == [provider.requests[0], provider.requests[0]]
    assert sleeps == [0.1]


def test_nonretryable_authentication_error_is_terminal_without_sleep(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        [ProviderError(kind="authentication", message="Denied.", retryable=False)]
    )
    sleeps: list[float] = []

    attempts = run_to_jsonl(
        manifest=run_manifest(retries=5),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=tmp_path / "raw.jsonl",
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert len(provider.requests) == 1
    assert sleeps == []
    assert len(attempts) == 1
    assert attempts[0].terminal is True
    assert attempts[0].backoff_ms is None
    assert attempts[0].error is not None
    assert attempts[0].error.kind == "authentication"


def test_retryable_errors_stop_after_retry_budget_with_exponential_backoff(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider(
        [
            ProviderError(kind="overloaded", message=f"Failure {index}.", retryable=True)
            for index in range(1, 5)
        ]
    )
    sleeps: list[float] = []

    attempts = run_to_jsonl(
        manifest=run_manifest(retries=3),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=tmp_path / "raw.jsonl",
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert len(provider.requests) == 4
    assert [attempt.attempt for attempt in attempts] == [1, 2, 3, 4]
    assert [attempt.retry_of_attempt for attempt in attempts] == [None, 1, 2, 3]
    assert [attempt.terminal for attempt in attempts] == [False, False, False, True]
    assert [attempt.backoff_ms for attempt in attempts] == [100, 200, 400, None]
    assert sleeps == [0.1, 0.2, 0.4]


def test_unexpected_provider_exception_propagates_without_error_record(tmp_path: Path) -> None:
    provider = ScriptedProvider([RuntimeError("provider bug")])
    path = tmp_path / "raw.jsonl"

    with pytest.raises(RuntimeError, match="provider bug"):
        run_to_jsonl(
            manifest=run_manifest(),
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=lambda _: None,
        )

    assert load_raw_attempts(path) == ()


def test_resume_skips_terminal_key_without_provider_call(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    first_provider = ScriptedProvider([GenerationResult(output_text="Complete.")])
    existing = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=first_provider,
        output_path=path,
        run_id="run-1",
        sleep=lambda _: None,
    )
    provider = ScriptedProvider([])

    resumed = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=lambda _: None,
    )

    assert resumed == existing
    assert provider.requests == []


def test_resume_skips_valid_sequential_retry_chain_ending_terminal(tmp_path: Path) -> None:
    manifest = run_manifest(retries=2)
    path = tmp_path / "raw.jsonl"
    expected_hash = manifest_sha256(manifest)
    existing = (
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=1,
            terminal=False,
            backoff_ms=100,
        ),
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=2,
            terminal=True,
            retry_of_attempt=1,
        ),
    )
    write_attempts(path, existing)
    provider = ScriptedProvider([])
    sleeps: list[float] = []

    resumed = run_to_jsonl(
        manifest=manifest,
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert resumed == existing
    assert provider.requests == []
    assert sleeps == []


def test_resume_rejects_retryable_terminal_before_retry_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    manifest = run_manifest(retries=2)
    path = tmp_path / "raw.jsonl"
    expected_hash = manifest_sha256(manifest)
    history = (
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=1,
            terminal=False,
            backoff_ms=100,
        ),
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=2,
            terminal=True,
            retry_of_attempt=1,
            error_retryable=True,
            terminal_error=True,
        ),
    )
    write_attempts(path, history)
    original_raw = path.read_bytes()
    provider = ScriptedProvider([])
    sleeps: list[float] = []

    with pytest.raises(ValueError, match="premature") as error:
        run_to_jsonl(
            manifest=manifest,
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=sleeps.append,
        )

    assert str(path) in str(error.value)
    assert path.read_bytes() == original_raw
    assert provider.requests == []
    assert sleeps == []


def test_resume_skips_retryable_terminal_at_exhausted_retry_budget(tmp_path: Path) -> None:
    manifest = run_manifest(retries=2)
    path = tmp_path / "raw.jsonl"
    expected_hash = manifest_sha256(manifest)
    history = (
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=1,
            terminal=False,
            backoff_ms=100,
        ),
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=2,
            terminal=False,
            retry_of_attempt=1,
            backoff_ms=200,
        ),
        existing_attempt(
            manifest_hash=expected_hash,
            attempt=3,
            terminal=True,
            retry_of_attempt=2,
            error_retryable=True,
            terminal_error=True,
        ),
    )
    write_attempts(path, history)
    provider = ScriptedProvider([])
    sleeps: list[float] = []

    resumed = run_to_jsonl(
        manifest=manifest,
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert resumed == history
    assert provider.requests == []
    assert sleeps == []


def test_resume_skips_nonretryable_terminal_error_before_retry_budget(tmp_path: Path) -> None:
    manifest = run_manifest(retries=2)
    path = tmp_path / "raw.jsonl"
    terminal = existing_attempt(
        manifest_hash=manifest_sha256(manifest),
        terminal=True,
        error_retryable=False,
        terminal_error=True,
    )
    write_attempts(path, (terminal,))
    provider = ScriptedProvider([])
    sleeps: list[float] = []

    resumed = run_to_jsonl(
        manifest=manifest,
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert resumed == (terminal,)
    assert provider.requests == []
    assert sleeps == []


@pytest.mark.parametrize(
    "history_spec",
    [
        (
            {"attempt": 1, "terminal": True},
            {"attempt": 2, "terminal": True, "retry_of_attempt": 1},
        ),
        (
            {"attempt": 1, "terminal": True},
            {
                "attempt": 2,
                "terminal": False,
                "retry_of_attempt": 1,
                "backoff_ms": 200,
            },
        ),
        (
            {"attempt": 1, "terminal": False, "backoff_ms": 100},
            {"attempt": 3, "terminal": True, "retry_of_attempt": 1},
        ),
        (
            {
                "attempt": 2,
                "terminal": False,
                "retry_of_attempt": 1,
                "backoff_ms": 200,
            },
            {"attempt": 1, "terminal": True},
        ),
        (
            {"attempt": 1, "terminal": False, "backoff_ms": 100},
            {"attempt": 2, "terminal": True},
        ),
        (
            {
                "attempt": 1,
                "terminal": False,
                "backoff_ms": 100,
                "error_retryable": False,
            },
            {"attempt": 2, "terminal": True, "retry_of_attempt": 1},
        ),
    ],
    ids=(
        "duplicate-terminal",
        "record-after-terminal",
        "attempt-gap",
        "out-of-order",
        "bad-retry-link",
        "nonretryable-nonterminal",
    ),
)
def test_resume_rejects_malformed_history_even_when_terminal_exists(
    tmp_path: Path,
    history_spec: tuple[dict[str, object], ...],
) -> None:
    manifest = run_manifest(retries=5)
    path = tmp_path / "raw.jsonl"
    history = tuple(
        existing_attempt(manifest_hash=manifest_sha256(manifest), **spec) for spec in history_spec
    )
    write_attempts(path, history)
    original_raw = path.read_bytes()
    provider = ScriptedProvider([])
    sleeps: list[float] = []

    with pytest.raises(ValueError) as error:
        run_to_jsonl(
            manifest=manifest,
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=sleeps.append,
        )

    assert str(path) in str(error.value)
    assert path.read_bytes() == original_raw
    assert provider.requests == []
    assert sleeps == []


def test_resume_continues_nonterminal_retry_chain(tmp_path: Path) -> None:
    manifest = run_manifest(retries=2)
    path = tmp_path / "raw.jsonl"
    prior = existing_attempt(
        manifest_hash=manifest_sha256(manifest),
        attempt=1,
        terminal=False,
        backoff_ms=100,
    )
    write_attempts(path, (prior,))
    provider = ScriptedProvider([GenerationResult(output_text="Recovered.")])
    sleeps: list[float] = []

    attempts = run_to_jsonl(
        manifest=manifest,
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=sleeps.append,
    )

    assert attempts[0] == prior
    assert len(attempts) == 2
    assert attempts[1].attempt == 2
    assert attempts[1].retry_of_attempt == 1
    assert attempts[1].terminal is True
    assert attempts[1].output_text == "Recovered."
    assert len(provider.requests) == 1
    assert sleeps == []


def test_resume_rejects_exhausted_nonterminal_retry_chain(tmp_path: Path) -> None:
    manifest = run_manifest(retries=1)
    path = tmp_path / "raw.jsonl"
    first = existing_attempt(
        manifest_hash=manifest_sha256(manifest),
        attempt=1,
        terminal=False,
        backoff_ms=100,
    )
    exhausted = existing_attempt(
        manifest_hash=manifest_sha256(manifest),
        attempt=2,
        terminal=False,
        retry_of_attempt=1,
        backoff_ms=200,
    )
    write_attempts(path, (first, exhausted))
    provider = ScriptedProvider([GenerationResult(output_text="Must not run.")])

    with pytest.raises(ValueError, match="nonterminal") as error:
        run_to_jsonl(
            manifest=manifest,
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=lambda _: None,
        )

    assert str(path) in str(error.value)
    assert provider.requests == []


def test_resume_rejects_different_manifest_hash(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    write_attempts(path, (existing_attempt(manifest_hash="different"),))
    provider = ScriptedProvider([GenerationResult(output_text="Must not run.")])

    with pytest.raises(ValueError, match="manifest") as error:
        run_to_jsonl(
            manifest=run_manifest(),
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=lambda _: None,
        )

    assert str(path) in str(error.value)
    assert provider.requests == []


def test_resume_rejects_mixed_run_ids(tmp_path: Path) -> None:
    manifest = run_manifest()
    path = tmp_path / "raw.jsonl"
    expected_hash = manifest_sha256(manifest)
    write_attempts(
        path,
        (
            existing_attempt(manifest_hash=expected_hash, run_id="run-1"),
            existing_attempt(
                manifest_hash=expected_hash,
                run_id="another-run",
                arm_name="concise",
            ),
        ),
    )
    provider = ScriptedProvider([GenerationResult(output_text="Must not run.")])

    with pytest.raises(ValueError, match="run_id") as error:
        run_to_jsonl(
            manifest=manifest,
            cases=(response_case(),),
            arms=(ARMS[0],),
            provider=provider,
            output_path=path,
            run_id="run-1",
            sleep=lambda _: None,
        )

    assert str(path) in str(error.value)
    assert provider.requests == []


def test_error_secrets_are_redacted_from_records_and_raw_file(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    provider = ScriptedProvider(
        [
            ProviderError(
                kind="authentication",
                message="token-123 then token then token-123",
                retryable=False,
                request_id="request-token-123-token",
            )
        ]
    )

    attempts = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        secret_values=("token", "", "token-123"),
        sleep=lambda _: None,
    )

    error = attempts[0].error
    assert error is not None
    assert error.message == "[REDACTED] then [REDACTED] then [REDACTED]"
    assert error.request_id == "request-[REDACTED]-[REDACTED]"
    raw = path.read_text(encoding="utf-8")
    assert "token-123" not in raw
    assert "token" not in raw
    assert raw.count("[REDACTED]") == 5


def test_success_secrets_are_redacted_from_records_and_raw_file(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    provider = ScriptedProvider(
        [
            GenerationResult(
                output_text="secret-long then secret",
                request_id="request-secret-long-secret",
                finish_reason="finish-secret",
            )
        ]
    )

    attempts = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        secret_values=("secret", "", "secret-long"),
        sleep=lambda _: None,
    )

    attempt = attempts[0]
    assert attempt.output_text == "[REDACTED] then [REDACTED]"
    assert attempt.request_id == "request-[REDACTED]-[REDACTED]"
    assert attempt.finish_reason == "finish-[REDACTED]"
    raw = path.read_text(encoding="utf-8")
    assert "secret-long" not in raw
    assert "secret" not in raw
    assert raw.count("[REDACTED]") == 5


def test_each_attempt_is_fsynced_and_parseable_before_next_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "raw.jsonl"
    fsync_calls: list[int] = []

    def record_fsync(file_descriptor: int) -> None:
        fsync_calls.append(file_descriptor)

    monkeypatch.setattr(runner_module.os, "fsync", record_fsync)

    class InspectingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: GenerationRequest) -> GenerationResult:
            self.calls += 1
            if self.calls == 1:
                raise ProviderError(kind="temporary", message="Retry.", retryable=True)
            raw = path.read_text(encoding="utf-8")
            assert raw.endswith("\n")
            lines = raw.splitlines()
            assert len(lines) == 1
            assert json.loads(lines[0])["attempt"] == 1
            return GenerationResult(output_text="Done.")

    provider = InspectingProvider()
    attempts = run_to_jsonl(
        manifest=run_manifest(),
        cases=(response_case(),),
        arms=(ARMS[0],),
        provider=provider,
        output_path=path,
        run_id="run-1",
        sleep=lambda _: None,
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line) for line in lines)
    assert len(fsync_calls) == len(attempts) == 2


def test_load_raw_attempts_returns_empty_tuple_for_missing_file(tmp_path: Path) -> None:
    assert load_raw_attempts(tmp_path / "missing.jsonl") == ()


@pytest.mark.parametrize("invalid_line", ["", "{", "{}"])
def test_load_raw_attempts_reports_path_and_line_for_invalid_lines(
    tmp_path: Path,
    invalid_line: str,
) -> None:
    path = tmp_path / "invalid.jsonl"
    valid = existing_attempt(manifest_hash="manifest").model_dump_json()
    path.write_text(f"{valid}\n{invalid_line}\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_raw_attempts(path)

    assert f"{path}:2" in str(error.value)


def test_load_raw_attempts_preserves_valid_file_order(tmp_path: Path) -> None:
    path = tmp_path / "raw.jsonl"
    first = existing_attempt(manifest_hash="manifest", terminal=False, backoff_ms=100)
    second = existing_attempt(
        manifest_hash="manifest",
        attempt=2,
        retry_of_attempt=1,
    )
    write_attempts(path, (first, second))

    assert load_raw_attempts(path) == (first, second)


def test_raw_attempt_requires_exactly_one_output_or_error() -> None:
    valid = existing_attempt(manifest_hash="manifest")
    payload = valid.model_dump(mode="python")

    with pytest.raises(ValidationError, match="exactly one"):
        RawAttempt.model_validate({**payload, "output_text": None, "error": None})
    with pytest.raises(ValidationError, match="exactly one"):
        RawAttempt.model_validate(
            {
                **payload,
                "output_text": "Done.",
                "error": ErrorInfo(kind="failure", message="No.", retryable=False),
            }
        )

    empty_output = RawAttempt.model_validate({**payload, "output_text": "", "error": None})
    assert empty_output.output_text == ""


def test_token_usage_rejects_cached_tokens_above_input_tokens() -> None:
    with pytest.raises(ValidationError, match="cached_input_tokens"):
        TokenUsageModel(
            input_tokens=3,
            output_tokens=2,
            total_tokens=5,
            cached_input_tokens=4,
        )


def test_raw_models_are_frozen_and_forbid_extra_fields() -> None:
    attempt = existing_attempt(manifest_hash="manifest")

    with pytest.raises(ValidationError, match="extra_forbidden"):
        RawAttempt.model_validate({**attempt.model_dump(), "unknown": True})
    with pytest.raises(ValidationError, match="frozen"):
        attempt.output_text = "Changed."  # type: ignore[misc]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ErrorInfo.model_validate(
            {
                "kind": "failure",
                "message": "No.",
                "retryable": False,
                "unknown": True,
            }
        )


def test_manifest_sha256_is_canonical_and_sensitive_to_meaningful_changes() -> None:
    manifest = run_manifest()
    equivalent = RunManifest.model_validate(manifest.model_dump(mode="json"))
    changed = run_manifest(model="fixture-v2")

    assert manifest_sha256(manifest) == manifest_sha256(equivalent)
    assert manifest_sha256(manifest) != manifest_sha256(changed)
