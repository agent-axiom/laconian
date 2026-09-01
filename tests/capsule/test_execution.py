from __future__ import annotations

import builtins
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
from pydantic import BaseModel

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
from laconian_eval.providers.base import (
    PublicBenchmarkRequestPolicyV1,
    PublicBenchmarkRequestV1,
)
from laconian_eval.providers.openai import OpenAIProvider

from . import test_prepare as test_prepare_module
from .test_prepare import _install_harness, _manifest_payload, _request

_DIGEST = "a" * 64
_SECRET = "credential-CANARY-do-not-disclose"
_REPLAY_CANARY = b"replay-CANARY-do-not-disclose"
_PUBLIC_BENCHMARK_REPLAY_FIXTURE = (
    Path(__file__).parents[1] / "fixtures/replay-public-benchmark-responses.yaml"
)


def _benchmark_request(
    *,
    case_id: str = "case-en",
    arm: str = "if",
) -> PublicBenchmarkRequestV1:
    return PublicBenchmarkRequestV1(
        case_id=case_id,
        arm=arm,
        repetition=0,
        requested_model_id="gpt-5.6-sol",
        instructions="Synthetic instructions.",
        prompt="Synthetic prompt.",
        max_output_tokens=128,
        temperature=None,
        timeout_seconds=5.0,
        reasoning_effort="medium",
        text_verbosity="medium",
        policy=PublicBenchmarkRequestPolicyV1(
            schema_version="PublicBenchmarkRequestPolicyV1",
            reasoning_mode="omitted",
            prompt_cache_mode="explicit",
            prompt_cache_ttl="30m",
            service_tier="default",
            input_token_bound_version="openai-utf8-envelope-v1",
            max_input_tokens=272000,
        ),
    )


