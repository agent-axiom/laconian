from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.recovery as recovery_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval.capsule.attempts import normalize_provider_outcome
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.events import event_jsonl, make_event
from laconian_eval.capsule.execution import ResumeError
from laconian_eval.capsule.filesystem import UnsupportedFilesystemError
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.planning import request_config_sha256
from laconian_eval.capsule.record_models import SessionEnvironmentV1
from laconian_eval.capsule.sanitizer import SanitizerPatterns
from laconian_eval.capsule.verify import VerificationMode, verify_capsule
from laconian_eval.cases import response_case_sha256
from laconian_eval.providers import GenerationResult, ProviderError

from .test_prepare import _load_success
from .test_verify_prepared import _prepare_all_input_roles


class _InjectedCrash(BaseException):
    pass


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONSOLE_SCRIPT = Path(sys.executable).with_name("laconian")
_CONTROLLED_RESUME_CHILD = r"""
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import laconian_eval.capsule.execution as execution
from laconian_eval.capsule.record_models import SessionEnvironmentV1
from laconian_eval.providers import GenerationResult

capsule = Path(sys.argv[1])
ready_fd = int(sys.argv[2])
release_fd = int(sys.argv[3])
call_log = Path(sys.argv[4])

def append_audit(row):
    descriptor = os.open(call_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, row.encode() + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def matching_authority(context, *, authored_input_byte_count, filesystem_class):
    del authored_input_byte_count
    environment = context.environment
    runtime = environment.runtime
    provider = environment.provider
    return execution._RuntimeAuthority(
        object(),
        object(),
        filesystem_class,
        SessionEnvironmentV1(
            schema_version="1",
            package_version=environment.package_version,
            runner_source_sha256=environment.runner_source_sha256,
            runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
            python_implementation=runtime.python_implementation,
            python_version=runtime.python_version,
            os_family=runtime.os_family,
            os_release=runtime.os_release,
            architecture=runtime.architecture,
            filesystem_class=filesystem_class,
            adapter_source_sha256=provider.adapter_source_sha256,
            sdk_distribution=provider.sdk_distribution,
            sdk_version=provider.sdk_version,
        ),
    )

class ControlledProvider:
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        append_audit(f"call:{request.case_id}:{request.arm}:{request.repetition}")
        if self.calls == 1:
            os.write(ready_fd, b"R")
            if os.read(release_fd, 1) != b"1":
                raise RuntimeError("provider barrier closed without release")
        return GenerationResult(
            output_text="controlled response",
            response_model="controlled-v1",
        )

def bind_provider(_request):
    append_audit("factory")
    return execution._PrivateProviderBinding(provider, ())

execution._capture_runtime_authority = matching_authority
execution._runtime_checkpoint = lambda *_args, **_kwargs: None
provider = ControlledProvider()
seams = execution._ExecutionSeams(
    utc_now=lambda: datetime.now(UTC),
    install_guard=lambda _policy: None,
    checkpoint=lambda *_args: None,
    private_provider_factory=bind_provider,
)
outcome = execution._resume_capsule(
    capsule,
    provider_factory=execution.ProviderFactory(),
    seams=seams,
)
os.write(1, f"{outcome.exit_code}|{outcome.result.status}|{outcome.result.state}\n".encode())
raise SystemExit(outcome.exit_code)
"""


def _cli_command(*arguments: str) -> list[str]:
    assert _CONSOLE_SCRIPT.is_file()
    return [str(_CONSOLE_SCRIPT), *arguments]


def _plan_real_capsule(tmp_path: Path) -> Path:
    input_root = tmp_path / "real-inputs"
    cases_root = input_root / "cases"
    cases_root.mkdir(parents=True)
    (cases_root / "response.yaml").write_text(
        """schema_version: "1"
kind: response
cases:
  - id: subprocess-en
    scenario_id: subprocess
    locale: en
    category: direct
    prompt: Answer briefly.
  - id: subprocess-ru
    scenario_id: subprocess
    locale: ru
    category: direct
    prompt: Ответьте кратко.
""",
        encoding="utf-8",
    )
    manifest = input_root / "manifest.yaml"
    manifest.write_text(
        """schema_version: "2"
runner_version: 0.1.0.dev0
run_name: resume-subprocess
provider:
  kind: fake
  model: fixture-v1
case_files:
  - cases/response.yaml
arms:
  - baseline
repetitions: 1
arm_order_seed: 17
instruction_placement: system_suffix
generation:
  max_output_tokens: 128
  temperature: null
retry:
  max_transient_retries: 0
  timeout_seconds: 5
price_snapshot: null
capsule:
  run_purpose: integration_smoke
  claim_intent: none
  datasets:
    - dataset_id: resume-subprocess
      dataset_version: fixture-v1
      role: smoke
      case_schema_version: "1"
      case_file_ordinals:
        - 0
  comparisons: []
  protocol_bindings: []
""",
        encoding="utf-8",
    )
    results_root = tmp_path / "real-results"
    results_root.mkdir()
    completed = subprocess.run(
        _cli_command(
            "plan",
            str(manifest),
            "--results-root",
            str(results_root),
            "--source-root",
            str(_REPOSITORY_ROOT),
        ),
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    first_line = completed.stdout.splitlines()[0]
    capsule = Path(first_line)
    assert capsule.is_absolute()
    assert capsule.is_dir()
    return capsule


def _start_controlled_resume(
    capsule: Path,
    call_log: Path,
) -> tuple[subprocess.Popen[str], int, int]:
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    command = [
        sys.executable,
        "-c",
        _CONTROLLED_RESUME_CHILD,
        str(capsule),
        str(ready_write),
        str(release_read),
        str(call_log),
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=_REPOSITORY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            pass_fds=(ready_write, release_read),
        )
    except BaseException:
        os.close(ready_read)
        os.close(ready_write)
        os.close(release_read)
        os.close(release_write)
        raise
    os.close(ready_write)
    os.close(release_read)
    return process, ready_read, release_write


def _wait_for_provider_barrier(
    process: subprocess.Popen[str],
    ready_read: int,
    *,
    timeout_seconds: float = 20.0,
) -> None:
    try:
        readable, _, _ = select.select((ready_read,), (), (), timeout_seconds)
        if not readable:
            raise AssertionError(
                f"timed out waiting for provider pipe barrier: returncode={process.poll()}"
            )
        marker = os.read(ready_read, 1)
        if marker != b"R":
            if process.poll() is None:
                raise AssertionError(
                    "resume child closed provider pipe before signalling readiness "
                    "but is still running"
                )
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(
                "resume child exited before provider pipe barrier: "
                f"returncode={process.returncode}, stdout={stdout!r}, stderr={stderr!r}"
            )
    finally:
        os.close(ready_read)


def _load_resume_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, object, Path]:
    """Prepare with provider bombs, then restore the production adapters for resume."""

    prepared, harness, manifest = _load_success(tmp_path, monkeypatch)
    monkeypatch.setattr(
        execution_module._fake_provider_module,
        "FakeProvider",
        execution_module._FAKE_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._replay_provider_module,
        "ReplayProvider",
        execution_module._REPLAY_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._openai_provider_module,
        "OpenAIProvider",
        execution_module._OPENAI_PROVIDER_TYPE,
    )
    return prepared, harness, manifest


