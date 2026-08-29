from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
import yaml

import laconian_eval.capsule.execution as execution_module
from laconian_eval.capsule.execution import (
    CredentialUnavailable,
    ProviderBinding,
    ProviderFactory,
    ProviderFactoryRequest,
    ProviderUnavailable,
    ResumeError,
    resume_capsule,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.prepare import prepare_capsule
from laconian_eval.capsule.record_models import SessionEnvironmentV1
from laconian_eval.providers import (
    FakeProvider,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ReplayProvider,
    TokenUsage,
)
from laconian_eval.providers.openai import OpenAIProvider

from .test_prepare import _install_harness, _manifest_payload, _request

_DIGEST = "a" * 64
_SECRET = "credential-CANARY-do-not-disclose"
_REPLAY_CANARY = b"replay-CANARY-do-not-disclose"


def _factory_request(
    *,
    provider_kind: str = "fake",
    api_key_env: str | None = None,
    captured_replay_bytes: bytes | None = None,
) -> ProviderFactoryRequest:
    return ProviderFactoryRequest(
        provider_kind=provider_kind,
        requested_model="fixture-v1",
        api_key_env=api_key_env,
        timeout_seconds=5.0,
        adapter_source_sha256=_DIGEST,
        transport_policy="openai-direct-v1" if provider_kind == "openai" else "offline",
        sdk_distribution="openai" if provider_kind == "openai" else None,
        sdk_version="3.0.0" if provider_kind == "openai" else None,
        captured_replay_bytes=captured_replay_bytes,
    )


class _SecretProvider:
    def __repr__(self) -> str:
        return f"SecretProvider({_SECRET})"


class _ExecutionOsProxy:
    def __init__(self, environment: Mapping[str, str]) -> None:
        self.environ = environment

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)