def _factory_request(
    *,
    provider_kind: str = "fake",
    requested_model: str = "fixture-v1",
    api_key_env: str | None = None,
    captured_replay_bytes: bytes | None = None,
) -> ProviderFactoryRequest:
    return ProviderFactoryRequest(
        provider_kind=provider_kind,
        requested_model=requested_model,
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
    provider_kind: str = "fake",
    provider_model: str = "fixture-v1",
    api_key_env: str | None = None,
    benchmark_generation: bool = False,
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
    payload = _manifest_payload(
        arms=["baseline"],
        provider_kind=provider_kind,
        api_key_env=api_key_env,
    )
    provider_payload = payload["provider"]
    assert isinstance(provider_payload, dict)
    provider_payload["model"] = provider_model
    if benchmark_generation:
        payload["generation"] = {
            "max_output_tokens": 128,
            "temperature": None,
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        }
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
    if provider_model != "fixture-v1":
        original_environment = test_prepare_module._environment

        def matching_environment(*args: object, **kwargs: object) -> object:
            environment = original_environment(*args, **kwargs)  # type: ignore[arg-type]
            environment_payload = environment.model_dump(mode="python")
            provider_environment = environment_payload["provider"]
            assert isinstance(provider_environment, dict)
            provider_environment["requested_model"] = provider_model
            return type(environment).model_validate(environment_payload)

        monkeypatch.setattr(test_prepare_module, "_environment", matching_environment)
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


class _BenchmarkProbeProvider:
    def __init__(self) -> None:
        self.benchmark_calls: list[object] = []
        self.legacy_calls: list[object] = []

    def generate_benchmark(self, request: object) -> object:
        self.benchmark_calls.append(request)
        raise RuntimeError("stop after captured benchmark request")

    def generate(self, request: object) -> GenerationResult:
        self.legacy_calls.append(request)
        raise RuntimeError("legacy provider path must not serve a public benchmark request")


class _BenchmarkScriptedProvider:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.benchmark_calls: list[PublicBenchmarkRequestV1] = []
        self.legacy_calls: list[object] = []

    def generate_benchmark(self, request: PublicBenchmarkRequestV1) -> object:
        self.benchmark_calls.append(request)
        if not self.outcomes:
            raise AssertionError("benchmark provider was called after its final outcome")
        return self.outcomes.pop(0)

    def generate(self, request: object) -> GenerationResult:
        self.legacy_calls.append(request)
        raise AssertionError("legacy path served a public benchmark request")


class _BenchmarkAuthorityMutatingProvider:
    def __init__(self, outcome: object, mutate: Callable[[], None]) -> None:
        self.outcome = outcome
        self.mutate = mutate
        self.benchmark_calls: list[PublicBenchmarkRequestV1] = []

    def generate_benchmark(self, request: PublicBenchmarkRequestV1) -> object:
        self.benchmark_calls.append(request)
        self.mutate()
        return self.outcome


def _seams_for_provider(
    provider: (
        _ScriptedProvider
        | _BenchmarkProbeProvider
        | _BenchmarkScriptedProvider
        | _BenchmarkAuthorityMutatingProvider
    ),
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


def _benchmark_replay_outcome(*, returned_service_tier: str) -> object:
    fixture = _PUBLIC_BENCHMARK_REPLAY_FIXTURE.read_bytes()
    if returned_service_tier != "default":
        fixture = fixture.replace(
            b"service_tier: default",
            f"service_tier: {returned_service_tier}".encode(),
        )
    provider = ReplayProvider.from_benchmark_bytes(fixture)
    return provider.generate_benchmark(_benchmark_request())


def _benchmark_replay_response_with_output(output_text: str) -> object:
    response_type = execution_module._attempts_module.PublicBenchmarkResponseEvidenceV1
    source_type = execution_module._attempts_module.PublicBenchmarkRawResponseSourceV1
    response = _benchmark_replay_outcome(returned_service_tier="default")
    assert type(response) is response_type
    source_payload = response.raw_response_source.model_dump(mode="python")
    source_entries = list(source_payload["entries"])
    output_ordinal = next(
        ordinal
        for ordinal, entry in enumerate(source_entries)
        if entry["path"] == "response.output"
    )
    source_entries[output_ordinal] = source_entries[output_ordinal] | {
        "value": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": output_text}],
            }
        ]
    }
    source = source_type.model_validate(source_payload | {"entries": source_entries})
    digest = execution_module._attempts_module.public_benchmark_raw_response_sha256(source)
    payload = response_type.model_dump(response, mode="python", round_trip=True)
    payload.update(
        {
            "output_text": output_text,
            "raw_response_source": source,
            "raw_response_sha256": digest,
        }
    )
    for field in (
        "returned_model_source_sha256",
        "service_tier_source_sha256",
        "applied_cache_control_source_sha256",
        "cache_read_source_sha256",
        "cache_write_source_sha256",
        "usage_source_sha256",
        "reasoning_tokens_source_sha256",
    ):
        payload[field] = digest
    return response_type.model_validate(payload)


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
    monkeypatch.setattr(execution_module, "_PROVIDER_EVIDENCE_BUILTIN_BINDINGS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_EVIDENCE_MODULE_NAMESPACE_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_TRANSITIVE_ATTRIBUTE_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_INHERITED_DESCRIPTOR_SEALS", ())
    monkeypatch.setattr(execution_module, "_PROVIDER_RUNTIME_HELPER_ROOTS", ())
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