def _verified_context(path: Path) -> object:
    root_fd = open_directory_no_follow(path)
    try:
        inventory = verify_module._scan_inventory(root_fd)
        return verify_module._verify_capsule_context_descriptors(root_fd, inventory)
    finally:
        os.close(root_fd)


def _matching_test_authority(
    context: object,
    *,
    authored_input_byte_count: int,
    filesystem_class: str,
) -> object:
    """Return fixture-matching authority while tests isolate execution from host provenance."""

    del authored_input_byte_count
    environment = context.environment  # type: ignore[attr-defined]
    runtime = environment.runtime
    provider = environment.provider
    return execution_module._RuntimeAuthority(
        object(),
        object(),
        filesystem_class,
        SessionEnvironmentV1(
            schema_version="1",
            package_version=environment.package_version,
            runner_source_sha256=environment.runner_source_sha256,
            runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
            python_implementation=runtime.python_implementation,
            python_version=runtime.python_version,
            os_family=runtime.os_family,
            os_release=runtime.os_release,
            architecture=runtime.architecture,
            filesystem_class=filesystem_class,
            adapter_source_sha256=provider.adapter_source_sha256,
            sdk_distribution=provider.sdk_distribution,
            sdk_version=provider.sdk_version,
        ),
    )


def test_request_reconstruction_uses_only_verified_captured_bytes_and_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)

    # Make every original authored input unavailable before the capsule is read.  The copied
    # runner source was already displaced by `_prepare_all_input_roles`.
    (tmp_path / "all-role-inputs").rename(tmp_path / "all-role-inputs-removed")
    (tmp_path / "all-role-manifest").rename(tmp_path / "all-role-manifest-removed")
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    context = _verified_context(capsule_path)

    cases = {
        case.id: case
        for captured_file in context.captured.case_files  # type: ignore[attr-defined]
        for case in captured_file.cases
    }
    arms = {arm.name: arm for arm in context.captured.arms}  # type: ignore[attr-defined]
    manifest = context.manifest  # type: ignore[attr-defined]

    def forbidden_path_access(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("request reconstruction attempted external path access")

    monkeypatch.setattr(Path, "open", forbidden_path_access)
    monkeypatch.setattr(Path, "read_bytes", forbidden_path_access)
    monkeypatch.setattr(Path, "read_text", forbidden_path_access)
    monkeypatch.setattr(execution_module.os, "open", forbidden_path_access)

    reconstructed = tuple(
        execution_module._derive_captured_request(context, ordinal)  # type: ignore[arg-type]
        for ordinal in range(len(context.plan))  # type: ignore[attr-defined]
    )

    assert tuple(item.row for item in reconstructed) == context.plan  # type: ignore[attr-defined]
    assert {item.row.arm for item in reconstructed} == {
        "baseline",
        "concise",
        "caveman",
        "if",
    }
    assert request_config_sha256(manifest) == reconstructed[0].row.request_config_sha256
    for item in reconstructed:
        row = item.row
        case = cases[row.case_id]
        arm = arms[row.arm]
        request = item.request
        assert item.case == case
        assert item.instruction == arm.instruction
        assert request.case_id == row.case_id
        assert request.arm == row.arm
        assert request.repetition == row.repetition
        assert request.model == manifest.provider.model
        assert request.instructions == arm.instruction
        assert request.prompt == case.prompt
        assert request.max_output_tokens == manifest.generation.max_output_tokens
        assert request.temperature == manifest.generation.temperature
        assert request.timeout_seconds == manifest.retry.timeout_seconds
        assert sha256_bytes(request.prompt.encode("utf-8")) == row.prompt_sha256
        assert response_case_sha256(case) == row.case_definition_sha256
        assert arm.sha256 == row.instruction_sha256
    assert all(
        item.request.instructions is None for item in reconstructed if item.row.arm == "baseline"
    )
    assert all(
        item.request.instructions == arms[item.row.arm].instruction
        for item in reconstructed
        if item.row.arm != "baseline"
    )


def test_provider_request_carries_captured_replay_bytes_not_a_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    context = _verified_context(capsule_path)
    expected = next(
        item.data
        for item in context.captured.files
        if item.record.role == "replay"  # type: ignore[attr-defined]
    )

    request = execution_module._provider_request(context)  # type: ignore[arg-type]

    assert request.provider_kind == "replay"
    assert request.captured_replay_bytes == expected
    assert request.api_key_env is None
    assert "replay.yaml" not in repr(request)
    assert expected.decode("utf-8") not in repr(request)


def test_capacity_budget_reserves_before_mutation_and_poisoning_is_terminal() -> None:
    budget = execution_module._CapacityBudget(current_capsule_bytes=1_000, raw_rows=0)

    budget.reserve_epoch_and_first_attempt()
    reserved = budget.reserved_bytes
    assert reserved == (
        6 * (RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1)
        + RESOURCE_LIMITS_V1.raw_jsonl_row_bytes
        + 1
    )
    assert budget.current_capsule_bytes == 1_000
    assert budget.raw_rows == 0

    budget.consume_exact(500, 0)
    assert budget.current_capsule_bytes == 1_500
    assert budget.reserved_bytes == reserved - 500
    budget.poison()
    with pytest.raises(ResumeError) as caught:
        budget.consume_exact(1, 0)
    assert caught.value.code == "capacity_budget_mismatch"


def test_capacity_budget_rejects_next_attempt_before_request_row_or_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = replace(RESOURCE_LIMITS_V1, raw_rows=1)
    monkeypatch.setattr(execution_module, "RESOURCE_LIMITS_V1", limits)
    budget = execution_module._CapacityBudget(current_capsule_bytes=0, raw_rows=1)

    with pytest.raises(ResumeError) as caught:
        budget.reserve_next_attempt()

    assert caught.value.code == "resource_limit"
    assert budget.current_capsule_bytes == 0
    assert budget.raw_rows == 1
    assert budget.reserved_bytes == 0


def test_capacity_budget_retains_interruption_and_future_seal_allowances() -> None:
    event_row = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
    budget = execution_module._CapacityBudget(current_capsule_bytes=0, raw_rows=0)
    budget.reserve_epoch_and_first_attempt()

    budget.release_attempt_headroom()

    assert budget.reserved_bytes == 2 * event_row


def test_reused_real_guard_process_is_rejected_before_filesystem_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accesses: list[object] = []

    def forbidden_open(path: object) -> int:
        accesses.append(path)
        raise AssertionError("filesystem access after real guard reuse")

    monkeypatch.setattr(execution_module, "_REAL_GUARD_STATE", "poisoned")
    monkeypatch.setattr(execution_module, "open_directory_no_follow", forbidden_open)

    outcome = execution_module._resume_capsule(
        tmp_path / "capsule",
        provider_factory=execution_module.ProviderFactory(),
    )

    assert outcome.exit_code == 2
    assert outcome.result.status == "invalid"
    assert accesses == []


def test_runtime_mismatch_preserves_capsule_and_never_constructs_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    before = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    known_targets: list[Path] = []
    provider_requests: list[object] = []

    def runtime_mismatch(*_args: object, **_kwargs: object) -> object:
        raise ResumeError("producer_runtime_differs")

    def forbidden_provider(request: object) -> object:
        provider_requests.append(request)
        raise AssertionError("provider constructed during runtime mismatch")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", runtime_mismatch)
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("723e4567-e89b-42d3-a456-426614174006"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=forbidden_provider,
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        on_target_known=known_targets.append,
        seams=seams,
    )

    after = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    assert outcome.exit_code == 2
    assert outcome.code == "producer_runtime_differs"
    assert outcome.result.status == "valid"
    assert outcome.result.state == "PREPARED"
    assert outcome.result.warnings[-1] == "producer_runtime_differs"
    assert known_targets == [prepared.path]
    assert provider_requests == []
    assert after == before


def test_capability_probe_unsupported_is_distinct_and_byte_preserving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    before = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    known_targets: list[Path] = []
    provider_requests: list[object] = []

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("injected unsupported filesystem")

    def forbidden_provider(request: object) -> object:
        provider_requests.append(request)
        raise AssertionError("provider constructed on unsupported filesystem")

    monkeypatch.setattr(recovery_module, "run_filesystem_probes", unsupported)
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("723e4567-e89b-42d3-a456-426614174016"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=forbidden_provider,
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        on_target_known=known_targets.append,
        seams=seams,
    )

    after = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    assert outcome.exit_code == 2
    assert outcome.code == "unsupported_filesystem"
    assert outcome.result.status == "unsupported"
    assert outcome.result.first_error is not None
    assert outcome.result.first_error.code == "unsupported_filesystem"
    assert known_targets == []
    assert provider_requests == []
    assert after == before


@pytest.mark.parametrize("fatal_type", [KeyboardInterrupt, _InjectedCrash])
def test_cleanup_fatal_is_propagated_after_owned_descriptors_are_closed(
    fatal_type: type[BaseException],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)

    def runtime_mismatch(*_args: object, **_kwargs: object) -> object:
        raise ResumeError("producer_runtime_differs")

    real_close = execution_module.JournalTransaction.close

    def close_then_interrupt(transaction: object) -> None:
        real_close(transaction)  # type: ignore[arg-type]
        raise fatal_type()

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", runtime_mismatch)
    monkeypatch.setattr(execution_module.JournalTransaction, "close", close_then_interrupt)
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("733e4567-e89b-42d3-a456-426614174006"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
    )

    with pytest.raises(fatal_type):
        execution_module._resume_capsule(
            prepared.path,
            provider_factory=execution_module.ProviderFactory(),
            seams=seams,
        )


def test_factory_immutable_tamper_cannot_append_blocked_or_interrupted_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    manifest_path = prepared.path / "manifest.json"  # type: ignore[attr-defined]
    original_manifest = manifest_path.read_bytes()
    tampered_manifest = original_manifest.replace(b"prepare-smoke", b"prepare-smokf", 1)
    assert tampered_manifest != original_manifest
    assert len(tampered_manifest) == len(original_manifest)
    factory_calls = 0

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            SessionEnvironmentV1(
                schema_version="1",
                package_version=environment.package_version,
                runner_source_sha256=environment.runner_source_sha256,
                runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
                python_implementation=runtime.python_implementation,
                python_version=runtime.python_version,
                os_family=runtime.os_family,
                os_release=runtime.os_release,
                architecture=runtime.architecture,
                filesystem_class=filesystem_class,
                adapter_source_sha256=provider.adapter_source_sha256,
                sdk_distribution=provider.sdk_distribution,
                sdk_version=provider.sdk_version,
            ),
        )

    def tamper_then_block(_request: object) -> object:
        nonlocal factory_calls
        factory_calls += 1
        manifest_path.write_bytes(tampered_manifest)
        raise execution_module.CredentialUnavailable

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    identifiers = iter(
        (
            UUID("743e4567-e89b-42d3-a456-426614174006"),
            UUID("753e4567-e89b-42d3-a456-426614174006"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=tamper_then_block,
    )

    outcome = execution_module._resume_capsule(
        prepared.path,  # type: ignore[attr-defined]
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )
    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()  # type: ignore[attr-defined]
    ]
    manifest_path.write_bytes(original_manifest)

    assert factory_calls == 1
    assert outcome.exit_code == 2
    assert outcome.result.status == "invalid"
    assert event_kinds == ["prepared", "execution_started"]


def test_sealed_looking_unverified_tree_fails_closed_without_callback_or_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    (prepared.path / "seal.json").write_bytes(b"{}\n")
    before = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    known_targets: list[Path] = []
    provider_requests: list[object] = []
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("823e4567-e89b-42d3-a456-426614174007"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=lambda request: provider_requests.append(request),  # type: ignore[arg-type,return-value]
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        on_target_known=known_targets.append,
        seams=seams,
    )

    after = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    assert outcome.exit_code == 2
    assert outcome.result.status == "invalid"
    assert outcome.result.first_error is not None
    assert outcome.result.first_error.code == "invalid_model"
    assert known_targets == []
    assert provider_requests == []
    assert after == before


def test_sealing_interrupted_is_announced_and_preserved_without_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    seal_requested = make_event(
        sequence=1,
        run_id=prepared.run_id,
        occurred_at=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        kind="seal_requested",
        operation_id=UUID("923e4567-e89b-42d3-a456-426614174008"),
        execution_session_id=None,
        payload={
            "seal_transaction_id": "a23e4567-e89b-42d3-a456-426614174009",
            "expected_generation_status": "incomplete",
            "prior_event_sequence": 0,
        },
    )
    with (prepared.path / "events.jsonl").open("ab") as stream:
        stream.write(event_jsonl(seal_requested))
    before = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    known_targets: list[Path] = []
    provider_requests: list[object] = []

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            SessionEnvironmentV1(
                schema_version="1",
                package_version=environment.package_version,
                runner_source_sha256=environment.runner_source_sha256,
                runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
                python_implementation=runtime.python_implementation,
                python_version=runtime.python_version,
                os_family=runtime.os_family,
                os_release=runtime.os_release,
                architecture=runtime.architecture,
                filesystem_class=filesystem_class,
                adapter_source_sha256=provider.adapter_source_sha256,
                sdk_distribution=provider.sdk_distribution,
                sdk_version=provider.sdk_version,
            ),
        )

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("b23e4567-e89b-42d3-a456-426614174010"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=lambda request: provider_requests.append(request),  # type: ignore[arg-type,return-value]
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        on_target_known=known_targets.append,
        seams=seams,
    )

    after = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    assert outcome.exit_code == 2
    assert outcome.code == "sealed"
    assert outcome.result.status == "valid"
    assert outcome.result.state == "SEALING_INTERRUPTED"
    assert known_targets == [prepared.path]
    assert provider_requests == []
    assert after == before