def _single_plan_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_transient_retries: int = 0,
) -> Path:
    source = tmp_path / "execution-source"
    cases = source / "cases"
    cases.mkdir(parents=True)
    (cases / "response.yaml").write_bytes(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "kind": "response",
                "cases": [
                    {
                        "id": "execution-001-en",
                        "scenario_id": "execution-001",
                        "locale": "en",
                        "category": "direct",
                        "prompt": "Return captured evidence.",
                    },
                    {
                        "id": "execution-001-ru",
                        "scenario_id": "execution-001",
                        "locale": "ru",
                        "category": "direct",
                        "prompt": "Верните зафиксированные свидетельства.",
                    },
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    payload = _manifest_payload(arms=["baseline"])
    retry = payload["retry"]
    assert isinstance(retry, dict)
    retry["max_transient_retries"] = max_transient_retries
    manifest = source / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    )
    results = tmp_path / "execution-results"
    results.mkdir()
    _install_harness(monkeypatch, results)
    prepared = prepare_capsule(_request(manifest, results))

    # Preparation deliberately installs construction bombs in the provider modules. Resume
    # verifies those module exports, so restore the exact repository-owned classes first.
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
    return prepared.path


def _matching_runtime_authority(
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


class _ScriptedProvider:
    def __init__(self, outcomes: list[GenerationResult | ProviderError | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls.append(request)
        if not self.outcomes:
            raise AssertionError("scripted provider was called after its final outcome")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _seams_for_provider(
    provider: _ScriptedProvider,
    *,
    credential_values: tuple[str, ...] = (),
    sleeps: list[float] | None = None,
    stop_before_attempt: Callable[[object], str | None] | None = None,
    install_guard: Callable[[object], object] | None = None,
    factory_calls: list[ProviderFactoryRequest] | None = None,
    factory_error: Exception | None = None,
) -> object:
    identifiers = iter(
        (
            UUID("723e4567-e89b-42d3-a456-426614174020"),
            UUID("823e4567-e89b-42d3-a456-426614174021"),
            UUID("923e4567-e89b-42d3-a456-426614174022"),
            UUID("a23e4567-e89b-42d3-a456-426614174023"),
        )
    )
    monotonic = iter(range(0, 100_000_000, 1_000_000))

    def bind(request: ProviderFactoryRequest) -> object:
        if factory_calls is not None:
            factory_calls.append(request)
        if factory_error is not None:
            raise factory_error
        return execution_module._PrivateProviderBinding(provider, credential_values)

    def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return execution_module._ExecutionSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        monotonic_ns=lambda: next(monotonic),
        sleeper=sleep,
        install_guard=(lambda _policy: None) if install_guard is None else install_guard,
        stop_before_attempt=(
            (lambda _row: None) if stop_before_attempt is None else stop_before_attempt
        ),
        private_provider_factory=bind,
    )


def _install_fast_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        execution_module,
        "_capture_runtime_authority",
        _matching_runtime_authority,
    )
    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        lambda *_args, **_kwargs: None,
    )


def _journal_rows(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = [json.loads(row) for row in (path / "events.jsonl").read_bytes().splitlines()]
    raw = [json.loads(row) for row in (path / "raw.jsonl").read_bytes().splitlines()]
    return events, raw


def test_provider_factory_dtos_are_frozen_slotted_and_hide_sensitive_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _factory_request(
        provider_kind="replay",
        captured_replay_bytes=_REPLAY_CANARY,
    )
    provider = FakeProvider({})
    binding = ProviderBinding(
        provider_kind="fake",
        adapter_source_sha256=_DIGEST,
        provider=provider,
        credential_values=(),
    )
    monkeypatch.setattr(FakeProvider, "__repr__", lambda _self: repr(_SecretProvider()))

    assert [field.name for field in fields(request)] == [
        "provider_kind",
        "requested_model",
        "api_key_env",
        "timeout_seconds",
        "adapter_source_sha256",
        "transport_policy",
        "sdk_distribution",
        "sdk_version",
        "captured_replay_bytes",
    ]
    assert [field.name for field in fields(binding)] == [
        "provider_kind",
        "adapter_source_sha256",
        "provider",
        "credential_values",
    ]
    assert fields(request)[-1].repr is False
    assert fields(binding)[-2].repr is False
    assert fields(binding)[-1].repr is False
    assert _REPLAY_CANARY.decode() not in repr(request)
    assert _SECRET not in repr(binding)
    assert not hasattr(request, "__dict__")
    assert not hasattr(binding, "__dict__")
    with pytest.raises(FrozenInstanceError):
        request.requested_model = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        binding.provider = object()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("provider_kind", 1),
        ("requested_model", 1),
        ("api_key_env", b"API_KEY"),
        ("timeout_seconds", 5),
        ("adapter_source_sha256", b"a" * 64),
        ("transport_policy", object()),
        ("sdk_distribution", object()),
        ("sdk_version", object()),
        ("captured_replay_bytes", bytearray(b"fixture")),
    ],
)
def test_provider_factory_request_rejects_nonexact_boundary_types(
    field_name: str,
    invalid: object,
) -> None:
    values = {
        "provider_kind": "replay",
        "requested_model": "fixture-v1",
        "api_key_env": None,
        "timeout_seconds": 5.0,
        "adapter_source_sha256": _DIGEST,
        "transport_policy": "offline",
        "sdk_distribution": None,
        "sdk_version": None,
        "captured_replay_bytes": b"entry: value\n",
    }
    values[field_name] = invalid

    with pytest.raises((TypeError, ValueError)):
        ProviderFactoryRequest(**values)  # type: ignore[arg-type]


def test_provider_factory_request_never_invokes_hostile_equality() -> None:
    class HostileEquality:
        def __eq__(self, _other: object) -> bool:
            raise AssertionError("hostile equality was invoked")

    with pytest.raises(ResumeError) as caught:
        ProviderFactoryRequest(
            provider_kind="fake",
            requested_model="fixture-v1",
            api_key_env=None,
            timeout_seconds=5.0,
            adapter_source_sha256=_DIGEST,
            transport_policy=HostileEquality(),  # type: ignore[arg-type]
            sdk_distribution=None,
            sdk_version=None,
            captured_replay_bytes=None,
        )

    assert caught.value.code == "invalid_provider_factory_request"


def test_resume_public_signature_has_no_orchestration_hooks() -> None:
    parameters = inspect.signature(resume_capsule).parameters

    assert list(parameters) == ["path", "provider_factory"]
    assert parameters["path"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters["provider_factory"].kind is inspect.Parameter.KEYWORD_ONLY


def test_provider_factory_is_an_exact_repository_owned_capability() -> None:
    factory = ProviderFactory()

    assert type(factory) is ProviderFactory
    assert not hasattr(factory, "__dict__")

    class ForgedFactory(ProviderFactory):
        pass

    with pytest.raises(ProviderUnavailable):
        ForgedFactory().create(_factory_request())


def test_provider_factory_rejects_rebound_repository_adapter_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[object] = []

    class ReboundFakeProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            constructed.append(self)

    monkeypatch.setattr(execution_module, "FakeProvider", ReboundFakeProvider)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())

    assert constructed == []