@pytest.mark.parametrize(
    "target",
    (
        ReplayProvider._validate_benchmark_request,
        ReplayProvider.generate_benchmark,
        OpenAIProvider._validate_benchmark_request,
        OpenAIProvider.generate_benchmark,
    ),
    ids=(
        "replay-validator",
        "replay-dispatch",
        "openai-validator",
        "openai-dispatch",
    ),
)
def test_provider_factory_rejects_mutated_benchmark_adapter_code(
    monkeypatch: pytest.MonkeyPatch,
    target: Callable[..., object],
) -> None:
    def forged_benchmark_method(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutated benchmark adapter executed")

    monkeypatch.setattr(target, "__code__", forged_benchmark_method.__code__)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


@pytest.mark.parametrize(
    ("owner", "name", "replacement"),
    (
        (
            execution_module._openai_provider_module,
            "_canonical_json_v1",
            lambda _value: b"{}",
        ),
        (
            execution_module._openai_provider_module.hashlib,
            "sha256",
            lambda _value=b"": object(),
        ),
        (
            execution_module._openai_provider_module.unicodedata,
            "normalize",
            lambda _form, value: value,
        ),
        (
            execution_module._replay_provider_module,
            "_BENCHMARK_MODEL_IDS",
            frozenset(),
        ),
        (
            execution_module._attempts_module,
            "PublicBenchmarkResponseEvidenceV1",
            object,
        ),
        (
            execution_module,
            "normalize_public_benchmark_outcome",
            lambda *_args, **_kwargs: object(),
        ),
        (
            execution_module._attempts_module,
            "sanitize_output",
            lambda *_args, **_kwargs: object(),
        ),
    ),
    ids=(
        "canonicalizer",
        "sha256",
        "unicode-normalizer",
        "replay-models",
        "evidence-type",
        "execution-normalizer",
        "attempts-sanitizer",
    ),
)
def test_provider_factory_rejects_rebound_benchmark_global_authority(
    monkeypatch: pytest.MonkeyPatch,
    owner: object,
    name: str,
    replacement: object,
) -> None:
    monkeypatch.setattr(owner, name, replacement)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


def test_provider_factory_rejects_mutated_benchmark_digest_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = execution_module._attempts_module.public_benchmark_raw_response_sha256

    def forged_digest(_source: object) -> str:
        return "0" * 64

    monkeypatch.setattr(digest, "__code__", forged_digest.__code__)

    with pytest.raises(ProviderUnavailable):
        ProviderFactory().create(_factory_request())


@pytest.mark.parametrize(
    "authority",
    ("model_validate", "model_dump", "__pydantic_validator__"),
)
def test_provider_runtime_checks_reject_direct_benchmark_model_namespace_mutation(
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    model_type = execution_module._attempts_module.PublicBenchmarkResponseEvidenceV1
    forged_calls: list[object] = []

    if authority == "__pydantic_validator__":
        replacement = object()
    else:

        def replacement(*args: object, **kwargs: object) -> object:
            forged_calls.append((args, kwargs))
            return {}

    monkeypatch.setattr(model_type, authority, replacement, raising=False)

    assert vars(model_type)[authority] is replacement
    assert execution_module._provider_adapter_runtime_intact() is False
    assert runtime_integrity_check() is False
    assert forged_calls == []


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


def test_provider_factory_selects_strict_benchmark_replay_from_captured_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _PUBLIC_BENCHMARK_REPLAY_FIXTURE.read_bytes()

    def forbidden_path_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("benchmark replay factory reopened a pathname")

    monkeypatch.setattr(Path, "read_text", forbidden_path_read)
    monkeypatch.setattr(Path, "read_bytes", forbidden_path_read)

    binding = ProviderFactory().create(
        _factory_request(
            provider_kind="replay",
            requested_model="gpt-5.6-sol",
            captured_replay_bytes=captured,
        )
    )
    provider = binding.provider

    assert type(provider) is ReplayProvider
    outcome = provider.generate_benchmark(_benchmark_request())
    assert outcome.output_text == "Done."  # type: ignore[union-attr]
    assert outcome.requested_service_tier == "default"
    assert outcome.returned_service_tier == "default"
    assert outcome.service_tier_status == "reported_default"
    assert binding.credential_values == ()


def test_public_benchmark_execution_reconstructs_exact_captured_policy_before_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    provider = _BenchmarkProbeProvider()

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    assert outcome.exit_code == 1, outcome.result.model_dump(mode="json")
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert provider.legacy_calls == []
    assert len(provider.benchmark_calls) == 1
    request = provider.benchmark_calls[0]
    assert type(request) is PublicBenchmarkRequestV1
    assert request.requested_model_id == "gpt-5.6-sol"
    assert request.reasoning_effort == "medium"
    assert request.text_verbosity == "medium"
    assert request.policy.reasoning_mode == "omitted"
    assert request.policy.prompt_cache_mode == "explicit"
    assert request.policy.prompt_cache_ttl == "30m"
    assert request.policy.service_tier == "default"


@pytest.mark.parametrize(
    ("returned_service_tier", "expected_status"),
    (
        ("default", "reported_default"),
        ("priority", "mismatch"),
    ),
)
def test_public_benchmark_execution_commits_tier_and_usage_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returned_service_tier: str,
    expected_status: str,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    evidence = _benchmark_replay_outcome(returned_service_tier=returned_service_tier)
    provider = _BenchmarkScriptedProvider([evidence, evidence])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.benchmark_calls) == len(raw) == 2
    assert provider.legacy_calls == []
    assert [row["attempt"] for row in raw] == [1, 1]
    assert [row["retry_of_attempt"] for row in raw] == [None, None]
    assert [row["terminal_reason"] for row in raw] == ["success", "success"]
    for row in raw:
        assert row["requested_model_id"] == "gpt-5.6-sol"
        assert row["returned_model_id"] == "gpt-5.6-sol-2026-08-07"
        assert row["requested_service_tier"] == "default"
        assert row["returned_service_tier"] == returned_service_tier
        assert row["service_tier_status"] == expected_status
        assert row["applied_prompt_cache_mode"] == "explicit"
        assert row["applied_prompt_cache_ttl"] == "30m"
        assert row["applied_cache_control_status"] == "reported_exact"
        assert row["usage"]["input_tokens"] == 10
        assert row["usage"]["cache_read_tokens"] == 0
        assert row["usage"]["cache_write_tokens"] == 0
        assert row["usage"]["ordinary_uncached_input_tokens"] == 10
        assert row["usage"]["reasoning_tokens"] == 2
        assert row["usage"]["output_tokens"] == 5
        assert row["usage"]["total_tokens"] == 15


def test_public_benchmark_post_redaction_expansion_commits_durable_discard_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    credential = "z"
    replacement = b"[REDACTED]"
    replacement_count = RESOURCE_LIMITS_V1.output_utf8_bytes // len(replacement) + 1
    source_output = credential * replacement_count
    assert len(source_output.encode()) <= RESOURCE_LIMITS_V1.output_utf8_bytes
    evidence = _benchmark_replay_response_with_output(source_output)
    provider = _BenchmarkScriptedProvider([evidence, evidence])

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=(credential,)),
    )

    _events, raw = _journal_rows(capsule)
    raw_bytes = (capsule / "raw.jsonl").read_bytes()
    expected_discarded = replacement * replacement_count
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.benchmark_calls) == len(raw) == 2
    assert source_output.encode() not in raw_bytes
    for row in raw:
        assert row["terminal_reason"] == "provider_rejected"
        assert row["error"] == {
            "kind": "response_too_large",
            "message": "response_too_large",
            "retryable": False,
            "request_id": evidence.response_id,
        }
        assert row["output_text"] is None
        assert row["output_sha256"] is None
        assert row["discarded_output_byte_length"] == len(expected_discarded)
        assert row["discarded_output_sha256"] == hashlib.sha256(expected_discarded).hexdigest()
        assert row["output_was_redacted"] is True
        assert row["output_redaction_count"] == replacement_count
        assert row["requested_model_id"] == evidence.requested_model_id
        assert row["returned_model_id"] == evidence.returned_model_id
        assert row["requested_service_tier"] == "default"
        assert row["returned_service_tier"] == evidence.returned_service_tier
        assert row["service_tier_status"] == evidence.service_tier_status
        assert row["applied_prompt_cache_mode"] == evidence.applied_prompt_cache_mode
        assert row["applied_prompt_cache_ttl"] == evidence.applied_prompt_cache_ttl
        assert row["applied_cache_control_status"] == evidence.applied_cache_control_status
        assert row["usage"] == evidence.usage.model_dump(mode="json")
        assert row["request_id"] == evidence.response_id


