from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.recovery as recovery_module
import laconian_eval.cli as cli
from laconian_eval import __version__
from laconian_eval.capsule.attempts import derive_attempt_id
from laconian_eval.capsule.events import event_jsonl, make_event
from laconian_eval.capsule.filesystem import UnsupportedFilesystemError
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    EnvironmentV1,
    PlanRowV1,
    SessionEnvironmentV1,
)
from laconian_eval.capsule.verify import VerificationMode, verify_capsule
from laconian_eval.cli import main
from laconian_eval.providers import ProviderError

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONSOLE_SCRIPT = Path(sys.executable).with_name("laconian")
_DYNAMIC_OPERATION = UUID("72345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_SESSION = UUID("82345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_AT = datetime(2026, 8, 29, 15, 0, 0, tzinfo=UTC)


class _FactorySentinel:
    pass


def _install_resume_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exit_code: int,
    announce_target: bool,
) -> list[tuple[Path, object, object]]:
    calls: list[tuple[Path, object, object]] = []
    factory = _FactorySentinel()

    def make_factory() -> object:
        return factory

    def fake_resume_capsule(
        path: Path,
        *,
        provider_factory: object,
        on_target_known: object,
        seams: object,
    ) -> SimpleNamespace:
        calls.append((path, provider_factory, seams))
        if announce_target:
            assert callable(on_target_known)
            on_target_known(path)
        return SimpleNamespace(result=None, exit_code=exit_code, code="test_outcome")

    monkeypatch.setattr(cli, "ProviderFactory", make_factory, raising=False)
    monkeypatch.setattr(cli, "_resume_capsule", fake_resume_capsule, raising=False)
    return calls


def _cli_command(*arguments: str) -> list[str]:
    assert _CONSOLE_SCRIPT.is_file()
    return [str(_CONSOLE_SCRIPT), *arguments]


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _clone_capsule(source: Path, parent: Path) -> Path:
    destination = parent / source.name
    shutil.copytree(source, destination)
    return destination


