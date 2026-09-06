from __future__ import annotations

import ast
import builtins
import inspect
import io
import json
import os
import socket
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
import yaml
from capsule_helpers import capsule_v1_payload

import laconian_eval.cli as cli
from laconian_eval.capsule.canonical import canonical_json
from laconian_eval.capsule.capture import CaptureError
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    PostPublishSyncError,
    UnsupportedFilesystemError,
)
from laconian_eval.capsule.prepare import (
    PostPublishVerificationError,
    PreparationError,
    PrepareRequest,
)
from laconian_eval.capsule.record_models import CapsuleV1, VerifyResultV1
from laconian_eval.capsule.verify import VerificationMode
from laconian_eval.cli import main

ROOT = Path(__file__).parents[2]
RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
OPERATION_ID = UUID("223e4567-e89b-42d3-a456-426614174001")
MISSING_PLAN_ID = "1" * 64


class _ForbiddenEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"credential/environment value was read: {key}")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("ambient environment was iterated")

    def __len__(self) -> int:
        raise AssertionError("ambient environment size was inspected")

    def get(self, key: str, default: str | None = None) -> str | None:
        del default
        return self[key]


class _CliOsProxy:
    environ = _ForbiddenEnvironment()
    environb = _ForbiddenEnvironment()

    @staticmethod
    def getenv(key: str, default: str | None = None) -> str | None:
        del default
        return _CliOsProxy.environ[key]

    @staticmethod
    def getenvb(key: bytes, default: bytes | None = None) -> bytes | None:
        del default
        return _CliOsProxy.environb[key]  # type: ignore[index,return-value]

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)


def _capsule() -> CapsuleV1:
    return CapsuleV1.model_validate(capsule_v1_payload())


def _summary(*, warnings: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        case_count=4,
        scenario_count=2,
        locale_case_counts=(("en", 2), ("ru", 2)),
        arm_count=3,
        repetition_count=2,
        planned_request_count=24,
        checkout_binding="unavailable",
        git_state="unavailable",
        uv_lock_availability="unavailable",
        filesystem_class="ext-family",
        provider_kind="fake",
        transport_policy="offline",
        container_image_digest=None,
        verification_warnings=warnings,
    )


def _prepared(path: Path, *, warnings: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        run_id=RUN_ID,
        operation_id=OPERATION_ID,
        capsule=_capsule(),
        summary=_summary(warnings=warnings),
    )


def _expected_summary(prepared: SimpleNamespace) -> dict[str, object]:
    capsule = prepared.capsule
    summary = prepared.summary
    return {
        "arms": summary.arm_count,
        "cases": summary.case_count,
        "claim_intent": capsule.claim_intent,
        "cost": "n/a",
        "hashes": {
            "case_index_sha256": capsule.case_index_sha256,
            "environment_sha256": capsule.environment_sha256,
            "input_index_sha256": capsule.input_index_sha256,
            "manifest_sha256": capsule.manifest_sha256,
            "plan_sha256": capsule.plan_sha256,
            "runner_source_sha256": capsule.runner_source_sha256,
            "source_manifest_commitment_sha256": (capsule.source_manifest_commitment_sha256),
        },
        "locales": dict(summary.locale_case_counts),
        "operational_disclosures": {
            "checkout_binding": summary.checkout_binding,
            "container_image_digest": summary.container_image_digest,
            "filesystem_class": summary.filesystem_class,
            "git_state": summary.git_state,
            "provider_kind": summary.provider_kind,
            "transport_policy": summary.transport_policy,
            "uv_lock_availability": summary.uv_lock_availability,
            "verification_warnings": list(summary.verification_warnings),
        },
        "planned_requests": summary.planned_request_count,
        "repetitions": summary.repetition_count,
        "run_purpose": capsule.run_purpose,
        "scenarios": summary.scenario_count,
    }