@pytest.mark.parametrize("authority", ("normalizer", "sanitizer"))
def test_public_benchmark_checkpoint_rejects_post_call_evidence_authority_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        if not runtime_integrity_check():
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    forged_calls: list[object] = []

    def forged(*args: object, **kwargs: object) -> object:
        forged_calls.append((args, kwargs))
        return object()

    def mutate() -> None:
        if authority == "normalizer":
            monkeypatch.setattr(
                execution_module,
                "normalize_public_benchmark_outcome",
                forged,
            )
        else:
            monkeypatch.setattr(execution_module._attempts_module, "sanitize_output", forged)

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


@pytest.mark.parametrize(
    "authority",
    (
        "heapq-heappush",
        "heapq-heappop",
        "builtins-enumerate",
        "builtins-next",
        "sanitizer-enumerate-shadow",
    ),
)
def test_public_benchmark_checkpoint_rejects_post_call_sanitizer_resolution_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    checkpoint_calls = [0]
    mutation_complete = [False]
    post_mutation_checkpoint_calls = [0]

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        checkpoint_calls[0] += 1
        if mutation_complete[0]:
            post_mutation_checkpoint_calls[0] += 1
        if not runtime_integrity_check():
            if mutation_complete[0]:
                restore_mutation()
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    forged_calls: list[object] = []
    pre_call_checkpoint_counts: list[int] = []
    checker_results: list[tuple[bool, bool]] = []
    sanitizer = execution_module._sanitizer_module

    def forged(*args: object, **kwargs: object) -> object:
        forged_calls.append((args, kwargs))
        if authority in {"heapq-heappop", "builtins-enumerate", "builtins-next"}:
            return original(*args, **kwargs)
        return ()

    if authority.startswith("heapq-"):
        name = authority.removeprefix("heapq-")
        owner = sanitizer.heapq
        original = getattr(owner, name)
    elif authority.startswith("builtins-"):
        name = authority.removeprefix("builtins-")
        owner = builtins
        original = getattr(owner, name)
    else:
        name = "enumerate"
        owner = sanitizer
        original = builtins.enumerate

    def restore_mutation() -> None:
        setattr(owner, name, original)

    def mutate() -> None:
        pre_call_checkpoint_counts.append(checkpoint_calls[0])
        monkeypatch.setattr(owner, name, forged, raising=False)
        consumer_resolution = (
            getattr(sanitizer.heapq, name)
            if authority.startswith("heapq-")
            else vars(sanitizer).get(name, vars(builtins)[name])
        )
        assert consumer_resolution is forged
        mutation_complete[0] = True
        checker_results.append(
            (
                execution_module._provider_adapter_runtime_intact(),
                runtime_integrity_check(),
            )
        )
        assert forged_calls == []

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=("Done.",)),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1, (
        pre_call_checkpoint_counts,
        post_mutation_checkpoint_calls,
        checker_results,
        forged_calls,
        len(provider.benchmark_calls),
        raw,
        outcome,
    )
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert pre_call_checkpoint_counts and pre_call_checkpoint_counts[0] > 0
    assert post_mutation_checkpoint_calls[0] == 1
    assert checker_results == [(False, False)]
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