def _plan_real_capsule(root: Path) -> Path:
    input_root = root / "inputs"
    cases_root = input_root / "cases"
    cases_root.mkdir(parents=True)
    (cases_root / "response.yaml").write_text(
        """schema_version: "1"
kind: response
cases:
  - id: cli-resume-en
    scenario_id: cli-resume
    locale: en
    category: direct
    prompt: Answer briefly.
  - id: cli-resume-ru
    scenario_id: cli-resume
    locale: ru
    category: direct
    prompt: Ответьте кратко.
""",
        encoding="utf-8",
    )
    (input_root / "replay.yaml").write_text(
        """description: Deterministic CLI resume integration fixture.
cli-resume-en:baseline:0:
  output_text: Completed in English.
  response_model: replay-v1
  finish_reason: stop
cli-resume-ru:baseline:0:
  output_text: Завершено по-русски.
  response_model: replay-v1
  finish_reason: stop
""",
        encoding="utf-8",
    )
    manifest = input_root / "manifest.yaml"
    manifest.write_text(
        f"""schema_version: "2"
runner_version: {__version__}
run_name: cli-resume-integration
provider:
  kind: replay
  model: replay-v1
  replay_file: replay.yaml
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
    - dataset_id: cli-resume
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
    results_root = root / "results"
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
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stderr)["planned_requests"] == 2
    capsule = Path(completed.stdout.splitlines()[0])
    assert capsule.is_absolute()
    assert capsule.is_dir()
    return capsule


@pytest.fixture(scope="module")
def real_prepared_capsule(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _plan_real_capsule(tmp_path_factory.mktemp("cli-resume-real"))


def _forbid_provider_binding(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []

    def forbidden(request: object, **_kwargs: object) -> object:
        calls.append(request)
        raise AssertionError("provider binding was reached")

    monkeypatch.setattr(execution_module, "_bind_provider", forbidden)
    return calls


def _install_private_execution_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI orchestration real while avoiding a process-global import-guard install."""

    def matching_authority(
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

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", matching_authority)
    monkeypatch.setattr(
        execution_module,
        "_install_execution_guard",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        lambda *_args, **_kwargs: None,
    )


def _append_inflight_attempt(capsule_path: Path) -> None:
    capsule = CapsuleV1.model_validate_json((capsule_path / "capsule.json").read_bytes())
    environment = EnvironmentV1.model_validate_json(
        (capsule_path / "environment.json").read_bytes()
    )
    plan = PlanRowV1.model_validate_json((capsule_path / "plan.jsonl").read_bytes().splitlines()[0])
    runtime = environment.runtime
    provider = environment.provider
    started = make_event(
        sequence=1,
        run_id=capsule.run_id,
        occurred_at=_DYNAMIC_AT,
        kind="execution_started",
        operation_id=_DYNAMIC_OPERATION,
        execution_session_id=_DYNAMIC_SESSION,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": {
                "schema_version": "1",
                "package_version": environment.package_version,
                "runner_source_sha256": environment.runner_source_sha256,
                "runtime_fingerprint_sha256": runtime.runtime_fingerprint_sha256,
                "python_implementation": runtime.python_implementation,
                "python_version": runtime.python_version,
                "os_family": runtime.os_family,
                "os_release": runtime.os_release,
                "architecture": runtime.architecture,
                "filesystem_class": runtime.filesystem_class,
                "adapter_source_sha256": provider.adapter_source_sha256,
                "sdk_distribution": provider.sdk_distribution,
                "sdk_version": provider.sdk_version,
            },
        },
    )
    attempt_id = derive_attempt_id(capsule.run_id, plan.plan_item_id, 1)
    request_started = make_event(
        sequence=2,
        run_id=capsule.run_id,
        occurred_at=_DYNAMIC_AT,
        kind="request_started",
        operation_id=_DYNAMIC_OPERATION,
        execution_session_id=_DYNAMIC_SESSION,
        payload={
            "call_sequence": 0,
            "plan_item_id": plan.plan_item_id,
            "attempt_id": attempt_id,
            "attempt": 1,
            "retry_of_attempt": None,
            "request_config_sha256": plan.request_config_sha256,
            "prompt_sha256": plan.prompt_sha256,
            "case_definition_sha256": plan.case_definition_sha256,
            "instruction_sha256": plan.instruction_sha256,
            "provider": provider.kind,
            "model": provider.requested_model,
        },
    )
    events = capsule_path / "events.jsonl"
    events.write_bytes(events.read_bytes() + event_jsonl(started) + event_jsonl(request_started))


def _append_seal_request(capsule_path: Path) -> None:
    capsule = CapsuleV1.model_validate_json((capsule_path / "capsule.json").read_bytes())
    seal_requested = make_event(
        sequence=1,
        run_id=capsule.run_id,
        occurred_at=_DYNAMIC_AT,
        kind="seal_requested",
        operation_id=UUID("92345678-1234-4abc-8def-1234567890ab"),
        execution_session_id=None,
        payload={
            "seal_transaction_id": UUID("a2345678-1234-4abc-8def-1234567890ab"),
            "expected_generation_status": "incomplete",
            "prior_event_sequence": 0,
        },
    )
    events = capsule_path / "events.jsonl"
    events.write_bytes(events.read_bytes() + event_jsonl(seal_requested))