@pytest.mark.parametrize(
    (
        "outcome",
        "attempt_number",
        "max_retries",
        "terminal",
        "terminal_reason",
        "backoff_ms",
        "marker",
    ),
    [
        (
            GenerationResult(output_text="done", response_model="returned-v1"),
            1,
            2,
            True,
            "success",
            None,
            None,
        ),
        (
            ProviderError(
                "transient",
                "retry later",
                True,
                delivery_certainty="definitely_not_sent",
            ),
            1,
            2,
            False,
            None,
            100,
            None,
        ),
        (
            ProviderError(
                "transient",
                "retry later",
                True,
                delivery_certainty="definitely_rejected",
            ),
            3,
            2,
            True,
            "retry_exhausted",
            None,
            None,
        ),
        (
            ProviderError(
                "authentication",
                "invalid credential",
                False,
                delivery_certainty="response_received",
            ),
            1,
            2,
            True,
            "authentication_stopped",
            None,
            "authentication_stopped",
        ),
        (
            ProviderError(
                "timeout",
                "delivery is unknown",
                True,
                delivery_certainty="unknown",
            ),
            1,
            2,
            True,
            "ambiguous_delivery",
            None,
            "delivery_ambiguous",
        ),
        (
            ProviderError(
                "rejected",
                "invalid request",
                False,
                delivery_certainty="definitely_rejected",
            ),
            1,
            2,
            True,
            "provider_rejected",
            None,
            None,
        ),
    ],
)
def test_attempt_decision_precedence_covers_success_retry_auth_and_ambiguity(
    outcome: GenerationResult | ProviderError,
    attempt_number: int,
    max_retries: int,
    terminal: bool,
    terminal_reason: str | None,
    backoff_ms: int | None,
    marker: str | None,
) -> None:
    evidence = normalize_provider_outcome(outcome, patterns=SanitizerPatterns())

    decision = execution_module._attempt_decision(
        evidence,
        attempt_number=attempt_number,
        max_transient_retries=max_retries,
    )

    assert decision.terminal is terminal
    assert decision.terminal_reason == terminal_reason
    assert decision.backoff_ms == backoff_ms
    assert decision.marker == marker