def _forbid_provider_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("provider, environment, or network access was attempted")

    monkeypatch.setattr(cli, "_provider", forbidden)
    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _CliOsProxy())


def test_plan_passes_exact_lexical_request_and_prints_stable_channels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = tmp_path / "invocation"
    invocation.mkdir()
    monkeypatch.chdir(invocation)
    _forbid_provider_and_environment(monkeypatch)
    prepared = _prepared(invocation / "results" / str(RUN_ID), warnings=("broader_permissions",))
    requests: list[PrepareRequest] = []

    def fake_prepare(request: PrepareRequest) -> SimpleNamespace:
        requests.append(request)
        return prepared

    monkeypatch.setattr(cli, "prepare_capsule", fake_prepare, raising=False)
    digest = f"sha256:{'0123456789abcdef' * 4}"

    code = main(
        [
            "plan",
            "manifest.yaml",
            "--results-root",
            "results",
            "--input-root",
            "inputs",
            "--source-root",
            "source",
            "--container-image-digest",
            digest,
        ],
        program="laconian",
    )

    captured = capsys.readouterr()
    assert code == 0
    assert requests == [
        PrepareRequest(
            manifest_path=Path("manifest.yaml"),
            results_root=Path("results"),
            invocation_cwd=invocation,
            input_root=Path("inputs"),
            source_root=Path("source"),
            container_image_digest=digest,
        )
    ]
    assert captured.out == f"{prepared.path}\n"
    assert captured.err.encode("utf-8") == canonical_json(_expected_summary(prepared)) + b"\n"
    assert len(captured.err.encode("utf-8")) <= 4096


def test_capsule_cli_never_uses_path_resolve() -> None:
    assert ".resolve(" not in inspect.getsource(cli)