@pytest.mark.parametrize("exit_code", [0, 1, 2])
def test_resume_dispatches_one_lexical_absolute_target_and_preserves_exit_code(
    exit_code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = tmp_path / "invocation"
    invocation.mkdir()
    monkeypatch.chdir(invocation)
    calls = _install_resume_stub(
        monkeypatch,
        exit_code=exit_code,
        announce_target=True,
    )

    assert main(["resume", "nested/../capsule"], program="laconian") == exit_code

    captured = capsys.readouterr()
    expected = Path(os.path.abspath("nested/../capsule"))
    assert len(calls) == 1
    assert calls[0][0] == expected
    assert isinstance(calls[0][1], _FactorySentinel)
    assert captured.out == f"{expected}\n"
    assert captured.err == ""


def test_resume_invalid_target_prints_no_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    calls = _install_resume_stub(
        monkeypatch,
        exit_code=2,
        announce_target=False,
    )

    assert main(["resume", "missing-capsule"], program="laconian") == 2

    captured = capsys.readouterr()
    assert len(calls) == 1
    assert calls[0][0] == tmp_path / "missing-capsule"
    assert captured.out == ""
    assert captured.err == ""


def test_resume_target_callback_is_printed_exactly_once_even_if_repeated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = _FactorySentinel()

    def fake_resume_capsule(
        path: Path,
        *,
        provider_factory: object,
        on_target_known: object,
        seams: object,
    ) -> SimpleNamespace:
        del provider_factory, seams
        assert callable(on_target_known)
        on_target_known(path)
        on_target_known(path)
        return SimpleNamespace(result=None, exit_code=1, code="interrupted")

    monkeypatch.setattr(cli, "ProviderFactory", lambda: factory, raising=False)
    monkeypatch.setattr(cli, "_resume_capsule", fake_resume_capsule, raising=False)

    target = tmp_path / "capsule"
    assert main(["resume", str(target)], program="laconian") == 1
    captured = capsys.readouterr()
    assert captured.out == f"{target}\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["res", "capsule"],
        ["resume"],
        ["resume", "capsule", "extra"],
        ["resume", "capsule", "--manifest", "manifest.yaml"],
        ["resume", "capsule", "--input-root", "inputs"],
        ["resume", "capsule", "--source-root", "source"],
        ["resume", "capsule", "--results-root", "results"],
    ],
)
def test_resume_parser_has_exact_nonabbreviated_syntax_and_no_external_inputs(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def forbidden(_path: Path) -> int:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid resume syntax reached dispatch")

    monkeypatch.setattr(cli, "_resume", forbidden, raising=False)

    assert main(argv, program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "usage:" in captured.err


def test_legacy_run_still_rejects_resume_only_positional_shape(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cli, "_run", forbidden)

    assert (
        main(
            [
                "run",
                "manifest.yaml",
                "--results-root",
                "results",
                "capsule",
            ],
            program="laconian",
        )
        == 2
    )
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "unrecognized arguments" in captured.err


@pytest.mark.parametrize(
    "target_kind",
    ["missing", "empty_directory", "regular_file", "symlink"],
)
def test_real_resume_rejects_invalid_target_types_without_mutation_or_provider_access(
    target_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider_calls = _forbid_provider_binding(monkeypatch)
    target = tmp_path / "capsule"
    referent = tmp_path / "referent"
    if target_kind == "empty_directory":
        target.mkdir()
    elif target_kind == "regular_file":
        target.write_bytes(b"not a capsule\n")
    elif target_kind == "symlink":
        referent.mkdir()
        target.symlink_to(referent, target_is_directory=True)

    before_names = tuple(sorted(path.name for path in tmp_path.iterdir()))
    before_file = target.read_bytes() if target_kind == "regular_file" else None
    before_link = os.readlink(target) if target_kind == "symlink" else None

    assert main(["resume", str(target)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert provider_calls == []
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == before_names
    if target_kind == "missing":
        assert not target.exists()
    elif target_kind == "empty_directory":
        assert target.is_dir()
        assert tuple(target.iterdir()) == ()
    elif target_kind == "regular_file":
        assert target.read_bytes() == before_file
    else:
        assert target.is_symlink()
        assert os.readlink(target) == before_link
        assert tuple(referent.iterdir()) == ()


def test_real_resume_busy_is_silent_and_byte_preserving_before_provider_access(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    provider_calls = _forbid_provider_binding(monkeypatch)
    lock_fd = os.open(capsule / ".laconian.lock", os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main(["resume", str(capsule)], program="laconian") == 2
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert provider_calls == []
    assert _snapshot_files(capsule) == before


def test_real_resume_runtime_mismatch_announces_target_but_never_mutates_or_binds_provider(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    provider_calls = _forbid_provider_binding(monkeypatch)

    def runtime_mismatch(*_args: object, **_kwargs: object) -> object:
        raise execution_module.ResumeError("producer_runtime_differs")

    monkeypatch.setattr(execution_module, "_capture_runtime_authority", runtime_mismatch)

    assert main(["resume", str(capsule)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == f"{capsule}\n"
    assert captured.err == ""
    assert provider_calls == []
    assert _snapshot_files(capsule) == before
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "PREPARED"


def test_fresh_console_resume_genuinely_completes_and_only_appends_runtime_ledgers(
    real_prepared_capsule: Path,
    tmp_path: Path,
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)

    completed = subprocess.run(
        _cli_command("resume", str(capsule)),
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{capsule}\n"
    assert completed.stderr == ""
    after = _snapshot_files(capsule)
    assert after.keys() == before.keys()
    assert {
        path: data for path, data in after.items() if path not in {"events.jsonl", "raw.jsonl"}
    } == {path: data for path, data in before.items() if path not in {"events.jsonl", "raw.jsonl"}}
    assert after["events.jsonl"].startswith(before["events.jsonl"])
    assert before["raw.jsonl"] == b""
    assert after["raw.jsonl"]
    event_kinds = [json.loads(row)["kind"] for row in after["events.jsonl"].splitlines()]
    assert event_kinds == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "generation_completed",
    ]
    raw_rows = [json.loads(row) for row in after["raw.jsonl"].splitlines()]
    assert len(raw_rows) == 2
    assert all(row["terminal_reason"] == "success" for row in raw_rows)
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "GENERATION_COMPLETE"


def test_fresh_console_resume_reports_inflight_ambiguity_without_provider_access(
    real_prepared_capsule: Path,
    tmp_path: Path,
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    _append_inflight_attempt(capsule)
    before = _snapshot_files(capsule)

    completed = subprocess.run(
        _cli_command("resume", str(capsule)),
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 1, completed.stderr
    assert completed.stdout == f"{capsule}\n"
    assert completed.stderr == ""
    after = _snapshot_files(capsule)
    assert after == before
    all_kinds = [json.loads(row)["kind"] for row in after["events.jsonl"].splitlines()]
    assert all_kinds == [
        "prepared",
        "execution_started",
        "request_started",
    ]
    assert after["raw.jsonl"] == b""
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "AMBIGUOUS_INFLIGHT"


@pytest.mark.parametrize(
    ("failure_type", "reason"),
    [
        (execution_module.CredentialUnavailable, "credential_unavailable"),
        (execution_module.ProviderUnavailable, "provider_unavailable"),
    ],
)
def test_real_cli_resume_records_request_free_provider_binding_blockers(
    failure_type: type[RuntimeError],
    reason: str,
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    _install_private_execution_injection(monkeypatch)
    binding_requests: list[object] = []

    def blocked(request: object, **_kwargs: object) -> object:
        binding_requests.append(request)
        raise failure_type()

    monkeypatch.setattr(execution_module, "_bind_provider", blocked)

    assert main(["resume", str(capsule)], program="laconian") == 1

    captured = capsys.readouterr()
    assert captured.out == f"{capsule}\n"
    assert captured.err == ""
    assert len(binding_requests) == 1
    after = _snapshot_files(capsule)
    assert after.keys() == before.keys()
    assert {path: data for path, data in after.items() if path != "events.jsonl"} == {
        path: data for path, data in before.items() if path != "events.jsonl"
    }
    event_rows = [json.loads(row) for row in after["events.jsonl"].splitlines()]
    assert [row["kind"] for row in event_rows] == [
        "prepared",
        "execution_started",
        "execution_blocked",
    ]
    assert event_rows[-1]["payload"] == {"reason": reason}
    assert after["raw.jsonl"] == b""
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "PREPARED"


def test_real_cli_resume_records_authentication_stop_after_exactly_one_provider_call(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    _install_private_execution_injection(monkeypatch)
    binding_requests: list[object] = []
    provider_requests: list[object] = []

    class AuthenticationProvider:
        def generate(self, request: object) -> object:
            provider_requests.append(request)
            raise ProviderError(
                "authentication",
                "credential rejected",
                False,
                delivery_certainty="response_received",
            )

    def bind(request: object, **_kwargs: object) -> object:
        binding_requests.append(request)
        return execution_module._PrivateProviderBinding(AuthenticationProvider(), ())

    monkeypatch.setattr(execution_module, "_bind_provider", bind)

    assert main(["resume", str(capsule)], program="laconian") == 1

    captured = capsys.readouterr()
    assert captured.out == f"{capsule}\n"
    assert captured.err == ""
    assert len(binding_requests) == 1
    assert len(provider_requests) == 1
    after = _snapshot_files(capsule)
    assert after.keys() == before.keys()
    assert {
        path: data for path, data in after.items() if path not in {"events.jsonl", "raw.jsonl"}
    } == {path: data for path, data in before.items() if path not in {"events.jsonl", "raw.jsonl"}}
    event_rows = [json.loads(row) for row in after["events.jsonl"].splitlines()]
    assert [row["kind"] for row in event_rows] == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "authentication_stopped",
    ]
    assert event_rows[-1]["payload"]["recovered"] is False
    raw_rows = [json.loads(row) for row in after["raw.jsonl"].splitlines()]
    assert len(raw_rows) == 1
    assert raw_rows[0]["terminal_reason"] == "authentication_stopped"
    assert raw_rows[0]["output_text"] is None
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "AUTHENTICATION_STOPPED"


def test_real_cli_resume_records_request_free_signal_without_provider_call(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    _install_private_execution_injection(monkeypatch)
    binding_requests: list[object] = []
    provider_requests: list[object] = []

    class NeverCalledProvider:
        def generate(self, request: object) -> object:
            provider_requests.append(request)
            raise AssertionError("request-free interruption called provider")

    def bind(request: object, **_kwargs: object) -> object:
        binding_requests.append(request)
        return execution_module._PrivateProviderBinding(NeverCalledProvider(), ())

    def interrupt(*_args: object, **_kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(execution_module, "_bind_provider", bind)
    monkeypatch.setattr(execution_module, "_sanitizer_patterns", interrupt)

    assert main(["resume", str(capsule)], program="laconian") == 1

    captured = capsys.readouterr()
    assert captured.out == f"{capsule}\n"
    assert captured.err == ""
    assert len(binding_requests) == 1
    assert provider_requests == []
    after = _snapshot_files(capsule)
    assert after.keys() == before.keys()
    assert {path: data for path, data in after.items() if path != "events.jsonl"} == {
        path: data for path, data in before.items() if path != "events.jsonl"
    }
    event_rows = [json.loads(row) for row in after["events.jsonl"].splitlines()]
    assert [row["kind"] for row in event_rows] == [
        "prepared",
        "execution_started",
        "execution_interrupted",
    ]
    assert event_rows[-1]["payload"]["reason"] == "signal"
    assert after["raw.jsonl"] == b""
    result = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert result.state == "INTERRUPTED"


@pytest.mark.parametrize("failure_site", ["classification", "capability_probe"])
def test_real_cli_resume_unsupported_filesystem_is_silent_and_byte_preserving(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_site: str,
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    before = _snapshot_files(capsule)
    provider_calls = _forbid_provider_binding(monkeypatch)

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("injected unsupported filesystem")

    if failure_site == "classification":
        monkeypatch.setattr(execution_module, "classify_filesystem", unsupported)
    else:
        monkeypatch.setattr(recovery_module, "run_filesystem_probes", unsupported)

    assert main(["resume", str(capsule)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert provider_calls == []
    assert _snapshot_files(capsule) == before


def test_real_cli_resume_preserves_authenticated_sealing_interrupted_state(
    real_prepared_capsule: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsule = _clone_capsule(real_prepared_capsule, tmp_path)
    _append_seal_request(capsule)
    authenticated = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert authenticated.status == "valid"
    assert authenticated.state == "SEALING_INTERRUPTED"
    before = _snapshot_files(capsule)
    provider_calls = _forbid_provider_binding(monkeypatch)

    assert main(["resume", str(capsule)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == f"{capsule}\n"
    assert captured.err == ""
    assert provider_calls == []
    assert _snapshot_files(capsule) == before
    after = verify_capsule(capsule, mode=VerificationMode.PREPARED)
    assert after.status == "valid"
    assert after.state == "SEALING_INTERRUPTED"