def test_successful_resume_obeys_write_ahead_and_raw_before_finish_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    trace: list[str] = []
    requests: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            trace.append("provider-call")
            requests.append(request)
            return GenerationResult(
                output_text="captured success",
                response_model="returned-v1",
            )

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        trace.append("runtime-preflight")
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        session_environment = SessionEnvironmentV1(
            schema_version="1",
            package_version=environment.package_version,
            runner_source_sha256=environment.runner_source_sha256,
            runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
            python_implementation=runtime.python_implementation,
            python_version=runtime.python_version,
            os_family=runtime.os_family,
            os_release=runtime.os_release,
            architecture=runtime.architecture,
            filesystem_class=filesystem_class,
            adapter_source_sha256=provider.adapter_source_sha256,
            sdk_distribution=provider.sdk_distribution,
            sdk_version=provider.sdk_version,
        )
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            session_environment,
        )

    def checkpoint(*_args: object, **_kwargs: object) -> None:
        trace.append("checkpoint")

    def bind(_request: object) -> object:
        trace.append("provider-factory")
        return execution_module._PrivateProviderBinding(ScriptedProvider(), ())

    real_append_event = execution_module.append_event
    real_append_raw = execution_module.append_raw_attempt
    real_plan_recovery = execution_module._plan_mutator_session_v1
    real_apply_recovery = execution_module._apply_recovery_plan_v1

    def traced_plan_recovery(session: object) -> object:
        trace.append("recovery-planned")
        return real_plan_recovery(session)  # type: ignore[arg-type]

    def traced_apply_recovery(session: object, plan: object) -> object:
        trace.append("recovery-applied")
        return real_apply_recovery(session, plan)  # type: ignore[arg-type]

    def traced_event(transaction: object, event: object) -> None:
        real_append_event(transaction, event)  # type: ignore[arg-type]
        trace.append(f"event:{event.kind}")  # type: ignore[attr-defined]

    def traced_raw(transaction: object, attempt: object) -> None:
        real_append_raw(transaction, attempt)  # type: ignore[arg-type]
        trace.append(f"raw:{attempt.terminal_reason}")  # type: ignore[attr-defined]

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", checkpoint)
    monkeypatch.setattr(execution_module, "append_event", traced_event)
    monkeypatch.setattr(execution_module, "append_raw_attempt", traced_raw)
    monkeypatch.setattr(execution_module, "_plan_mutator_session_v1", traced_plan_recovery)
    monkeypatch.setattr(execution_module, "_apply_recovery_plan_v1", traced_apply_recovery)

    identifiers = iter(
        (
            UUID("323e4567-e89b-42d3-a456-426614174002"),
            UUID("423e4567-e89b-42d3-a456-426614174003"),
        )
    )
    monotonic = iter(range(0, 100_000_000, 1_000_000))
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: next(monotonic),
        sleeper=lambda _seconds: (_ for _ in ()).throw(AssertionError("successful attempt slept")),
        install_guard=lambda _policy: trace.append("guard-installed"),
        checkpoint=None,
        private_provider_factory=bind,
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        on_target_known=lambda _path: trace.append("target-known"),
        seams=seams,
    )

    assert outcome.exit_code == 0
    assert outcome.code == "complete"
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(requests) == 4
    first_start = trace.index("event:request_started")
    first_call = trace.index("provider-call")
    first_raw = trace.index("raw:success")
    first_finish = trace.index("event:request_finished")
    assert trace.index("recovery-planned") < trace.index("target-known")
    assert trace.index("target-known") < trace.index("runtime-preflight")
    assert trace.index("runtime-preflight") < trace.index("recovery-applied")
    assert trace.index("recovery-applied") < trace.index("event:execution_started")
    assert trace.index("event:execution_started") < trace.index("guard-installed")
    assert trace.index("guard-installed") < trace.index("provider-factory")
    assert trace.index("provider-factory") < first_start < first_call < first_raw < first_finish

    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()
    ]
    raw_rows = [json.loads(row) for row in (prepared.path / "raw.jsonl").read_bytes().splitlines()]
    assert event_kinds[0:2] == ["prepared", "execution_started"]
    assert event_kinds[-1] == "generation_completed"
    assert event_kinds.count("request_started") == 4
    assert event_kinds.count("request_finished") == 4
    assert len(raw_rows) == 4
    assert all(row["terminal_reason"] == "success" for row in raw_rows)