def test_provider_factory_rejects_coordinated_public_and_private_adapter_rebinding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = execution_module._FAKE_PROVIDER_TYPE

    class ReboundFakeProvider:
        __slots__ = ("_script",)
        __init__ = original.__init__
        generate = original.generate

        def __getattribute__(self, name: str) -> object:
            if name == "generate":
                raise AssertionError("forged adapter dispatch executed")
            return object.__getattribute__(self, name)

    monkeypatch.setattr(execution_module, "FakeProvider", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_FAKE_PROVIDER_TYPE", ReboundFakeProvider)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_adapter_rebinding_when_public_checker_is_rebound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = execution_module._FAKE_PROVIDER_TYPE

    class ReboundFakeProvider:
        __slots__ = ("_script",)
        __init__ = original.__init__
        generate = original.generate

    monkeypatch.setattr(execution_module, "FakeProvider", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_FAKE_PROVIDER_TYPE", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_provider_adapter_runtime_intact", lambda: True)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_uses_captured_seals_when_all_public_tables_are_rebound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReboundFakeProvider:
        __slots__ = ()

        def __init__(self, _script: object) -> None:
            pass

        def generate(self, _request: object) -> object:
            raise AssertionError("forged adapter executed")

    monkeypatch.setattr(execution_module, "FakeProvider", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_FAKE_PROVIDER_TYPE", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_FAKE_PROVIDER_INIT", ReboundFakeProvider.__init__)
    monkeypatch.setattr(
        execution_module,
        "_FAKE_PROVIDER_GENERATE",
        ReboundFakeProvider.generate,
    )
    monkeypatch.setattr(execution_module, "_PROVIDER_EXACT_CLASS_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_CLASS_FUNCTION_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_MODULE_FUNCTION_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_MODULE_CLASS_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_GLOBAL_BINDINGS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_TRANSITIVE_GLOBAL_BINDINGS", ())
    monkeypatch.setattr(execution_module, "_provider_adapter_runtime_intact", lambda: True)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_resume_rejects_rebound_adapter_checker_before_filesystem_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accesses: list[object] = []
    original = execution_module._FAKE_PROVIDER_TYPE

    class ReboundFakeProvider:
        __slots__ = ("_script",)
        __init__ = original.__init__
        generate = original.generate

    def forbidden_open(path: object) -> int:
        accesses.append(path)
        raise AssertionError("filesystem accessed after provider checker rebinding")

    monkeypatch.setattr(execution_module, "FakeProvider", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_FAKE_PROVIDER_TYPE", ReboundFakeProvider)
    monkeypatch.setattr(execution_module, "_provider_adapter_runtime_intact", lambda: True)
    monkeypatch.setattr(execution_module, "open_directory_no_follow", forbidden_open)

    outcome = execution_module._resume_capsule(
        tmp_path / "capsule",
        provider_factory=ProviderFactory(),
    )

    assert outcome.exit_code == 2
    assert outcome.result.status == "invalid"
    assert accesses == []


def test_provider_factory_rejects_monkeypatched_adapter_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(FakeProvider, "generate", lambda *_args: None)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_mutated_adapter_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forged_generate(_self: object, _request: object) -> None:
        raise AssertionError("mutated adapter code executed")

    monkeypatch.setattr(FakeProvider.generate, "__code__", forged_generate.__code__)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_added_adapter_dispatch_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        FakeProvider,
        "__getattribute__",
        lambda _self, _name: (_ for _ in ()).throw(
            AssertionError("forged adapter dispatch executed")
        ),
        raising=False,
    )

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_mutated_replay_loader_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = execution_module._replay_provider_module.safe_load_unique_bytes

    def forged_loader(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutated replay loader executed")

    monkeypatch.setattr(loader, "__code__", forged_loader.__code__)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_mutated_openai_request_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forged_validator(_self: object, _request: object) -> None:
        raise AssertionError("mutated request validator executed")

    monkeypatch.setattr(
        OpenAIProvider._validate_request,
        "__code__",
        forged_validator.__code__,
    )

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_resume_rejects_mutated_factory_code_before_filesystem_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accesses: list[object] = []

    def forged_create(_self: object, _request: object) -> None:
        raise AssertionError("mutated provider factory executed")

    def forbidden_open(path: object) -> int:
        accesses.append(path)
        raise AssertionError("filesystem accessed after provider code mutation")

    monkeypatch.setattr(
        execution_module._UNGUARDED_PROVIDER_FACTORY_CREATE,
        "__code__",
        forged_create.__code__,
    )
    monkeypatch.setattr(execution_module, "open_directory_no_follow", forbidden_open)

    outcome = execution_module._resume_capsule(
        tmp_path / "capsule",
        provider_factory=ProviderFactory(),
    )

    assert outcome.exit_code == 2
    assert outcome.result.status == "invalid"
    assert accesses == []


def test_provider_factory_constructs_exact_fake_adapter_without_environment_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForbiddenEnvironment(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError(f"environment was read: {key}")

        def __iter__(self) -> Iterator[str]:
            raise AssertionError("environment was iterated")

        def __len__(self) -> int:
            raise AssertionError("environment size was read")

        def get(self, key: str, default: str | None = None) -> str | None:
            del default
            return self[key]

    monkeypatch.setattr(execution_module, "os", _ExecutionOsProxy(ForbiddenEnvironment()))

    binding = ProviderFactory().create(_factory_request())

    assert type(binding) is ProviderBinding
    assert binding.provider_kind == "fake"
    assert binding.adapter_source_sha256 == _DIGEST
    assert type(binding.provider) is FakeProvider
    assert binding.credential_values == ()


def test_provider_factory_constructs_replay_only_from_captured_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = (
        b"case:if:0:\n  output_text: Captured result.\n  response_model: replay-returned-v1\n"
    )

    def forbidden_path_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("replay factory reopened a pathname")

    monkeypatch.setattr(Path, "read_text", forbidden_path_read)
    monkeypatch.setattr(Path, "read_bytes", forbidden_path_read)

    binding = ProviderFactory().create(
        _factory_request(
            provider_kind="replay",
            captured_replay_bytes=document,
        )
    )
    request = GenerationRequest(
        case_id="case",
        arm="if",
        repetition=0,
        model="fixture-v1",
        instructions="captured instruction",
        prompt="captured prompt",
        max_output_tokens=128,
        temperature=None,
        timeout_seconds=5.0,
    )

    assert type(binding.provider) is ReplayProvider
    assert binding.provider.generate(request).output_text == "Captured result."
    assert binding.credential_values == ()


class _EnvironmentSpy(Mapping[str, str]):
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("provider factory iterated ambient environment")

    def __len__(self) -> int:
        raise AssertionError("provider factory inspected ambient environment size")

    def get(self, key: str, default: str | None = None) -> str | None:
        self.lookups.append(key)
        return self._values.get(key, default)


def test_openai_factory_reads_only_authored_key_and_custom_header_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _EnvironmentSpy({})
    monkeypatch.setattr(execution_module, "os", _ExecutionOsProxy(environment))

    with pytest.raises(CredentialUnavailable) as caught:
        ProviderFactory().create(
            _factory_request(provider_kind="openai", api_key_env="AUTHORED_API_KEY")
        )

    assert environment.lookups == ["AUTHORED_API_KEY"]
    assert str(caught.value) == str(CredentialUnavailable())
    assert "AUTHORED_API_KEY" not in str(caught.value)


def test_openai_factory_rejects_rebound_sdk_export_before_credential_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = importlib.import_module("openai")
    environment = _EnvironmentSpy({"AUTHORED_API_KEY": _SECRET})
    monkeypatch.setattr(execution_module, "os", _ExecutionOsProxy(environment))
    monkeypatch.setattr(sdk, "OpenAI", lambda **_kwargs: object())

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(
            _factory_request(provider_kind="openai", api_key_env="AUTHORED_API_KEY")
        )

    assert environment.lookups == []


def test_openai_custom_headers_fail_closed_without_disclosing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _EnvironmentSpy(
        {
            "AUTHORED_API_KEY": _SECRET,
            "OPENAI_CUSTOM_HEADERS": f"X-Canary: {_SECRET}",
        }
    )
    monkeypatch.setattr(execution_module, "os", _ExecutionOsProxy(environment))

    with pytest.raises(ProviderUnavailable) as caught:
        ProviderFactory().create(
            _factory_request(provider_kind="openai", api_key_env="AUTHORED_API_KEY")
        )

    assert _SECRET not in str(caught.value)
    assert _SECRET not in repr(caught.value)


def test_resume_exceptions_have_constant_content_free_messages() -> None:
    errors = (
        CredentialUnavailable(),
        ProviderUnavailable(),
        ResumeError("invalid_provider_factory"),
    )

    for error in errors:
        rendered = f"{error!s}\n{error!r}"
        assert _SECRET not in rendered
        assert _REPLAY_CANARY.decode() not in rendered
        assert len(str(error).encode("utf-8")) <= 128


@pytest.mark.parametrize(
    (
        "result",
        "credentials",
        "expected_output",
        "expected_redactions",
        "expected_usage",
    ),
    [
        pytest.param(
            GenerationResult(output_text="plain success", response_model="returned-plain-v1"),
            (),
            "plain success",
            0,
            {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cached_input_tokens": None,
                "availability": "unavailable",
                "source": "provider",
                "cache_accounting": "not_reported",
            },
            id="unmetered-success",
        ),
        pytest.param(
            GenerationResult(
                output_text=f"before {_SECRET} after",
                response_model="returned-redacted-v1",
            ),
            (_SECRET,),
            "before [REDACTED] after",
            1,
            {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cached_input_tokens": None,
                "availability": "unavailable",
                "source": "provider",
                "cache_accounting": "not_reported",
            },
            id="credential-redaction",
        ),
        pytest.param(
            GenerationResult(
                output_text="metered success",
                response_model="returned-metered-v2",
                request_id="request-metered",
                finish_reason="stop",
                usage=TokenUsage(
                    input_tokens=7,
                    output_tokens=3,
                    total_tokens=10,
                    cached_input_tokens=2,
                ),
            ),
            (),
            "metered success",
            0,
            {
                "input_tokens": 7,
                "output_tokens": 3,
                "total_tokens": 10,
                "cached_input_tokens": 2,
                "availability": "complete",
                "source": "provider",
                "cache_accounting": "reported",
            },
            id="metered-success",
        ),
    ],
)
def test_resume_success_integration_preserves_sanitized_output_and_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: GenerationResult,
    credentials: tuple[str, ...],
    expected_output: str,
    expected_redactions: int,
    expected_usage: dict[str, object],
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider([result, result])
    factory_calls: list[ProviderFactoryRequest] = []

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(
            provider,
            credential_values=credentials,
            factory_calls=factory_calls,
        ),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 0
    assert outcome.code == "complete"
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(factory_calls) == 1
    assert len(provider.calls) == 2
    assert [event["kind"] for event in events] == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "generation_completed",
    ]
    assert len(raw) == 2
    assert all(row["terminal"] is True for row in raw)
    assert all(row["terminal_reason"] == "success" for row in raw)
    assert all(row["output_text"] == expected_output for row in raw)
    assert all(row["output_was_redacted"] is (expected_redactions > 0) for row in raw)
    assert all(row["output_redaction_count"] == expected_redactions for row in raw)
    assert all(row["response_model"] == result.response_model for row in raw)
    assert all(row["usage"] == expected_usage for row in raw)
    assert _SECRET.encode() not in (capsule / "raw.jsonl").read_bytes()


def test_resume_response_too_large_commits_only_discarded_output_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    output = "x" * (RESOURCE_LIMITS_V1.output_utf8_bytes + 1)
    result = GenerationResult(output_text=output, response_model="returned-large-v1")
    provider = _ScriptedProvider([result, result])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.calls) == 2
    assert [event["kind"] for event in events][-1] == "generation_completed"
    assert len(raw) == 2
    assert all(row["terminal_reason"] == "provider_rejected" for row in raw)
    assert all(row["error"]["kind"] == "response_too_large" for row in raw)
    assert all(row["output_text"] is None for row in raw)
    assert all(row["output_sha256"] is None for row in raw)
    assert all(row["discarded_output_byte_length"] == len(output.encode("utf-8")) for row in raw)
    expected_sha256 = hashlib.sha256(output.encode("utf-8")).hexdigest()
    assert all(row["discarded_output_sha256"] == expected_sha256 for row in raw)
    assert output.encode("utf-8") not in (capsule / "raw.jsonl").read_bytes()


@pytest.mark.parametrize(
    (
        "provider_error",
        "expected_exit",
        "expected_state",
        "expected_terminal_reason",
        "expected_marker",
        "expected_calls",
    ),
    [
        pytest.param(
            ProviderError(
                "invalid_request",
                f"rejected {_SECRET}",
                False,
                delivery_certainty="definitely_rejected",
                response_model="returned-rejected-v1",
            ),
            0,
            "GENERATION_COMPLETE",
            "provider_rejected",
            None,
            2,
            id="nonretryable-rejection",
        ),
        pytest.param(
            ProviderError(
                "authentication",
                f"authentication failed {_SECRET}",
                False,
                delivery_certainty="definitely_rejected",
                response_model="returned-auth-v1",
            ),
            1,
            "AUTHENTICATION_STOPPED",
            "authentication_stopped",
            "authentication_stopped",
            1,
            id="authentication",
        ),
        pytest.param(
            ProviderError(
                "timeout",
                f"delivery unknown {_SECRET}",
                True,
                delivery_certainty="unknown",
                response_model="returned-unknown-v1",
            ),
            1,
            "AMBIGUOUS_INFLIGHT",
            "ambiguous_delivery",
            "delivery_ambiguous",
            1,
            id="unknown-delivery",
        ),
    ],
)
def test_resume_provider_failure_matrix_has_exact_terminal_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: ProviderError,
    expected_exit: int,
    expected_state: str,
    expected_terminal_reason: str,
    expected_marker: str | None,
    expected_calls: int,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider([provider_error, provider_error])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=(_SECRET,)),
    )

    events, raw = _journal_rows(capsule)
    event_kinds = [event["kind"] for event in events]
    assert outcome.exit_code == expected_exit
    assert outcome.result.state == expected_state
    assert len(provider.calls) == expected_calls
    assert len(raw) == expected_calls
    assert all(row["terminal"] is True for row in raw)
    assert all(row["terminal_reason"] == expected_terminal_reason for row in raw)
    assert all(row["error"]["kind"] == provider_error.kind for row in raw)
    expected_message = provider_error.message.replace(_SECRET, "[REDACTED]")
    assert all(row["error"]["message"] == expected_message for row in raw)
    expected_prefix = [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
    ]
    if expected_marker is None:
        assert event_kinds == [
            *expected_prefix,
            "request_started",
            "request_finished",
            "generation_completed",
        ]
    else:
        assert event_kinds == [*expected_prefix, expected_marker]
    assert _SECRET.encode() not in (capsule / "raw.jsonl").read_bytes()