def test_public_benchmark_checkpoint_rejects_post_call_private_checker_closure_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    checker_closure = runtime_integrity_check.__closure__
    assert checker_closure is not None
    checker_freevars = runtime_integrity_check.__code__.co_freevars
    assert len(checker_closure) == len(checker_freevars)
    named_cells = dict(zip(checker_freevars, checker_closure, strict=True))
    assert "runtime_closure_state" in named_cells
    closure_state = named_cells["runtime_closure_state"].cell_contents
    assert type(closure_state) is list
    assert len(closure_state) == 1
    sealed_function, sealed_cells = closure_state[0]
    assert sealed_function is runtime_integrity_check
    assert type(sealed_cells) is tuple
    sealed_names: list[str] = []
    for sealed_name, expected_value, expected_type in sealed_cells:
        sealed_names.append(sealed_name)
        assert sealed_name in named_cells
        actual_value = named_cells[sealed_name].cell_contents
        assert actual_value is expected_value
        assert type(actual_value) is expected_type
    assert sealed_names == [name for name in checker_freevars if name != "runtime_closure_state"]
    assert "all_of" in named_cells
    all_of_cell = named_cells["all_of"]
    original_all_of = all_of_cell.cell_contents
    assert original_all_of is builtins.all

    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    sanitizer = execution_module._sanitizer_module
    original_heappush = sanitizer.heapq.heappush
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    mutation_complete = [False]
    checker_results: list[tuple[bool, bool]] = []
    forged_calls: list[object] = []

    def forged_heappush(*args: object, **kwargs: object) -> None:
        forged_calls.append((args, kwargs))
        restore_mutation()
        original_heappush(*args, **kwargs)

    def restore_mutation() -> None:
        all_of_cell.cell_contents = original_all_of
        sanitizer.heapq.heappush = original_heappush

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        if not runtime_integrity_check():
            if mutation_complete[0]:
                restore_mutation()
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )

    def mutate() -> None:
        all_of_cell.cell_contents = builtins.any
        monkeypatch.setattr(sanitizer.heapq, "heappush", forged_heappush)
        mutation_complete[0] = True
        checker_results.append(
            (
                execution_module._provider_adapter_runtime_intact(),
                runtime_integrity_check(),
            )
        )
        assert forged_calls == []

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)
    try:
        outcome = execution_module._resume_capsule(
            capsule,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider, credential_values=("Done.",)),
        )
    finally:
        restore_mutation()

    _events, raw = _journal_rows(capsule)
    assert checker_results == [(False, False)]
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