def test_signal_during_sanitizer_setup_closes_request_free_epoch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="must not run")

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            SessionEnvironmentV1(
                schema_version="1",
                package_version=environment.package_version,
                runner_source_sha256=environment.runner_source_sha256,
                runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
                python_implementation=runtime.python_implementation,
                python_version=runtime.python_version,
                os_family=runtime.os_family,
                os_release=runtime.os_release,
                architecture=runtime.architecture,
                filesystem_class=filesystem_class,
                adapter_source_sha256=provider.adapter_source_sha256,
                sdk_distribution=provider.sdk_distribution,
                sdk_version=provider.sdk_version,
            ),
        )

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        execution_module,
        "_sanitizer_patterns",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    identifiers = iter(
        (
            UUID("523e4567-e89b-42d3-a456-426614174004"),
            UUID("623e4567-e89b-42d3-a456-426614174005"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )

    assert outcome.exit_code == 1
    assert provider_calls == []
    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()
    ]
    assert event_kinds == ["prepared", "execution_started", "execution_interrupted"]


def test_immutable_tamper_after_request_start_blocks_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="must not run")

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            SessionEnvironmentV1(
                schema_version="1",
                package_version=environment.package_version,
                runner_source_sha256=environment.runner_source_sha256,
                runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
                python_implementation=runtime.python_implementation,
                python_version=runtime.python_version,
                os_family=runtime.os_family,
                os_release=runtime.os_release,
                architecture=runtime.architecture,
                filesystem_class=filesystem_class,
                adapter_source_sha256=provider.adapter_source_sha256,
                sdk_distribution=provider.sdk_distribution,
                sdk_version=provider.sdk_version,
            ),
        )

    manifest_path = prepared.path / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    tampered_manifest = original_manifest.replace(b"prepare-smoke", b"prepare-smokf", 1)
    assert tampered_manifest != original_manifest
    assert len(tampered_manifest) == len(original_manifest)
    real_append_event = execution_module.append_event
    tampered = False

    def append_then_tamper(transaction: object, event: object) -> None:
        nonlocal tampered
        real_append_event(transaction, event)  # type: ignore[arg-type]
        if event.kind == "request_started" and not tampered:  # type: ignore[attr-defined]
            manifest_path.write_bytes(tampered_manifest)
            tampered = True

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(execution_module, "append_event", append_then_tamper)
    identifiers = iter(
        (
            UUID("c23e4567-e89b-42d3-a456-426614174011"),
            UUID("d23e4567-e89b-42d3-a456-426614174012"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: 0,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )
    manifest_path.write_bytes(original_manifest)

    assert tampered is True
    assert provider_calls == []
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()
    ]
    assert event_kinds == ["prepared", "execution_started", "request_started"]
    assert (prepared.path / "raw.jsonl").read_bytes() == b""


def test_ordinary_clock_failure_after_request_start_returns_ambiguity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="returned before clock failure")

    def fake_authority(
        context: object,
        *,
        authored_input_byte_count: int,
        filesystem_class: str,
    ) -> object:
        del authored_input_byte_count
        environment = context.environment  # type: ignore[attr-defined]
        runtime = environment.runtime
        provider = environment.provider
        return execution_module._RuntimeAuthority(
            object(),
            object(),
            filesystem_class,
            SessionEnvironmentV1(
                schema_version="1",
                package_version=environment.package_version,
                runner_source_sha256=environment.runner_source_sha256,
                runtime_fingerprint_sha256=runtime.runtime_fingerprint_sha256,
                python_implementation=runtime.python_implementation,
                python_version=runtime.python_version,
                os_family=runtime.os_family,
                os_release=runtime.os_release,
                architecture=runtime.architecture,
                filesystem_class=filesystem_class,
                adapter_source_sha256=provider.adapter_source_sha256,
                sdk_distribution=provider.sdk_distribution,
                sdk_version=provider.sdk_version,
            ),
        )

    monotonic_calls = 0

    def failing_second_monotonic() -> int:
        nonlocal monotonic_calls
        monotonic_calls += 1
        if monotonic_calls == 1:
            return 0
        raise RuntimeError("post-return clock failed")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", fake_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    identifiers = iter(
        (
            UUID("e23e4567-e89b-42d3-a456-426614174013"),
            UUID("f23e4567-e89b-42d3-a456-426614174014"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=failing_second_monotonic,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,  # type: ignore[attr-defined]
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )

    assert provider_calls and len(provider_calls) == 1
    assert outcome.exit_code == 1
    assert outcome.result.status == "valid"
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()  # type: ignore[attr-defined]
    ]
    assert event_kinds == ["prepared", "execution_started", "request_started"]
    assert (prepared.path / "raw.jsonl").read_bytes() == b""  # type: ignore[attr-defined]