@pytest.mark.parametrize(
    ("factory_error", "reason"),
    [
        pytest.param(CredentialUnavailable(), "credential_unavailable", id="credential"),
        pytest.param(ProviderUnavailable(), "provider_unavailable", id="provider"),
    ],
)
def test_resume_factory_unavailable_blocks_before_any_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory_error: Exception,
    reason: str,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider([])
    factory_calls: list[ProviderFactoryRequest] = []

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(
            provider,
            factory_calls=factory_calls,
            factory_error=factory_error,
        ),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "PREPARED"
    assert len(factory_calls) == 1
    assert provider.calls == []
    assert raw == []
    assert [event["kind"] for event in events] == [
        "prepared",
        "execution_started",
        "execution_blocked",
    ]
    assert events[-1]["payload"] == {"reason": reason}


def test_resume_treats_opaque_ordinary_exception_as_constant_unknown_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)

    class OpaqueProviderFailure(Exception):
        def __str__(self) -> str:
            raise AssertionError("ordinary provider exception was stringified")

        def __repr__(self) -> str:
            raise AssertionError("ordinary provider exception was represented")

    provider = _ScriptedProvider([OpaqueProviderFailure()])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=(_SECRET,)),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.calls) == 1
    assert [event["kind"] for event in events] == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "delivery_ambiguous",
    ]
    assert len(raw) == 1
    assert raw[0]["delivery_certainty"] == "unknown"
    assert raw[0]["terminal_reason"] == "ambiguous_delivery"
    assert raw[0]["error"] == {
        "kind": "malformed_response",
        "message": "malformed_response",
        "request_id": None,
        "retryable": False,
    }
    assert _SECRET.encode() not in (capsule / "raw.jsonl").read_bytes()