def test_public_benchmark_checkpoint_rejects_resealed_private_checker_closure_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    checker_closure = runtime_integrity_check.__closure__
    assert checker_closure is not None
    checker_freevars = runtime_integrity_check.__code__.co_freevars
    named_cells = dict(zip(checker_freevars, checker_closure, strict=True))
    closure_state = named_cells["runtime_closure_state"].cell_contents
    assert type(closure_state) is list
    assert len(closure_state) == 1
    original_closure_state = closure_state[0]
    all_of_cell = named_cells["all_of"]
    original_all_of = all_of_cell.cell_contents
    assert original_all_of is builtins.all

    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    attempts_module = execution_module._attempts_module
    original_sanitize_output = attempts_module.sanitize_output
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    checker_results: list[tuple[bool, bool]] = []
    forged_calls: list[object] = []

    def restore_mutation() -> None:
        all_of_cell.cell_contents = original_all_of
        attempts_module.sanitize_output = original_sanitize_output
        closure_state[0] = original_closure_state

    def forged_sanitize_output(*args: object, **kwargs: object) -> object:
        forged_calls.append((args, kwargs))
        restore_mutation()
        return original_sanitize_output(*args, **kwargs)

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        if not runtime_integrity_check():
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )

    def mutate() -> None:
        all_of_cell.cell_contents = builtins.any
        monkeypatch.setattr(attempts_module, "sanitize_output", forged_sanitize_output)
        closure_state[0] = (
            runtime_integrity_check,
            tuple(
                (name, cell.cell_contents, type(cell.cell_contents))
                for name, cell in zip(checker_freevars, checker_closure, strict=True)
                if name != "runtime_closure_state"
            ),
        )
        checker_results.append(
            (
                execution_module._provider_adapter_runtime_intact(),
                runtime_integrity_check(),
            )
        )

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)
    try:
        outcome = execution_module._resume_capsule(
            capsule,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider),
        )
    finally:
        restore_mutation()

    _events, raw = _journal_rows(capsule)
    assert checker_results == [(False, True)]
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


@pytest.mark.parametrize(
    "dispatch_name",
    (
        "_complete_execution_checkpoint",
        "_runtime_checkpoint",
        "_revalidate_mutator_session_v1",
    ),
)
def test_public_benchmark_checkpoint_rejects_post_call_dispatch_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dispatch_name: str,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    replacement_calls: list[object] = []

    def replacement(*args: object, **kwargs: object) -> None:
        replacement_calls.append((args, kwargs))

    def mutate() -> None:
        monkeypatch.setattr(execution_module, dispatch_name, replacement)

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert replacement_calls == []
    assert raw == []


@pytest.mark.parametrize(
    "dispatch_name",
    (
        "_complete_execution_checkpoint",
        "_runtime_checkpoint",
        "_revalidate_mutator_session_v1",
    ),
)
def test_public_benchmark_checkpoint_rejects_post_call_dispatch_code_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dispatch_name: str,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    dispatch = getattr(execution_module, dispatch_name)
    original_code = dispatch.__code__
    replacement_calls: list[object] = []
    monkeypatch.setitem(
        dispatch.__globals__,
        "_TEST_DISPATCH_REPLACEMENT_CALLS",
        replacement_calls,
    )

    def replacement(*args: object, **kwargs: object) -> None:
        calls = globals()["_TEST_DISPATCH_REPLACEMENT_CALLS"]
        assert isinstance(calls, list)
        calls.append((args, kwargs))

    assert replacement.__closure__ is None

    def mutate() -> None:
        monkeypatch.setattr(dispatch, "__code__", replacement.__code__)

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)
    try:
        outcome = execution_module._resume_capsule(
            capsule,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider),
        )
    finally:
        dispatch.__code__ = original_code

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert replacement_calls == []
    assert raw == []