def test_negative_monotonic_delta_is_clamped_after_durable_request_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    trace: list[str] = []

    class ScriptedProvider:
        def generate(self, _request: object) -> GenerationResult:
            trace.append("provider")
            return GenerationResult(output_text="done", response_model="returned-v1")

    real_append_event = execution_module.append_event

    def append_event_with_trace(transaction: object, event: object) -> None:
        real_append_event(transaction, event)  # type: ignore[arg-type]
        trace.append(f"event:{event.kind}")  # type: ignore[attr-defined]

    clock_values = iter((2_000_000, 1_000_000) * 4)

    def monotonic_ns() -> int:
        trace.append("monotonic")
        return next(clock_values)

    def checkpoint(*_args: object, **_kwargs: object) -> None:
        trace.append("checkpoint")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", _matching_test_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", checkpoint)
    monkeypatch.setattr(execution_module, "append_event", append_event_with_trace)
    identifiers = iter(
        (
            UUID("123e4567-e89b-4abc-8def-123456789101"),
            UUID("123e4567-e89b-4abc-8def-123456789102"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=monotonic_ns,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )

    assert outcome.exit_code == 0
    first_start = trace.index("event:request_started")
    first_clock = trace.index("monotonic", first_start)
    first_provider = trace.index("provider")
    post_return_checkpoint = trace.index("checkpoint", first_provider + 1)
    second_clock = trace.index("monotonic", first_clock + 1)
    assert first_start < first_clock < first_provider < post_return_checkpoint < second_clock
    raw_rows = [json.loads(row) for row in (prepared.path / "raw.jsonl").read_bytes().splitlines()]
    assert len(raw_rows) == 4
    assert {row["elapsed_ms"] for row in raw_rows} == {0}


def test_later_plan_capacity_stop_occurs_before_next_start_or_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="done", response_model="returned-v1")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", _matching_test_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        execution_module, "RESOURCE_LIMITS_V1", replace(RESOURCE_LIMITS_V1, raw_rows=1)
    )
    identifiers = iter(
        (
            UUID("123e4567-e89b-4abc-8def-123456789103"),
            UUID("123e4567-e89b-4abc-8def-123456789104"),
        )
    )
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: 0,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )

    assert outcome.exit_code == 1
    assert outcome.result.state == "INTERRUPTED"
    assert len(provider_calls) == 1
    event_kinds = [
        json.loads(row)["kind"]
        for row in (prepared.path / "events.jsonl").read_bytes().splitlines()
    ]
    assert event_kinds == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "execution_interrupted",
    ]
    assert len((prepared.path / "raw.jsonl").read_bytes().splitlines()) == 1