def test_operation_sanitizer_patterns_bind_only_current_local_roots_and_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    descriptor = os.open(capsule, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    monkeypatch.setattr(
        execution_module,
        "_descriptor_resolved_path",
        lambda _descriptor: "/resolved/current-capsule",
    )
    monkeypatch.setattr(execution_module.socket, "gethostname", lambda: "Build.Example.")
    monkeypatch.setattr(execution_module.socket, "getfqdn", lambda: "Build.FQDN.Example.")
    monkeypatch.setattr(
        execution_module.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir="/synthetic/home", pw_name="Builder"),
    )
    monkeypatch.setattr(execution_module.os, "getcwd", lambda: "/synthetic/cwd")
    try:
        patterns = execution_module._sanitizer_patterns(capsule, descriptor, (_SECRET,))
    finally:
        os.close(descriptor)

    assert patterns.credential_values == (_SECRET,)
    assert patterns.capsule_roots == (str(capsule), "/resolved/current-capsule")
    assert patterns.source_roots == ()
    assert patterns.input_roots == ()
    assert patterns.cwd_roots == ("/synthetic/cwd",)
    assert patterns.home_roots == ("/synthetic/home",)
    assert patterns.local_hostnames == ("Build.Example", "Build")
    assert patterns.local_fqdns == ("Build.FQDN.Example",)
    assert patterns.local_usernames == ("Builder",)