def test_public_benchmark_checkpoint_rejects_coordinated_matcher_and_dispatch_code_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    matcher = execution_module._function_matches_seal
    checkpoint = execution_module._complete_execution_checkpoint
    original_matcher_code = matcher.__code__
    original_checkpoint_code = checkpoint.__code__
    checkpoint_calls: list[object] = []
    monkeypatch.setitem(
        checkpoint.__globals__,
        "_TEST_COORDINATED_CHECKPOINT_CALLS",
        checkpoint_calls,
    )

    def accept_match(_value: object, _seal: object) -> bool:
        return True

    def skip_checkpoint(*args: object, **kwargs: object) -> None:
        calls = globals()["_TEST_COORDINATED_CHECKPOINT_CALLS"]
        assert isinstance(calls, list)
        calls.append((args, kwargs))

    assert accept_match.__closure__ is None
    assert skip_checkpoint.__closure__ is None

    def mutate() -> None:
        matcher.__code__ = accept_match.__code__
        checkpoint.__code__ = skip_checkpoint.__code__

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)
    try:
        outcome = execution_module._resume_capsule(
            capsule,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider),
        )
    finally:
        matcher.__code__ = original_matcher_code
        checkpoint.__code__ = original_checkpoint_code

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert checkpoint_calls == []
    assert raw == []


def test_public_benchmark_checkpoint_rejects_post_call_runtime_checkpoint_default_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)

    def integrity_only_checkpoint(
        *_args: object,
        _runtime_integrity_check: Callable[[], bool] = runtime_integrity_check,
        **_kwargs: object,
    ) -> None:
        if not _runtime_integrity_check():
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    replacement_calls: list[object] = []
    runtime_defaults = integrity_only_checkpoint.__kwdefaults__
    assert runtime_defaults is not None
    original_runtime_integrity_check = runtime_defaults["_runtime_integrity_check"]

    def replacement_runtime_integrity_check() -> bool:
        replacement_calls.append(object())
        return True

    def mutate() -> None:
        monkeypatch.setitem(
            runtime_defaults,
            "_runtime_integrity_check",
            replacement_runtime_integrity_check,
        )

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)
    try:
        outcome = execution_module._resume_capsule(
            capsule,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider),
        )
    finally:
        runtime_defaults["_runtime_integrity_check"] = original_runtime_integrity_check

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert len(provider.benchmark_calls) == 1
    assert replacement_calls == []
    assert raw == []


@pytest.mark.parametrize("helper_authority", ("function", "class"))
def test_public_benchmark_checkpoint_rejects_post_call_runtime_helper_composition_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    helper_authority: str,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    checkpoint_calls = [0]
    mutation_complete = [False]
    post_mutation_checkpoint_calls = [0]
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    forged_calls: list[object] = []
    pre_call_checkpoint_counts: list[int] = []
    checker_results: list[tuple[bool, bool]] = []

    def accept_function_match(_value: object, _seal: object) -> bool:
        return True

    helper_mutations = [
        (
            execution_module._function_matches_seal,
            execution_module._function_matches_seal.__code__,
            accept_function_match.__code__,
        )
    ]
    if helper_authority == "function":

        def accept_attribute_match(_seal: object) -> bool:
            return True

        helper_mutations.append(
            (
                execution_module._attribute_matches_seal,
                execution_module._attribute_matches_seal.__code__,
                accept_attribute_match.__code__,
            )
        )
        owner = execution_module._sanitizer_module.heapq
        name = "heappush"
    else:

        def accept_class_match(_value: object, _seal: object) -> bool:
            return True

        helper_mutations = [
            (
                execution_module._class_matches_seal,
                execution_module._class_matches_seal.__code__,
                accept_class_match.__code__,
            )
        ]
        owner = type(evidence)
        name = "model_dump"
    original_consumer = getattr(owner, name)

    def forged_consumer(*args: object, **kwargs: object) -> object:
        forged_calls.append((args, kwargs))
        return original_consumer(*args, **kwargs)

    def restore_mutation() -> None:
        for helper, original_code, _forged_code in helper_mutations:
            helper.__code__ = original_code
        setattr(owner, name, original_consumer)

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        checkpoint_calls[0] += 1
        if mutation_complete[0]:
            post_mutation_checkpoint_calls[0] += 1
        if not runtime_integrity_check():
            if mutation_complete[0]:
                restore_mutation()
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )

    def mutate() -> None:
        pre_call_checkpoint_counts.append(checkpoint_calls[0])
        for helper, _original_code, forged_code in helper_mutations:
            monkeypatch.setattr(helper, "__code__", forged_code)
        monkeypatch.setattr(owner, name, forged_consumer, raising=False)
        assert getattr(owner, name) is forged_consumer
        mutation_complete[0] = True
        checker_results.append(
            (
                execution_module._provider_adapter_runtime_intact(),
                runtime_integrity_check(),
            )
        )
        assert forged_calls == []

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=("Done.",)),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1, (
        pre_call_checkpoint_counts,
        post_mutation_checkpoint_calls,
        checker_results,
        forged_calls,
        len(provider.benchmark_calls),
        raw,
        outcome,
    )
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert pre_call_checkpoint_counts and pre_call_checkpoint_counts[0] > 0
    assert post_mutation_checkpoint_calls[0] == 1
    assert checker_results == [(False, False)]
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