def test_capsule_command_reachable_helpers_have_no_provider_environment_or_network_surface() -> (
    None
):
    module = ast.parse(inspect.getsource(cli))
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    entrypoints = {"_validate", "_plan", "_verify"}
    assert entrypoints <= functions.keys()
    aliases: dict[str, str] = {}

    for node in module.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", 1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            imported_from = node.module or ""
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{imported_from}.{alias.name}".strip(".")

    def resolved_name(node: ast.AST | None, scoped: Mapping[str, str]) -> str | None:
        if isinstance(node, ast.Name):
            return scoped.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            owner = resolved_name(node.value, scoped)
            return None if owner is None else f"{owner}.{node.attr}"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            owner = resolved_name(node.args[0], scoped)
            return None if owner is None else f"{owner}.{node.args[1].value}"
        return None

    def assignment(node: ast.AST) -> tuple[list[str], ast.AST | None]:
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            return targets, node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return [node.target.id], node.value
        return [], None

    for _ in range(len(module.body) + 1):
        changed = False
        for node in module.body:
            targets, value = assignment(node)
            resolved = resolved_name(value, aliases)
            if resolved is None:
                continue
            for target in targets:
                if aliases.get(target) != resolved:
                    aliases[target] = resolved
                    changed = True
        if not changed:
            break

    forbidden_exact = {
        "_provider",
        "os.environ",
        "os.environb",
        "os.getenv",
        "os.getenvb",
    }
    forbidden_prefixes = (
        "http",
        "requests",
        "socket",
        "urllib",
        "laconian_eval.providers",
    )

    def is_forbidden(name: str | None) -> bool:
        if name is None:
            return False
        return name in forbidden_exact or any(
            name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden_prefixes
        )

    reachable: set[str] = set()
    pending = list(entrypoints)
    violations: list[tuple[str, str]] = []
    while pending:
        function_name = pending.pop()
        if function_name in reachable:
            continue
        reachable.add(function_name)
        function = functions[function_name]
        scoped = dict(aliases)
        for node in ast.walk(function):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name.split(".", 1)[0]
                    scoped[local_name] = alias.name
                    if is_forbidden(alias.name):
                        violations.append((function_name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                imported_from = node.module or ""
                for alias in node.names:
                    imported = f"{imported_from}.{alias.name}".strip(".")
                    scoped[alias.asname or alias.name] = imported
                    if is_forbidden(imported):
                        violations.append((function_name, imported))
        for _ in range(len(tuple(ast.walk(function))) + 1):
            changed = False
            for node in ast.walk(function):
                targets, value = assignment(node)
                resolved = resolved_name(value, scoped)
                if resolved is None:
                    continue
                if is_forbidden(resolved):
                    violations.append((function_name, resolved))
                for target in targets:
                    if scoped.get(target) != resolved:
                        scoped[target] = resolved
                        changed = True
            if not changed:
                break
        for node in ast.walk(function):
            candidate: str | None = None
            if isinstance(node, ast.Call):
                candidate = resolved_name(node.func, scoped)
            elif isinstance(node, ast.Attribute):
                candidate = resolved_name(node, scoped)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                candidate = scoped.get(node.id)
            if is_forbidden(candidate):
                assert candidate is not None
                violations.append((function_name, candidate))
            if isinstance(node, ast.Call):
                called = resolved_name(node.func, scoped)
                if called in functions and called not in reachable:
                    pending.append(called)

    assert violations == []


@pytest.mark.parametrize("command", ["validate", "plan", "verify"])
def test_capsule_command_call_graph_cannot_read_global_environment_or_open_network(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    path = ROOT / "evals/cases/response-smoke.yaml"
    namespace = SimpleNamespace(command="validate", path=path)
    if command == "plan":
        namespace = SimpleNamespace(
            command="plan",
            manifest=Path("manifest.yaml"),
            results_root=Path("results"),
            input_root=None,
            source_root=None,
            container_image_digest=None,
        )
        monkeypatch.setattr(
            cli,
            "prepare_capsule",
            lambda _request: _prepared(tmp_path / "results" / str(RUN_ID)),
            raising=False,
        )
    elif command == "verify":
        namespace = SimpleNamespace(command="verify", capsule=Path("capsule"), require=None)
        monkeypatch.setattr(
            cli,
            "verify_capsule",
            lambda _path, *, mode: _verify_result(),
            raising=False,
        )
    parser = SimpleNamespace(parse_args=lambda _argv: namespace)
    monkeypatch.setattr(cli, "_parser", lambda: parser)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("capsule command touched ambient environment or network")

    with pytest.MonkeyPatch.context() as barrier:
        barrier.setattr(os, "environ", _ForbiddenEnvironment())
        barrier.setattr(os, "environb", _ForbiddenEnvironment())
        barrier.setattr(os, "getenv", forbidden)
        barrier.setattr(os, "getenvb", forbidden)
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
        ):
            barrier.setattr(socket, name, forbidden)
        assert main([], program="laconian") == 0


@pytest.mark.parametrize(
    ("input_root", "expected"),
    [(None, None), ("explicit-inputs", Path("explicit-inputs"))],
)
def test_plan_preserves_v2_default_and_explicit_input_root_semantics(
    input_root: str | None,
    expected: Path | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    prepared = _prepared(tmp_path / "results" / str(RUN_ID))
    requests: list[PrepareRequest] = []

    def fake_prepare(request: PrepareRequest) -> SimpleNamespace:
        requests.append(request)
        return prepared

    monkeypatch.setattr(cli, "prepare_capsule", fake_prepare, raising=False)
    argv = ["plan", "source-v2.yaml", "--results-root", "results"]
    if input_root is not None:
        argv.extend(("--input-root", input_root))

    assert main(argv, program="laconian") == 0
    assert len(requests) == 1
    assert requests[0].input_root == expected
    assert requests[0].invocation_cwd == tmp_path
    capsys.readouterr()


def test_plan_surfaces_v1_input_root_rejection_as_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _forbid_provider_and_environment(monkeypatch)
    requests: list[PrepareRequest] = []

    def reject_v1(request: PrepareRequest) -> SimpleNamespace:
        requests.append(request)
        raise CaptureError("v1_input_root_forbidden")

    monkeypatch.setattr(cli, "prepare_capsule", reject_v1, raising=False)

    assert (
        main(
            [
                "plan",
                "source-v1.yaml",
                "--results-root",
                "results",
                "--input-root",
                "inputs",
            ],
            program="laconian",
        )
        == 2
    )
    captured = capsys.readouterr()
    assert len(requests) == 1
    assert requests[0].input_root == Path("inputs")
    assert captured.out == ""
    assert captured.err == "error: authored input capture failed\n"


@pytest.mark.parametrize(
    "value",
    [
        "9" * 64,
        f"sha256:{'9' * 63}",
        f"sha256:{'9' * 65}",
        f"sha256:{'A' * 64}",
        f"SHA256:{'9' * 64}",
        f" sha256:{'9' * 64}",
        f"sha256:{'9' * 64} ",
    ],
)
def test_plan_rejects_nonexact_container_digest_before_preparation(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    calls = 0

    def forbidden(_request: PrepareRequest) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid digest reached preparation")

    monkeypatch.setattr(cli, "prepare_capsule", forbidden, raising=False)

    assert (
        main(
            [
                "plan",
                "manifest.yaml",
                "--results-root",
                "results",
                "--container-image-digest",
                value,
            ],
            program="laconian",
        )
        == 2
    )
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert captured.err.startswith("error: ")


@pytest.mark.parametrize(
    "argv",
    [
        ["plan", "manifest.yaml"],
        ["plan", "manifest.yaml", "--results-root", "results", "--force"],
        ["plan", "manifest.yaml", "--res", "results"],
    ],
)
def test_plan_usage_errors_exit_two_before_preparation(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    calls = 0

    def forbidden(_request: PrepareRequest) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        raise AssertionError("usage error reached preparation")

    monkeypatch.setattr(cli, "prepare_capsule", forbidden, raising=False)

    assert main(argv, program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "usage:" in captured.err


@pytest.mark.parametrize(
    ("failure", "expected_stderr"),
    [
        (PreparationError("invalid_request"), "error: capsule preparation failed\n"),
        (DestinationCollisionError(), "error: capsule publication failed\n"),
        (
            UnsupportedFilesystemError("synthetic remote filesystem"),
            "error: filesystem contract is unsupported\n",
        ),
    ],
)
def test_plan_prepublication_and_collision_failures_leave_stdout_empty(
    failure: BaseException,
    expected_stderr: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)

    def fail(_request: PrepareRequest) -> SimpleNamespace:
        raise failure

    monkeypatch.setattr(cli, "prepare_capsule", fail, raising=False)

    assert main(["plan", "manifest.yaml", "--results-root", "results"], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == expected_stderr


@pytest.mark.parametrize(
    "failure_type",
    [PostPublishSyncError, PostPublishVerificationError],
)
def test_plan_postpublication_failure_prints_owned_absolute_path_once_and_exits_one(
    failure_type: type[PostPublishSyncError] | type[PostPublishVerificationError],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _forbid_provider_and_environment(monkeypatch)
    destination_name = str(RUN_ID)
    publication_path = tmp_path / "original-publication-root" / destination_name

    def fail(_request: PrepareRequest) -> SimpleNamespace:
        raise failure_type(destination_name, publication_path=publication_path)

    monkeypatch.setattr(cli, "prepare_capsule", fail, raising=False)
    namespace = SimpleNamespace(
        command="plan",
        manifest=Path("manifest.yaml"),
        results_root=Path("results"),
        input_root=None,
        source_root=None,
        container_image_digest=None,
    )
    parser = SimpleNamespace(parse_args=lambda _argv: namespace)
    monkeypatch.setattr(cli, "_parser", lambda: parser)

    def forbidden_observation(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("CLI observed or normalized publication_path")

    with pytest.MonkeyPatch.context() as observation_barrier:
        for name in (
            "absolute",
            "exists",
            "lstat",
            "open",
            "read_bytes",
            "read_text",
            "resolve",
            "stat",
        ):
            observation_barrier.setattr(Path, name, forbidden_observation)
        for name in ("lstat", "open", "readlink", "stat"):
            observation_barrier.setattr(os, name, forbidden_observation)
        for name in ("abspath", "expanduser", "normcase", "normpath", "realpath"):
            observation_barrier.setattr(os.path, name, forbidden_observation)
        observation_barrier.setattr(builtins, "open", forbidden_observation)
        observation_barrier.setattr(io, "open", forbidden_observation)
        assert main(["plan", "manifest.yaml", "--results-root", "results"], program="laconian") == 1
    captured = capsys.readouterr()
    assert publication_path.is_absolute()
    assert publication_path != tmp_path / "results" / destination_name
    assert captured.out == f"{publication_path}\n"
    assert captured.out.count(destination_name) == 1
    assert captured.err == "plan failed: capsule publication failed\n"


def _verify_result(
    *,
    status: str = "valid",
    state: str | None = "PREPARED",
    missing: tuple[str, ...] = (MISSING_PLAN_ID,),
    blockers: tuple[str, ...] = ("never_started",),
) -> VerifyResultV1:
    payload: dict[str, object] = {
        "schema_version": "1",
        "status": status,
        "run_id": RUN_ID if status == "valid" else None,
        "state": state if status == "valid" else None,
        "capsule_sha256": (
            "2" * 64
            if status == "valid" and state in {"SEALED_COMPLETE", "SEALED_BLOCKED"}
            else None
        ),
        "missing_plan_item_ids": list(missing if status == "valid" else ()),
        "operational_blocker_codes": list(blockers if status == "valid" else ()),
        "warnings": [],
        "first_error": None,
    }
    if status == "invalid":
        payload["first_error"] = {
            "code": "hash_mismatch",
            "path": "manifest.json",
            "sequence": None,
            "explanation": "capsule verification failed",
        }
    elif status == "unsupported":
        payload["first_error"] = {
            "code": "unsupported_filesystem",
            "path": None,
            "sequence": None,
            "explanation": "filesystem contract is unsupported",
        }
    return VerifyResultV1.model_validate(payload)


@pytest.mark.parametrize(
    ("result", "expected_exit"),
    [
        (_verify_result(), 0),
        (_verify_result(status="invalid", state=None, missing=(), blockers=()), 2),
        (_verify_result(status="busy", state=None, missing=(), blockers=()), 2),
        (_verify_result(status="unsupported", state=None, missing=(), blockers=()), 2),
    ],
)
def test_verify_calls_prepared_mode_once_and_prints_one_canonical_object(
    result: VerifyResultV1,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    calls: list[tuple[Path, VerificationMode]] = []

    def fake_verify(path: Path, *, mode: VerificationMode) -> VerifyResultV1:
        calls.append((path, mode))
        return result

    monkeypatch.setattr(cli, "verify_capsule", fake_verify, raising=False)

    assert main(["verify", "capsule-copy"], program="laconian") == expected_exit
    captured = capsys.readouterr()
    assert calls == [(Path("capsule-copy"), VerificationMode.PREPARED)]
    assert captured.out.encode("utf-8") == canonical_json(result.model_dump(mode="json")) + b"\n"
    assert captured.err == ""
    assert json.loads(captured.out) == result.model_dump(mode="json")


@pytest.mark.parametrize(
    ("state", "missing", "blockers", "requirement", "expected_exit"),
    [
        ("PREPARED", (MISSING_PLAN_ID,), ("never_started",), "generation-complete", 2),
        ("PREPARED", (MISSING_PLAN_ID,), ("never_started",), "sealed", 2),
        ("GENERATION_COMPLETE", (), (), "generation-complete", 0),
        ("GENERATION_COMPLETE", (), (), "sealed", 2),
        ("SEALING_INTERRUPTED", (), (), "generation-complete", 0),
        ("SEALING_INTERRUPTED", (), (), "sealed", 2),
        (
            "SEALING_INTERRUPTED",
            (MISSING_PLAN_ID,),
            ("interrupted",),
            "generation-complete",
            2,
        ),
        ("INTERRUPTED", (MISSING_PLAN_ID,), ("interrupted",), "generation-complete", 2),
        ("INTERRUPTED", (MISSING_PLAN_ID,), ("interrupted",), "sealed", 2),
        (
            "AMBIGUOUS_INFLIGHT",
            (MISSING_PLAN_ID,),
            ("ambiguous_inflight",),
            "generation-complete",
            2,
        ),
        (
            "AMBIGUOUS_INFLIGHT",
            (MISSING_PLAN_ID,),
            ("ambiguous_inflight",),
            "sealed",
            2,
        ),
        (
            "AUTHENTICATION_STOPPED",
            (MISSING_PLAN_ID,),
            ("authentication_stopped",),
            "generation-complete",
            2,
        ),
        (
            "AUTHENTICATION_STOPPED",
            (MISSING_PLAN_ID,),
            ("authentication_stopped",),
            "sealed",
            2,
        ),
        ("SEALED_COMPLETE", (), (), "generation-complete", 0),
        ("SEALED_COMPLETE", (), (), "sealed", 0),
        ("SEALED_BLOCKED", (MISSING_PLAN_ID,), ("interrupted",), "generation-complete", 2),
        ("SEALED_BLOCKED", (MISSING_PLAN_ID,), ("interrupted",), "sealed", 0),
    ],
)
def test_verify_require_changes_only_exit_status(
    state: str,
    missing: tuple[str, ...],
    blockers: tuple[str, ...],
    requirement: str,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    result = _verify_result(state=state, missing=missing, blockers=blockers)
    calls = 0

    def fake_verify(_path: Path, *, mode: VerificationMode) -> VerifyResultV1:
        nonlocal calls
        calls += 1
        assert mode is VerificationMode.PREPARED
        return result

    monkeypatch.setattr(cli, "verify_capsule", fake_verify, raising=False)

    assert (
        main(["verify", "capsule", "--require", requirement], program="laconian") == expected_exit
    )
    captured = capsys.readouterr()
    assert calls == 1
    assert captured.out.encode("utf-8") == canonical_json(result.model_dump(mode="json")) + b"\n"
    assert captured.err == ""


@pytest.mark.parametrize("status", ["invalid", "busy", "unsupported"])
@pytest.mark.parametrize("requirement", ["generation-complete", "sealed"])
def test_verify_require_preserves_nonvalid_canonical_result_and_exit_two(
    status: str,
    requirement: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    result = _verify_result(status=status, state=None, missing=(), blockers=())
    calls = 0

    def fake_verify(_path: Path, *, mode: VerificationMode) -> VerifyResultV1:
        nonlocal calls
        calls += 1
        assert mode is VerificationMode.PREPARED
        return result

    monkeypatch.setattr(cli, "verify_capsule", fake_verify, raising=False)

    assert main(["verify", "capsule", "--require", requirement], program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 1
    assert captured.out.encode("utf-8") == canonical_json(result.model_dump(mode="json")) + b"\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["verify"],
        ["verify", "capsule", "--require", "prepared"],
        ["verify", "capsule", "--require", "generation_complete"],
        ["verify", "capsule", "--req", "sealed"],
    ],
)
def test_verify_rejects_missing_invalid_and_abbreviated_arguments_before_dispatch(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _forbid_provider_and_environment(monkeypatch)
    calls = 0

    def forbidden(_path: Path, *, mode: VerificationMode) -> VerifyResultV1:
        nonlocal calls
        calls += 1
        raise AssertionError(f"usage error reached verifier with {mode}")

    monkeypatch.setattr(cli, "verify_capsule", forbidden, raising=False)

    assert main(argv, program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "usage:" in captured.err


def test_ci_preserves_ubuntu_matrix_and_adds_focused_credential_free_macos_job() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    quality = jobs["quality"]
    expected_actions = [
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d",
    ]

    def nested_keys(value: object) -> Iterator[str]:
        if isinstance(value, dict):
            for key, nested in value.items():
                yield str(key).casefold()
                yield from nested_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from nested_keys(nested)

    assert workflow["permissions"] == {"contents": "read"}
    assert all("permissions" not in job for job in jobs.values())
    assert quality["runs-on"] == "ubuntu-latest"
    assert quality["strategy"] == {
        "fail-fast": False,
        "matrix": {"python-version": ["3.11", "3.14"]},
    }
    assert quality["env"] == {
        "UV_PYTHON": "${{ matrix.python-version }}",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    verify_python_command = (
        "uv run python -c 'import os, sys; expected = tuple(map(int, "
        'os.environ["UV_PYTHON"].split("."))); assert sys.version_info[:2] == expected, '
        "(sys.version, expected)'"
    )
    sync_index = next(
        index
        for index, step in enumerate(quality["steps"])
        if step.get("run") == "uv sync --all-extras --locked"
    )
    assert quality["steps"][sync_index + 1] == {
        "name": "Verify Python selection",
        "run": verify_python_command,
    }
    quality_commands = [step["run"] for step in quality["steps"] if "run" in step]
    assert quality_commands == [
        "uv sync --all-extras --locked",
        verify_python_command,
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy src",
        "uv run pytest tests/test_skill_contract.py tests/test_plugin_contract.py -q",
        "uv run pytest -q",
    ]

    macos = jobs["macos-capsule"]
    assert macos["runs-on"] == "macos-latest"
    assert macos["env"] == {"UV_PYTHON": "3.14", "UV_PYTHON_DOWNLOADS": "never"}
    quality_actions = [step["uses"] for step in quality["steps"] if "uses" in step]
    macos_actions = [step["uses"] for step in macos["steps"] if "uses" in step]
    assert quality_actions == expected_actions
    assert macos_actions == expected_actions
    setup_python = next(
        step
        for step in macos["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    )
    assert setup_python["with"]["python-version"] == "3.14"
    setup_uv = next(
        step
        for step in macos["steps"]
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    )
    assert setup_uv["with"] == {
        "version": "0.12.5",
        "enable-cache": True,
        "cache-dependency-glob": "uv.lock",
    }
    macos_commands = [step["run"] for step in macos["steps"] if "run" in step]
    sync_index = next(
        index
        for index, step in enumerate(macos["steps"])
        if step.get("run") == "uv sync --all-extras --locked"
    )
    assert macos["steps"][sync_index + 1] == {
        "name": "Verify Python selection",
        "run": verify_python_command,
    }
    assert macos_commands == [
        "uv sync --all-extras --locked",
        verify_python_command,
        (
            "uv run pytest tests/capsule/test_posix.py tests/capsule/test_filesystem.py "
            "tests/capsule/test_prepare.py tests/capsule/test_verify_prepared.py "
            "tests/capsule/test_cli_plan.py tests/test_cli.py -q"
        ),
    ]
    workflow_without_allowed_env = {
        **workflow,
        "jobs": {
            name: {key: value for key, value in job.items() if key != "env"}
            if name in {"quality", "macos-capsule"}
            else job
            for name, job in jobs.items()
        },
    }
    forbidden_keys = {
        key
        for key in nested_keys(workflow_without_allowed_env)
        if key in {"env", "environment", "secrets", "secret"} or "secret" in key
    }
    assert forbidden_keys == set()
    serialized = json.dumps(macos, sort_keys=True).casefold()
    assert "secret" not in serialized
    assert "api_key" not in serialized
    assert "environment" not in serialized