def test_resume_unsafe_provider_metadata_is_constant_and_never_leaks_canary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    result = GenerationResult(
        output_text="safe output",
        response_model=f"returned-{_SECRET}",
        request_id="safe-request",
        finish_reason="stop",
    )
    provider = _ScriptedProvider([result, result])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=(_SECRET,)),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(raw) == 2
    assert all(row["terminal_reason"] == "provider_rejected" for row in raw)
    assert all(row["response_model"] is None for row in raw)
    assert all(row["error"]["kind"] == "unsafe_provider_metadata" for row in raw)
    assert _SECRET.encode() not in (capsule / "raw.jsonl").read_bytes()


@pytest.mark.parametrize(
    (
        "failed_checkpoint",
        "expected_state",
        "expected_factory_calls",
        "expected_provider_calls",
    ),
    [
        pytest.param(1, "INTERRUPTED", 0, 0, id="pre-factory"),
        pytest.param(2, "INTERRUPTED", 1, 0, id="post-construction"),
        pytest.param(3, "INTERRUPTED", 1, 0, id="pre-attempt"),
        pytest.param(4, "AMBIGUOUS_INFLIGHT", 1, 0, id="pre-call"),
        pytest.param(5, "AMBIGUOUS_INFLIGHT", 1, 1, id="post-return"),
        pytest.param(6, "AMBIGUOUS_INFLIGHT", 1, 1, id="post-normalization"),
    ],
)
def test_resume_runtime_drift_at_every_checkpoint_has_exact_call_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_checkpoint: int,
    expected_state: str,
    expected_factory_calls: int,
    expected_provider_calls: int,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    provider = _ScriptedProvider(
        [GenerationResult(output_text="done", response_model="returned-v1")]
    )
    factory_calls: list[ProviderFactoryRequest] = []
    checkpoints = 0

    def fail_selected_checkpoint(*_args: object, **_kwargs: object) -> None:
        nonlocal checkpoints
        checkpoints += 1
        if checkpoints == failed_checkpoint:
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_capture_runtime_authority",
        _matching_runtime_authority,
    )
    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        fail_selected_checkpoint,
    )
    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, factory_calls=factory_calls),
    )

    events, raw = _journal_rows(capsule)
    event_kinds = [event["kind"] for event in events]
    assert outcome.exit_code == 1
    assert outcome.result.state == expected_state
    assert len(factory_calls) == expected_factory_calls
    assert len(provider.calls) == expected_provider_calls
    assert raw == []
    if expected_state == "INTERRUPTED":
        assert event_kinds == [
            "prepared",
            "execution_started",
            "execution_interrupted",
        ]
    else:
        assert event_kinds == ["prepared", "execution_started", "request_started"]