@pytest.mark.parametrize("method_name", ("model_validate", "model_dump"))
def test_public_benchmark_checkpoint_rejects_post_call_base_model_method_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    checkpoint_defaults = execution_module._runtime_checkpoint.__kwdefaults__
    assert checkpoint_defaults is not None
    runtime_integrity_check = checkpoint_defaults["_runtime_integrity_check"]
    assert callable(runtime_integrity_check)
    capsule = _single_plan_capsule(
        tmp_path,
        monkeypatch,
        provider_kind="fake",
        provider_model="gpt-5.6-sol",
        benchmark_generation=True,
    )
    _install_fast_runtime(monkeypatch)
    checkpoint_calls = [0]
    mutation_complete = [False]
    post_mutation_checkpoint_calls = [0]

    def integrity_only_checkpoint(*_args: object, **_kwargs: object) -> None:
        checkpoint_calls[0] += 1
        if mutation_complete[0]:
            post_mutation_checkpoint_calls[0] += 1
        if not runtime_integrity_check():
            if mutation_complete[0]:
                restore_mutation()
            raise ResumeError("producer_runtime_differs")

    monkeypatch.setattr(
        execution_module,
        "_runtime_checkpoint",
        integrity_only_checkpoint,
    )
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    forged_calls: list[object] = []
    pre_call_checkpoint_counts: list[int] = []
    checker_results: list[tuple[bool, bool]] = []
    original_descriptor = vars(BaseModel)[method_name]

    if method_name == "model_validate":
        assert type(original_descriptor) is classmethod
        original = original_descriptor.__func__

        def forged(cls: type[BaseModel], *args: object, **kwargs: object) -> object:
            forged_calls.append((cls, args, kwargs))
            return original(cls, *args, **kwargs)

        replacement: object = classmethod(forged)
    else:
        assert callable(original_descriptor)
        original = original_descriptor

        def forged(self: BaseModel, *args: object, **kwargs: object) -> object:
            forged_calls.append((self, args, kwargs))
            return original(self, *args, **kwargs)

        replacement = forged

    def restore_mutation() -> None:
        setattr(BaseModel, method_name, original_descriptor)

    def mutate() -> None:
        pre_call_checkpoint_counts.append(checkpoint_calls[0])
        monkeypatch.setattr(BaseModel, method_name, replacement)
        assert vars(BaseModel)[method_name] is replacement
        inherited_resolution = getattr(type(evidence), method_name)
        if method_name == "model_validate":
            assert inherited_resolution.__func__ is forged
        else:
            assert inherited_resolution is forged
        mutation_complete[0] = True
        checker_results.append(
            (
                execution_module._provider_adapter_runtime_intact(),
                runtime_integrity_check(),
            )
        )
        assert forged_calls == []

    provider = _BenchmarkAuthorityMutatingProvider(evidence, mutate)

    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )

    _events, raw = _journal_rows(capsule)
    assert outcome.exit_code == 1, (
        pre_call_checkpoint_counts,
        post_mutation_checkpoint_calls,
        checker_results,
        forged_calls,
        len(provider.benchmark_calls),
        raw,
        outcome,
    )
    assert outcome.result.state == "AMBIGUOUS_INFLIGHT"
    assert pre_call_checkpoint_counts and pre_call_checkpoint_counts[0] > 0
    assert post_mutation_checkpoint_calls[0] == 1
    assert checker_results == [(False, False)]
    assert len(provider.benchmark_calls) == 1
    assert forged_calls == []
    assert raw == []


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