def test_tail_recovery_and_execution_share_one_resume_operation_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    events_path = prepared.path / "events.jsonl"
    events_path.write_bytes(events_path.read_bytes() + b'{"torn":"event"}')
    operation_id = UUID("123e4567-e89b-4abc-8def-123456789105")
    execution_session_id = UUID("123e4567-e89b-4abc-8def-123456789106")
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="done", response_model="returned-v1")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", _matching_test_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    identifiers = iter((operation_id, execution_session_id))
    seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: 0,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=seams,
    )

    assert outcome.exit_code == 0
    assert len(provider_calls) == 4
    event_rows = [json.loads(row) for row in events_path.read_bytes().splitlines()]
    assert event_rows[1]["kind"] == "tail_recovered"
    assert event_rows[-1]["kind"] == "generation_completed"
    assert {row["operation_id"] for row in event_rows[1:]} == {str(operation_id)}
    assert {
        row["execution_session_id"]
        for row in event_rows[1:]
        if row["kind"] not in {"tail_recovered"}
    } == {str(execution_session_id)}


@pytest.mark.parametrize(
    ("crash_after", "expected_exit", "expected_state"),
    [
        ("request_started", 1, "AMBIGUOUS_INFLIGHT"),
        ("raw", 0, "GENERATION_COMPLETE"),
        ("request_finished", 0, "GENERATION_COMPLETE"),
        ("generation_completed", 0, "GENERATION_COMPLETE"),
    ],
)
def test_resume_rederives_after_durable_crash_boundaries_without_recalling_provider(
    crash_after: str,
    expected_exit: int,
    expected_state: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_resume_success(tmp_path, monkeypatch)
    plan_count = len((prepared.path / "plan.jsonl").read_bytes().splitlines())
    provider_calls: list[object] = []

    class ScriptedProvider:
        def generate(self, request: object) -> GenerationResult:
            provider_calls.append(request)
            return GenerationResult(output_text="done", response_model="returned-v1")

    real_append_event = execution_module.append_event
    real_append_raw = execution_module.append_raw_attempt
    seen_events: dict[str, int] = {}
    raw_count = 0

    def crash_after_event(transaction: object, event: object) -> None:
        real_append_event(transaction, event)  # type: ignore[arg-type]
        kind = event.kind  # type: ignore[attr-defined]
        seen_events[kind] = seen_events.get(kind, 0) + 1
        should_crash = kind == crash_after and (
            kind in {"request_started", "generation_completed"} or seen_events[kind] == plan_count
        )
        if should_crash:
            raise _InjectedCrash()

    def crash_after_raw(transaction: object, attempt: object) -> None:
        nonlocal raw_count
        real_append_raw(transaction, attempt)  # type: ignore[arg-type]
        raw_count += 1
        if crash_after == "raw" and raw_count == plan_count:
            raise _InjectedCrash()

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", _matching_test_authority)
    monkeypatch.setattr(execution_module, "_runtime_checkpoint", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(execution_module, "append_event", crash_after_event)
    monkeypatch.setattr(execution_module, "append_raw_attempt", crash_after_raw)
    first_identifiers = iter(
        (
            UUID("123e4567-e89b-4abc-8def-123456789107"),
            UUID("123e4567-e89b-4abc-8def-123456789108"),
        )
    )
    first_seams = execution_module._ExecutionSeams(
        new_uuid=lambda: next(first_identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: 0,
        install_guard=lambda _policy: None,
        private_provider_factory=lambda _request: execution_module._PrivateProviderBinding(
            ScriptedProvider(),
            (),
        ),
    )

    with pytest.raises(_InjectedCrash):
        execution_module._resume_capsule(
            prepared.path,
            provider_factory=execution_module.ProviderFactory(),
            seams=first_seams,
        )

    call_count_after_crash = len(provider_calls)
    monkeypatch.setattr(execution_module, "append_event", real_append_event)
    monkeypatch.setattr(execution_module, "append_raw_attempt", real_append_raw)

    def provider_bomb(_request: object) -> object:
        raise AssertionError("provider factory ran during recovery-only resume")

    second_seams = execution_module._ExecutionSeams(
        new_uuid=lambda: UUID("123e4567-e89b-4abc-8def-123456789109"),
        utc_now=lambda: datetime(2026, 8, 29, 12, 1, tzinfo=UTC),
        install_guard=lambda _policy: None,
        private_provider_factory=provider_bomb,
    )
    recovered = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=second_seams,
    )
    after_recovery = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }
    repeated = execution_module._resume_capsule(
        prepared.path,
        provider_factory=execution_module.ProviderFactory(),
        seams=replace(
            second_seams,
            new_uuid=lambda: UUID("123e4567-e89b-4abc-8def-123456789110"),
        ),
    )
    after_repeated = {
        path.relative_to(prepared.path).as_posix(): path.read_bytes()
        for path in prepared.path.rglob("*")
        if path.is_file()
    }

    assert recovered.exit_code == expected_exit
    assert recovered.result.state == expected_state
    assert repeated.exit_code == expected_exit
    assert repeated.result.state == expected_state
    assert len(provider_calls) == call_count_after_crash
    assert after_repeated == after_recovery


def test_two_process_resumes_serialize_provider_calls_and_verifier_visibility(
    tmp_path: Path,
) -> None:
    capsule = _plan_real_capsule(tmp_path)
    call_log = tmp_path / "provider-calls.log"
    first, first_ready, first_release = _start_controlled_resume(capsule, call_log)
    try:
        _wait_for_provider_barrier(first, first_ready)
        while_busy = verify_capsule(capsule, mode=VerificationMode.PREPARED)
        second, second_ready, second_release = _start_controlled_resume(capsule, call_log)
        os.close(second_release)
        second_stdout, second_stderr = second.communicate(timeout=20)
        assert second.returncode == 2
        assert second_stdout == "2|busy|None\n"
        assert second_stderr == ""
        assert os.read(second_ready, 1) == b""
        os.close(second_ready)
        os.write(first_release, b"1")
        first_stdout, first_stderr = first.communicate(timeout=30)
    finally:
        if first.poll() is None:
            with suppress(OSError):
                os.write(first_release, b"1")
            first.kill()
            first.wait(timeout=10)
        with suppress(OSError):
            os.close(first_release)

    assert while_busy.status == "busy"
    assert first.returncode == 0
    assert first_stdout == "0|valid|GENERATION_COMPLETE\n"
    assert first_stderr == ""
    plan_rows = (capsule / "plan.jsonl").read_bytes().splitlines()
    audit_rows = call_log.read_text(encoding="utf-8").splitlines()
    calls = [row for row in audit_rows if row.startswith("call:")]
    assert len(calls) == len(plan_rows)
    assert len(calls) == len(set(calls))
    assert audit_rows.count("factory") == 1
    after_release = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert after_release.status == "valid"
    assert after_release.state == "GENERATION_COMPLETE"
    event_kinds = [
        json.loads(row)["kind"] for row in (capsule / "events.jsonl").read_bytes().splitlines()
    ]
    assert event_kinds.count("request_started") == len(plan_rows)
    assert event_kinds.count("request_finished") == len(plan_rows)
    assert event_kinds.count("generation_completed") == 1


def test_killed_provider_process_leaves_ambiguity_and_next_resume_never_recalls(
    tmp_path: Path,
) -> None:
    capsule = _plan_real_capsule(tmp_path)
    call_log = tmp_path / "killed-provider-calls.log"
    first, first_ready, first_release = _start_controlled_resume(capsule, call_log)
    try:
        _wait_for_provider_barrier(first, first_ready)
        first.kill()
        first.communicate(timeout=10)
    finally:
        os.close(first_release)
        if first.poll() is None:
            first.kill()
            first.wait(timeout=10)

    second, second_ready, second_release = _start_controlled_resume(capsule, call_log)
    os.close(second_release)
    second_stdout, second_stderr = second.communicate(timeout=20)

    assert first.returncode is not None and first.returncode < 0
    assert second.returncode == 1
    assert second_stdout == "1|valid|AMBIGUOUS_INFLIGHT\n"
    assert second_stderr == ""
    assert os.read(second_ready, 1) == b""
    os.close(second_ready)
    first_plan_row = json.loads((capsule / "plan.jsonl").read_bytes().splitlines()[0])
    assert call_log.read_text(encoding="utf-8").splitlines() == [
        "factory",
        f"call:{first_plan_row['case_id']}:{first_plan_row['arm']}:{first_plan_row['repetition']}",
    ]
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "AMBIGUOUS_INFLIGHT"
    event_kinds = [
        json.loads(row)["kind"] for row in (capsule / "events.jsonl").read_bytes().splitlines()
    ]
    assert event_kinds == ["prepared", "execution_started", "request_started"]
    assert (capsule / "raw.jsonl").read_bytes() == b""


def test_public_real_guard_resume_runs_in_fresh_console_process_and_is_idempotent(
    tmp_path: Path,
) -> None:
    capsule = _plan_real_capsule(tmp_path)

    completed = subprocess.run(
        _cli_command("resume", str(capsule)),
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert completed.stdout == f"{capsule}\n"
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "GENERATION_COMPLETE"
    before = {
        path.relative_to(capsule).as_posix(): path.read_bytes()
        for path in capsule.rglob("*")
        if path.is_file()
    }

    repeated = subprocess.run(
        _cli_command("resume", str(capsule)),
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    after = {
        path.relative_to(capsule).as_posix(): path.read_bytes()
        for path in capsule.rglob("*")
        if path.is_file()
    }
    assert repeated.returncode == 0
    assert repeated.stdout == f"{capsule}\n"
    assert repeated.stderr == ""
    assert after == before


def test_public_resume_import_preflight_drift_is_byte_preserving_and_provider_free(
    tmp_path: Path,
) -> None:
    capsule = _plan_real_capsule(tmp_path)
    before = {
        path.relative_to(capsule).as_posix(): path.read_bytes()
        for path in capsule.rglob("*")
        if path.is_file()
    }
    unowned_import_root = tmp_path / "unowned-import-root"
    unowned_import_root.mkdir()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(unowned_import_root)

    completed = subprocess.run(
        _cli_command("resume", str(capsule)),
        cwd=_REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    after = {
        path.relative_to(capsule).as_posix(): path.read_bytes()
        for path in capsule.rglob("*")
        if path.is_file()
    }
    assert completed.returncode == 2
    assert completed.stdout == f"{capsule}\n"
    assert completed.stderr == ""
    assert after == before