def test_resume_safe_retry_sleeps_once_preserves_mixed_models_and_never_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch, max_transient_retries=1)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider(
        [
            ProviderError(
                "transient",
                f"retry safely {_SECRET}",
                True,
                delivery_certainty="definitely_not_sent",
                response_model="returned-retry-v1",
                request_id="request-retry",
                usage=TokenUsage(3, 0, 3),
            ),
            GenerationResult(
                output_text="retry succeeded",
                response_model="returned-success-v2",
                request_id="request-success",
                usage=TokenUsage(3, 2, 5, cached_input_tokens=1),
            ),
            ProviderError(
                "transient",
                f"retry safely {_SECRET}",
                True,
                delivery_certainty="definitely_not_sent",
                response_model="returned-retry-v1",
                request_id="request-retry",
                usage=TokenUsage(3, 0, 3),
            ),
            GenerationResult(
                output_text="retry succeeded",
                response_model="returned-success-v2",
                request_id="request-success",
                usage=TokenUsage(3, 2, 5, cached_input_tokens=1),
            ),
        ]
    )
    sleeps: list[float] = []
    factory_calls: list[ProviderFactoryRequest] = []
    seams = _seams_for_provider(
        provider,
        credential_values=(_SECRET,),
        sleeps=sleeps,
        factory_calls=factory_calls,
    )

    first = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=seams,
    )
    before_second = (
        (capsule / "events.jsonl").read_bytes(),
        (capsule / "raw.jsonl").read_bytes(),
    )
    second = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=seams,
    )

    events, raw = _journal_rows(capsule)
    assert first.exit_code == second.exit_code == 0
    assert first.result.state == second.result.state == "GENERATION_COMPLETE"
    assert len(factory_calls) == 1
    assert len(provider.calls) == 4
    assert provider.outcomes == []
    assert sleeps == [0.1, 0.1]
    assert [row["attempt"] for row in raw] == [1, 2, 1, 2]
    assert [row["retry_of_attempt"] for row in raw] == [None, 1, None, 1]
    assert [row["terminal"] for row in raw] == [False, True, False, True]
    assert [row["terminal_reason"] for row in raw] == [None, "success", None, "success"]
    assert [row["backoff_ms"] for row in raw] == [100, None, 100, None]
    assert [row["response_model"] for row in raw] == [
        "returned-retry-v1",
        "returned-success-v2",
        "returned-retry-v1",
        "returned-success-v2",
    ]
    assert [row["usage"]["total_tokens"] for row in raw] == [3, 5, 3, 5]
    assert [event["kind"] for event in events] == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "generation_completed",
    ]
    assert before_second == (
        (capsule / "events.jsonl").read_bytes(),
        (capsule / "raw.jsonl").read_bytes(),
    )
    assert _SECRET.encode() not in before_second[1]


def test_resume_safe_retry_exhaustion_commits_exponential_backoff_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch, max_transient_retries=2)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider(
        [
            ProviderError(
                "transient",
                f"retry {attempt} {_SECRET}",
                True,
                delivery_certainty=(
                    "definitely_not_sent" if attempt % 2 else "definitely_rejected"
                ),
                response_model=f"returned-retry-v{attempt}",
            )
            for _plan_ordinal in range(2)
            for attempt in (1, 2, 3)
        ]
    )
    sleeps: list[float] = []

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(
            provider,
            credential_values=(_SECRET,),
            sleeps=sleeps,
        ),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.calls) == 6
    assert sleeps == [0.1, 0.2, 0.1, 0.2]
    assert [row["attempt"] for row in raw] == [1, 2, 3, 1, 2, 3]
    assert [row["retry_of_attempt"] for row in raw] == [None, 1, 2, None, 1, 2]
    assert [row["terminal"] for row in raw] == [False, False, True] * 2
    assert [row["terminal_reason"] for row in raw] == [
        None,
        None,
        "retry_exhausted",
    ] * 2
    assert [row["backoff_ms"] for row in raw] == [100, 200, None] * 2
    assert [row["response_model"] for row in raw] == [
        "returned-retry-v1",
        "returned-retry-v2",
        "returned-retry-v3",
    ] * 2
    assert [event["kind"] for event in events].count("request_started") == 6
    assert [event["kind"] for event in events].count("request_finished") == 6
    assert events[-1]["kind"] == "generation_completed"


@pytest.mark.parametrize(
    ("reason", "factory_count"),
    [
        pytest.param("signal", 1, id="signal"),
        pytest.param("operator", 1, id="operator"),
        pytest.param("internal_error", 0, id="internal-error"),
    ],
)
def test_resume_interruption_taxonomy_is_request_free_and_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    factory_count: int,
) -> None:
    capsule = _single_plan_capsule(tmp_path, monkeypatch)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider([])
    factory_calls: list[ProviderFactoryRequest] = []

    def stop(_row: object) -> str | None:
        return reason if reason in {"signal", "operator"} else None

    def guard(_policy: object) -> None:
        if reason == "internal_error":
            raise ResumeError("checkpoint_failed")

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(
            provider,
            stop_before_attempt=stop,
            install_guard=guard,
            factory_calls=factory_calls,
        ),
    )

    events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "INTERRUPTED"
    assert len(factory_calls) == factory_count
    assert provider.calls == []
    assert raw == []
    assert [event["kind"] for event in events] == [
        "prepared",
        "execution_started",
        "execution_interrupted",
    ]
    assert events[-1]["payload"]["reason"] == reason
    first_plan_row = json.loads((capsule / "plan.jsonl").read_bytes().splitlines()[0])
    assert events[-1]["payload"]["next_plan_item_id"] == first_plan_row["plan_item_id"]
