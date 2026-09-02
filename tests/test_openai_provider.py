from __future__ import annotations

import builtins
import csv
import hashlib
import importlib.metadata
import io
import os
import socket
import subprocess
import sys
import threading
import tomllib
import typing
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from laconian_eval.capsule.attempts import normalize_provider_outcome
from laconian_eval.capsule.sanitizer import SanitizerPatterns
from laconian_eval.providers import GenerationRequest, ProviderError, TokenUsage
from laconian_eval.providers.openai import OpenAIProvider


class _BytesSubclass(bytes):
    pass


class _StrSubclass(str):
    pass


class _IntSubclass(int):
    pass


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True


class _SDKModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class _BenchmarkResponse:
    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)

    @property
    def output_text(self) -> object:
        raise AssertionError("benchmark adapter must not read response.output_text")


_EXPECTED_LOCK_DEPENDENCIES = (
    "anyio",
    "httpx2",
    "jiter",
    "pydantic",
    "sniffio",
    "typing-extensions",
)
_EXPECTED_LOCK_SDIST = (
    "https://files.pythonhosted.org/packages/7d/9c/ba0c292b4032ede74c249ca314ad64eb1bb5a03a843f6e01facb02f80cd8/openai-3.3.1.tar.gz",
    "sha256:6f22807de1a976c932cecda620e8172a8c3fdbaeed29c7f21564e0c2410edf56",
    1_282_113,
    "2026-08-19T16:31:35.006Z",
)
_EXPECTED_LOCK_WHEEL = (
    "https://files.pythonhosted.org/packages/6a/db/2b7a1b3de659bb82aef979116c74e809982b13e42c057759767552b5155f/openai-3.3.1-py3-none-any.whl",
    "sha256:9652df7fdf8ee6f5bd58e0a12f2b1d414a18e0f06bb7a9a57c8643a5f5469bd3",
    1_690_337,
    "2026-08-19T16:31:32.812Z",
)

_EXPECTED_OPENAI_WHEEL_RECORD = (
    164_291,
    "4a9a567d1c130100b9fd5bb48d4f6605d39f818d0466329225a853a7ff5ead31",
)
_EXPECTED_OPENAI_RECORD_PROJECTION = (
    1_530,
    6_364_613,
    163_990,
    "8b8a7f3f95d8937c1e795223842535a58ad7e1e17991eb66b565429b345393db",
)


def _assert_sdk_error(error: BaseException, code: str) -> None:
    from laconian_eval.providers import openai as provider_openai

    assert isinstance(error, provider_openai.BenchmarkSDKContractError)
    assert error.code == code
    assert error.args == ("public benchmark SDK contract verification failed",)
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.fixture
def precredential_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    counters = [0, 0, 0, 0, 0]

    def reject(index: int):
        def rejected(*args: object, **kwargs: object) -> object:
            counters[index] += 1
            raise AssertionError("precredential SDK gate crossed an external boundary")

        return rejected

    provider_trap = reject(0)
    environment_trap = reject(1)
    credential_trap = reject(2)
    monkeypatch.setattr(OpenAIProvider, "generate", provider_trap)
    monkeypatch.setattr(type(os.environ), "get", environment_trap)
    monkeypatch.setattr(type(os.environ), "__getitem__", credential_trap)
    monkeypatch.setattr(OpenAIProvider, "__init__", reject(3))
    monkeypatch.setattr(socket, "create_connection", reject(4))
    probes = (
        (OpenAIProvider.generate, (object(), object())),
        (os.environ.get, ("NON_SECRET_SETTING",)),
        (os.environ.__getitem__, ("OPENAI_API_KEY",)),
        (OpenAIProvider, ()),
        (socket.create_connection, (("example.invalid", 443),)),
    )
    for probe, args in probes:
        with pytest.raises(AssertionError, match="external boundary"):
            probe(*args)
    assert tuple(counters) == (1, 1, 1, 1, 1)
    counters[:] = [0, 0, 0, 0, 0]
    yield
    assert type(os.environ).get is environment_trap
    assert type(os.environ).__getitem__ is credential_trap
    assert tuple(counters) == (0, 0, 0, 0, 0)


@pytest.fixture(autouse=True)
def isolated_benchmark_sdk_process_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from laconian_eval.providers import openai as provider_openai

    monkeypatch.setattr(provider_openai, "_PRIVATE_OPENAI_GRAPH", None, raising=False)
    yield


def test_public_benchmark_policy_rejects_float_token_ceiling() -> None:
    from pydantic import ValidationError

    from laconian_eval.providers.base import PublicBenchmarkRequestPolicyV1

    with pytest.raises(ValidationError):
        PublicBenchmarkRequestPolicyV1(
            schema_version="PublicBenchmarkRequestPolicyV1",
            service_tier="default",
            prompt_cache_mode="explicit",
            prompt_cache_ttl="30m",
            reasoning_mode="omitted",
            input_token_bound_version="openai-utf8-envelope-v1",
            max_input_tokens=272000.0,  # type: ignore[arg-type]
        )


def test_benchmark_sdk_contract_rejects_invalid_inputs_without_provider_access(
    precredential_guard: None,
) -> None:
    from laconian_eval.providers.openai import (
        BenchmarkSDKContractError,
        require_benchmark_sdk_contract,
    )

    with pytest.raises(BenchmarkSDKContractError) as caught:
        require_benchmark_sdk_contract(
            c0_uv_lock_bytes=b"not the lock",
            expected_c0_uv_lock_sha256="0" * 64,
        )
    assert caught.value.code == "lock-digest"
    assert caught.value.args == ("public benchmark SDK contract verification failed",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_benchmark_sdk_contract_accepts_frozen_openai_member(precredential_guard: None) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    assert (
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
        is None
    )
    parsed = tomllib.loads(lock.decode("utf-8"))
    member = [item for item in parsed["package"] if item.get("name") == "openai"]
    assert member == [
        {
            "name": "openai",
            "version": "3.3.1",
            "source": {"registry": "https://pypi.org/simple"},
            "dependencies": [{"name": name} for name in _EXPECTED_LOCK_DEPENDENCIES],
            "sdist": dict(
                zip(
                    ("url", "hash", "size", "upload-time"),
                    _EXPECTED_LOCK_SDIST,
                    strict=True,
                )
            ),
            "wheels": [
                dict(
                    zip(
                        ("url", "hash", "size", "upload-time"),
                        _EXPECTED_LOCK_WHEEL,
                        strict=True,
                    )
                )
            ],
        }
    ]
    assert provider_openai.BENCHMARK_OPENAI_LOCK_REGISTRY_V1 == "https://pypi.org/simple"
    assert provider_openai.BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1 == _EXPECTED_LOCK_DEPENDENCIES
    assert provider_openai.BENCHMARK_OPENAI_LOCK_SDIST_V1 == _EXPECTED_LOCK_SDIST
    assert provider_openai.BENCHMARK_OPENAI_LOCK_WHEELS_V1 == (_EXPECTED_LOCK_WHEEL,)
    assert (
        provider_openai._OPENAI_WHEEL_RECORD_SIZE,
        provider_openai._OPENAI_WHEEL_RECORD_SHA256,
    ) == _EXPECTED_OPENAI_WHEEL_RECORD
    assert (
        provider_openai._OPENAI_RECORD_PROJECTION_ROWS,
        provider_openai._OPENAI_RECORD_PROJECTION_DECLARED_SIZE,
        provider_openai._OPENAI_RECORD_PROJECTION_PREIMAGE_SIZE,
        provider_openai._OPENAI_RECORD_PROJECTION_SHA256,
    ) == _EXPECTED_OPENAI_RECORD_PROJECTION
    assert provider_openai.BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1 == (
        b'{"input":"sdk-contract-input-v1","instructions":"sdk-contract-instructions-v1",'
        b'"max_output_tokens":1024,"model":"gpt-5.6-sol","prompt_cache_options":'
        b'{"mode":"explicit","ttl":"30m"},"reasoning":{"effort":"medium"},'
        b'"service_tier":"default","store":false,"text":{"verbosity":"medium"}}'
    )
    assert provider_openai.BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1 == (
        "c7f3d0d8d7b056226b10195e76e9974c213881e3678d09aee071ad3cbedb0211"
    )
    from laconian_eval.providers.base import (
        PublicBenchmarkRequestPolicyV1,
        PublicBenchmarkRequestV1,
    )

    policy = PublicBenchmarkRequestPolicyV1(
        schema_version="PublicBenchmarkRequestPolicyV1",
        service_tier="default",
        prompt_cache_mode="explicit",
        prompt_cache_ttl="30m",
        reasoning_mode="omitted",
        input_token_bound_version="openai-utf8-envelope-v1",
        max_input_tokens=272000,
    )
    probe = PublicBenchmarkRequestV1(
        case_id="sdk-contract-probe-v1",
        arm="if",
        repetition=0,
        requested_model_id="gpt-5.6-sol",
        instructions="sdk-contract-instructions-v1",
        prompt="sdk-contract-input-v1",
        max_output_tokens=1024,
        temperature=None,
        timeout_seconds=120.0,
        policy=policy,
        reasoning_effort="medium",
        text_verbosity="medium",
    )
    assert tuple(provider_openai._public_benchmark_responses_kwargs(probe)) == (
        "model",
        "instructions",
        "input",
        "max_output_tokens",
        "store",
        "reasoning",
        "text",
        "prompt_cache_options",
        "service_tier",
    )
    record = provider_openai._build_verified_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )
    assert tuple(type(record).model_fields) == (
        "schema_version",
        "distribution",
        "installed_version",
        "pydantic_version",
        "pydantic_core_version",
        "c0_uv_lock_sha256",
        "lock_version",
        "lock_registry",
        "lock_dependencies",
        "lock_sdist_url",
        "lock_sdist_hash",
        "lock_sdist_size",
        "lock_sdist_upload_time",
        "lock_wheel_url",
        "lock_wheel_hash",
        "lock_wheel_size",
        "lock_wheel_upload_time",
        "request_model_qualified_name",
        "response_model_qualified_name",
        "request_fields",
        "structured_request_paths",
        "response_paths",
        "returned_model_path",
        "response_content_paths",
        "serializer_projection_sha256",
        "structured_serializer_projection_sha256",
        "contract_sha256",
    )
    from laconian_eval.capsule.canonical import stable_digest

    assert record.contract_sha256 == stable_digest(
        "laconian-benchmark-sdk-contract-v1",
        record.model_dump(mode="json", exclude={"contract_sha256"}),
    )
    assert record.response_content_paths == (
        "response.id",
        "response.status",
        "response.error",
        "response.output",
    )


def test_authenticated_openai_install_matches_frozen_record_projection() -> None:
    from laconian_eval.providers import openai as provider_openai

    install = provider_openai._authenticate_openai_install()

    assert install.root.name == "openai"
    assert len(install.entries) == _EXPECTED_OPENAI_RECORD_PROJECTION[0]
    assert (
        sum(entry.size for entry in install.entries.values())
        == (_EXPECTED_OPENAI_RECORD_PROJECTION[1])
    )
    assert install.record_projection_sha256 == _EXPECTED_OPENAI_RECORD_PROJECTION[3]


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "unknown", "traversal", "hash", "size"],
)
def test_sdk_contract_rejects_installed_record_drift_before_source_exec(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    record_path = Path(
        importlib.metadata.distribution("openai").locate_file("openai-3.3.1.dist-info/RECORD")
    )
    rows = list(
        csv.reader(
            io.StringIO(record_path.read_text(encoding="utf-8"), newline=""),
            strict=True,
        )
    )
    target = next(index for index, row in enumerate(rows) if row[0] == "openai/__init__.py")
    if mutation == "missing":
        rows.pop(target)
    elif mutation == "duplicate":
        rows.insert(target, list(rows[target]))
    elif mutation == "unknown":
        rows.insert(target, ["openai/unknown.py", rows[target][1], rows[target][2]])
    elif mutation == "traversal":
        rows[target][0] = "openai/../outside.py"
    elif mutation == "hash":
        rows[target][1] = "sha256=" + "A" * 43
    else:
        rows[target][2] = str(int(rows[target][2]) + 1)
    tampered = "".join(",".join(row) + "\n" for row in rows).encode("utf-8")
    monkeypatch.setattr(provider_openai, "_read_openai_record_bytes", lambda _path: tampered)
    monkeypatch.setattr(provider_openai, "_PRIVATE_OPENAI_GRAPH", None, raising=False)
    exec_calls: list[str] = []
    monkeypatch.setattr(
        provider_openai._PrivateOpenAITypeLoader,
        "_before_exec",
        lambda _self, name, _path: exec_calls.append(name),
    )
    lock = Path("uv.lock").read_bytes()

    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )

    _assert_sdk_error(caught.value, "request-model")
    assert exec_calls == []


def test_sdk_contract_authenticates_source_bytes_before_exec(
    monkeypatch: pytest.MonkeyPatch,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._PrivateOpenAITypeLoader._read_source

    def malicious_source(
        self: object,
        name: str,
        path: Path,
    ) -> bytes | str:
        source = original(self, name, path)
        if name == "openai.types.responses.response_create_params":
            suffix: bytes | str = (
                b"\nimport os; os.environ.get('OPENAI_API_KEY')\n"
                if isinstance(source, bytes)
                else "\nimport os; os.environ.get('OPENAI_API_KEY')\n"
            )
            return source + suffix  # type: ignore[operator]
        return source

    monkeypatch.setattr(provider_openai._PrivateOpenAITypeLoader, "_read_source", malicious_source)
    monkeypatch.setattr(provider_openai, "_PRIVATE_OPENAI_GRAPH", None, raising=False)
    exec_calls: list[str] = []
    monkeypatch.setattr(
        provider_openai._PrivateOpenAITypeLoader,
        "_before_exec",
        lambda _self, name, _path: exec_calls.append(name),
    )
    lock = Path("uv.lock").read_bytes()

    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )

    _assert_sdk_error(caught.value, "request-model")
    assert "openai.types.responses.response_create_params" not in exec_calls


@pytest.mark.parametrize(
    "version",
    ["3.3.0", 331, True, None, _StrSubclass("3.3.1"), _EqualitySpoof()],
)
def test_benchmark_sdk_contract_rejects_wrong_installed_version_without_details(
    monkeypatch: pytest.MonkeyPatch, version: object, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    monkeypatch.setattr(provider_openai, "_installed_openai_version", lambda: version)
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "installed-version")


@pytest.mark.parametrize(
    "lock_bytes",
    [
        "bad",
        bytearray(b"bad"),
        memoryview(b"bad"),
        _BytesSubclass(b"bad"),
        b"",
        b"x" * 1_048_577,
    ],
)
def test_benchmark_sdk_contract_rejects_nonexact_lock_bytes(
    lock_bytes: object, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock_bytes,  # type: ignore[arg-type]
            expected_c0_uv_lock_sha256="0" * 64,
        )
    _assert_sdk_error(caught.value, "lock-entry")


def test_sdk_contract_type_loading_reads_no_environment_in_fresh_process(
    precredential_guard: None,
) -> None:
    script = r"""
import hashlib
import os
from pathlib import Path
from laconian_eval.providers.openai import require_benchmark_sdk_contract

def forbidden(*args, **kwargs):
    raise AssertionError("environment read")

type(os.environ).get = forbidden
type(os.environ).__getitem__ = forbidden
lock = Path("uv.lock").read_bytes()
require_benchmark_sdk_contract(
    c0_uv_lock_bytes=lock,
    expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_provider_import_does_not_inspect_openai_distribution() -> None:
    script = r"""
import importlib.metadata

def forbidden(*args, **kwargs):
    raise AssertionError("distribution inspected during owner import")

importlib.metadata.distribution = forbidden
import laconian_eval.providers.openai
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_sdk_contract_isolated_probe_never_exposes_parent_module_or_plugin_state(
    precredential_guard: None,
) -> None:
    from pydantic.plugin import _loader as plugin_loader

    from laconian_eval.providers import openai as provider_openai

    before_modules = {
        key: value
        for key, value in sys.modules.copy().items()
        if key == "openai" or key.startswith("openai.")
    }
    before_plugins = plugin_loader.get_plugins
    errors: list[BaseException] = []
    lock = Path("uv.lock").read_bytes()

    def verify() -> None:
        try:
            provider_openai.require_benchmark_sdk_contract(
                c0_uv_lock_bytes=lock,
                expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
            )
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=verify) for _ in range(2)]
    for worker in workers:
        worker.start()
    while any(worker.is_alive() for worker in workers):
        assert plugin_loader.get_plugins is before_plugins
        assert {
            key: value
            for key, value in sys.modules.copy().items()
            if key == "openai" or key.startswith("openai.")
        } == before_modules
    for worker in workers:
        worker.join()
    assert errors == []
    assert plugin_loader.get_plugins is before_plugins


def test_sdk_contract_isolated_probe_exception_leaves_parent_state_unchanged(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from pydantic.plugin import _loader as plugin_loader

    from laconian_eval.providers import openai as provider_openai

    before_modules = {
        key: value
        for key, value in sys.modules.copy().items()
        if key == "openai" or key.startswith("openai.")
    }
    before_plugins = plugin_loader.get_plugins
    monkeypatch.setattr(
        provider_openai._PrivateOpenAITypeLoader,
        "import_module",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private loader failure")),
    )
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")
    assert {
        key: value
        for key, value in sys.modules.copy().items()
        if key == "openai" or key.startswith("openai.")
    } == before_modules
    assert plugin_loader.get_plugins is before_plugins
    assert provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get() is None


def test_sdk_contract_private_graphs_are_distinct_and_never_globally_visible() -> None:
    from laconian_eval.providers import openai as provider_openai

    ambient_openai = importlib.import_module("openai")
    with provider_openai._isolated_openai_type_modules():
        first, _ = provider_openai._load_sdk_request_contract_types()
        first_modules = provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get().modules
        assert all(sys.modules.get(name) is not module for name, module in first_modules.items())
    with provider_openai._isolated_openai_type_modules():
        second, _ = provider_openai._load_sdk_request_contract_types()
        second_modules = provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get().modules
        assert all(sys.modules.get(name) is not module for name, module in second_modules.items())
    assert first is not second
    assert sys.modules["openai"] is ambient_openai
    assert provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get() is None


def test_sdk_contract_gate_is_pure_with_real_sdk_preloaded() -> None:
    from laconian_eval.providers import openai as provider_openai

    ambient_openai = importlib.import_module("openai")
    before_modules = {
        name: module
        for name, module in sys.modules.copy().items()
        if name == "openai" or name.startswith("openai.")
    }
    before_namespace = dict(vars(ambient_openai))
    before_meta_path = tuple(sys.meta_path)
    before_sys_path = tuple(sys.path)
    before_init = OpenAIProvider.__init__
    before_generate = OpenAIProvider.generate
    lock = Path("uv.lock").read_bytes()

    result = provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )

    assert result is None
    loader = provider_openai._PRIVATE_OPENAI_GRAPH.loader
    assert all(sys.modules.get(name) is not module for name, module in loader.modules.items())
    assert sys.modules["openai"] is ambient_openai
    after_modules = {
        name: module
        for name, module in sys.modules.copy().items()
        if name == "openai" or name.startswith("openai.")
    }
    assert after_modules.keys() == before_modules.keys()
    assert all(after_modules[name] is module for name, module in before_modules.items())
    assert vars(ambient_openai).keys() == before_namespace.keys()
    assert all(vars(ambient_openai)[name] is value for name, value in before_namespace.items())
    assert tuple(sys.meta_path) == before_meta_path
    assert tuple(sys.path) == before_sys_path
    assert OpenAIProvider.__init__ is before_init
    assert OpenAIProvider.generate is before_generate
    assert not hasattr(provider_openai, "_PENDING_AUTHENTICATED_OPENAI_INSTALL")
    assert not hasattr(provider_openai, "_AUTHENTICATED_OPENAI_MODULE_GRAPH")


def test_sdk_contract_cached_graph_uses_module_level_import_dispatcher() -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )

    loader = provider_openai._PRIVATE_OPENAI_GRAPH.loader
    assert loader.modules
    for module in loader.modules.values():
        module_builtins = module.__dict__.get("__builtins__")
        if isinstance(module_builtins, dict):
            assert module_builtins["__import__"] is provider_openai._dispatch_private_openai_import


def test_sdk_contract_reuses_one_graph_across_twenty_default_calls() -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    loader_ids: list[int] = []

    for _ in range(20):
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
        loader_ids.append(id(provider_openai._PRIVATE_OPENAI_GRAPH.loader))

    assert len(set(loader_ids)) == 1


def test_sdk_contract_twenty_calls_retain_only_one_private_graph_in_fresh_process() -> None:
    script = r"""
import gc
import hashlib
from pathlib import Path
from laconian_eval.providers import openai as provider_openai

lock = Path("uv.lock").read_bytes()
for _ in range(20):
    provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )
gc.collect()
loaders = [
    value
    for value in gc.get_objects()
    if type(value) is provider_openai._PrivateOpenAITypeLoader
]
assert len(loaders) == 1, len(loaders)
assert loaders[0] is provider_openai._PRIVATE_OPENAI_GRAPH.loader
assert provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get() is None
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_sdk_contract_concurrent_calls_build_and_share_one_private_graph() -> None:
    from laconian_eval.providers import openai as provider_openai

    loader_ids: set[int] = set()
    observation_lock = threading.Lock()
    lock = Path("uv.lock").read_bytes()
    digest = hashlib.sha256(lock).hexdigest()
    errors: list[BaseException] = []

    def verify() -> None:
        try:
            provider_openai.require_benchmark_sdk_contract(
                c0_uv_lock_bytes=lock,
                expected_c0_uv_lock_sha256=digest,
            )
            assert provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get() is None
            cached = provider_openai._PRIVATE_OPENAI_GRAPH
            assert cached is not None
            with observation_lock:
                loader_ids.add(id(cached.loader))
        except BaseException as exc:
            errors.append(exc)

    workers = [threading.Thread(target=verify) for _ in range(16)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert errors == []
    assert len(loader_ids) == 1


def test_sdk_contract_cached_graph_reauthenticates_source_on_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    digest = hashlib.sha256(lock).hexdigest()
    provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=digest,
    )
    cached = provider_openai._PRIVATE_OPENAI_GRAPH
    assert cached is not None
    original = provider_openai._read_bounded_regular_file

    def drifted(path: Path, maximum_bytes: int) -> bytes:
        value = original(path, maximum_bytes)
        if path.name == "response_create_params.py":
            return value + b" "
        return value

    monkeypatch.setattr(provider_openai, "_read_bounded_regular_file", drifted)

    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=digest,
        )

    _assert_sdk_error(caught.value, "request-model")
    assert provider_openai._PRIVATE_OPENAI_GRAPH is cached


@pytest.mark.parametrize("seam", ["type", "serializer"])
def test_sdk_contract_cached_graph_never_caches_verifier_verdict(
    monkeypatch: pytest.MonkeyPatch,
    seam: str,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    digest = hashlib.sha256(lock).hexdigest()
    provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=digest,
    )
    cached = provider_openai._PRIVATE_OPENAI_GRAPH
    assert cached is not None
    fresh_loader_ids: list[int] = []
    with monkeypatch.context() as changed:
        if seam == "type":

            def changed_response_type() -> object:
                loader = provider_openai._ACTIVE_PRIVATE_OPENAI_LOADER.get()
                assert loader is not None
                fresh_loader_ids.append(id(loader))
                return object

            changed.setattr(
                provider_openai, "_load_sdk_response_contract_type", changed_response_type
            )
            expected_code = "response-model"
        else:
            original = provider_openai._public_benchmark_responses_kwargs
            original_after_exec = provider_openai._PrivateOpenAITypeLoader._after_exec

            def observed_after_exec(
                self: object, name: str, path: Path, module: ModuleType
            ) -> None:
                fresh_loader_ids.append(id(self))
                original_after_exec(self, name, path, module)

            def changed_builder(request: object) -> dict[str, object]:
                result = original(request)  # type: ignore[arg-type]
                result["service_tier"] = "flex"
                return result

            changed.setattr(provider_openai, "_public_benchmark_responses_kwargs", changed_builder)
            changed.setattr(
                provider_openai._PrivateOpenAITypeLoader,
                "_after_exec",
                observed_after_exec,
            )
            expected_code = "serializer-projection"

        with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
            provider_openai.require_benchmark_sdk_contract(
                c0_uv_lock_bytes=lock,
                expected_c0_uv_lock_sha256=digest,
            )

    _assert_sdk_error(caught.value, expected_code)
    assert provider_openai._PRIVATE_OPENAI_GRAPH is cached
    assert fresh_loader_ids and id(cached.loader) not in fresh_loader_ids
    provider_openai.require_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=digest,
    )


def test_sdk_contract_private_source_anchor_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._rewrite_private_openai_source

    def drifted(name: str, source: str) -> str:
        if name == "openai._models":
            source = source.replace("DEFER_PYDANTIC_BUILD", "DRIFTED_PYDANTIC_BUILD")
        return original(name, source)

    monkeypatch.setattr(provider_openai, "_rewrite_private_openai_source", drifted)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


def test_invalid_lock_precedes_sdk_type_loading(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    monkeypatch.setattr(
        provider_openai,
        "_isolated_openai_type_modules",
        lambda: (_ for _ in ()).throw(AssertionError("SDK types loaded")),
    )
    malformed = b"not = [toml"
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=malformed,
            expected_c0_uv_lock_sha256=hashlib.sha256(malformed).hexdigest(),
        )
    _assert_sdk_error(caught.value, "lock-entry")


@pytest.mark.parametrize(
    "expected",
    [None, True, b"0" * 64, "A" * 64, "0" * 63, "g" * 64, _StrSubclass("0" * 64)],
)
def test_benchmark_sdk_contract_rejects_malformed_expected_digest(
    expected: object, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=b"x",
            expected_c0_uv_lock_sha256=expected,  # type: ignore[arg-type]
        )
    _assert_sdk_error(caught.value, "lock-digest")


def test_benchmark_sdk_contract_maps_missing_distribution_to_installed_version(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    def missing() -> object:
        raise importlib.metadata.PackageNotFoundError("openai")

    monkeypatch.setattr(provider_openai, "_installed_openai_version", missing)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "installed-version")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'version = "3.3.1"', b'version = "3.3.0"'),
        (b'registry = "https://pypi.org/simple"', b'registry = "https://example.invalid"'),
        (b'name = "httpx2"', b'name = "httpx"'),
        (b"openai-3.3.1.tar.gz", b"openai-3.3.0.tar.gz"),
        (
            b"sha256:6f22807de1a976c932cecda620e8172a8c3fdbaeed29c7f21564e0c2410edf56",
            b"sha256:0f22807de1a976c932cecda620e8172a8c3fdbaeed29c7f21564e0c2410edf56",
        ),
        (b"openai-3.3.1-py3-none-any.whl", b"openai-3.3.0-py3-none-any.whl"),
        (
            b"sha256:9652df7fdf8ee6f5bd58e0a12f2b1d414a18e0f06bb7a9a57c8643a5f5469bd3",
            b"sha256:0652df7fdf8ee6f5bd58e0a12f2b1d414a18e0f06bb7a9a57c8643a5f5469bd3",
        ),
        (b"1282113", b"1282114"),
        (b"1690337", b"1690338"),
        (b"2026-08-19T16:31:35.006Z", b"2026-08-19T16:31:35.007Z"),
        (b"2026-08-19T16:31:32.812Z", b"2026-08-19T16:31:32.813Z"),
    ],
)
def test_benchmark_sdk_contract_rejects_digest_consistent_lock_mutations(
    old: bytes, new: bytes, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    marker = b'[[package]]\nname = "openai"'
    start = lock.index(marker)
    end = lock.find(b"\n[[package]]", start + len(marker))
    member = lock[start : end if end >= 0 else len(lock)]
    assert member.count(old) == 1
    mutated = lock[:start] + member.replace(old, new, 1) + lock[start + len(member) :]
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=mutated,
            expected_c0_uv_lock_sha256=hashlib.sha256(mutated).hexdigest(),
        )
    _assert_sdk_error(caught.value, "lock-entry")


def test_benchmark_sdk_contract_rejects_malicious_lock_shapes(
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    marker = b'[[package]]\nname = "openai"'
    start = lock.index(marker)
    end = lock.find(b"\n[[package]]", start + len(marker))
    member = lock[start : end if end >= 0 else len(lock)]

    def replace_member(old: bytes, new: bytes) -> bytes:
        assert member.count(old) == 1
        return lock[:start] + member.replace(old, new, 1) + lock[start + len(member) :]

    variants = [
        replace_member(b'name = "openai"', b'name = "openai-x"'),
        lock[:start] + member + b"\n" + member + lock[start + len(member) :],
        b"\xff",
        b"not = [valid",
        replace_member(b'version = "3.3.1"', b'version = "3.3.1"\nunknown = true'),
        replace_member(
            b'source = { registry = "https://pypi.org/simple" }',
            b'source = { path = "." }',
        ),
        replace_member(
            b'    { name = "anyio" },\n    { name = "httpx2" },',
            b'    { name = "httpx2" },\n    { name = "anyio" },',
        ),
        replace_member(b'    { name = "sniffio" },\n', b""),
        replace_member(b"sdist = {", b"other = {"),
        replace_member(b"wheels = [", b"artifacts = ["),
    ]
    for malicious in variants:
        with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
            provider_openai.require_benchmark_sdk_contract(
                c0_uv_lock_bytes=malicious,
                expected_c0_uv_lock_sha256=hashlib.sha256(malicious).hexdigest(),
            )
        _assert_sdk_error(caught.value, "lock-entry")


def test_benchmark_sdk_contract_rejects_complete_lock_shape_matrix(
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    marker = b'[[package]]\nname = "openai"'
    start = lock.index(marker)
    end = lock.find(b"\n[[package]]", start + len(marker))
    member = lock[start : end if end >= 0 else len(lock)]

    def replace(old: bytes, new: bytes) -> bytes:
        assert member.count(old) == 1
        return lock[:start] + member.replace(old, new, 1) + lock[start + len(member) :]

    dependency_mutations = []
    for name in _EXPECTED_LOCK_DEPENDENCIES:
        line = f'    {{ name = "{name}" }},'.encode()
        dependency_mutations.extend(
            (
                replace(line, b""),
                replace(line, line + b"\n" + line),
                replace(line, line.replace(name.encode(), f"{name}-changed".encode())),
            )
        )
    dependency_line = b'    { name = "anyio" },'
    sdist_line = next(line for line in member.splitlines() if line.startswith(b"sdist = "))
    wheel_line = next(line for line in member.splitlines() if b"py3-none-any.whl" in line)
    variants = [
        b'package = "not-a-list"\n',
        b"".join(f'[[package]]\nname = "filler-{index}"\n'.encode() for index in range(4097)),
        replace(b'version = "3.3.1"', b'version = "3.3.1"\nversion = "3.3.1"'),
        replace(
            b'source = { registry = "https://pypi.org/simple" }',
            b'source = { editable = "." }',
        ),
        replace(b'source = { registry = "https://pypi.org/simple" }', b'source = { git = "x" }'),
        replace(
            b'source = { registry = "https://pypi.org/simple" }',
            b'source = { directory = "." }',
        ),
        replace(b"sdist = {", b"sdist = { unknown = true, "),
        replace(sdist_line, sdist_line + b"\n" + sdist_line),
        replace(b"wheels = [", b"wheels = []\nwheels = ["),
        replace(wheel_line, wheel_line + b"\n" + wheel_line),
        replace(dependency_line, dependency_line + b"\n" + dependency_line),
        *dependency_mutations,
    ]
    for malicious in variants:
        with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
            provider_openai.require_benchmark_sdk_contract(
                c0_uv_lock_bytes=malicious,
                expected_c0_uv_lock_sha256=hashlib.sha256(malicious).hexdigest(),
            )
        _assert_sdk_error(caught.value, "lock-entry")


@pytest.mark.parametrize(
    ("old", "new"),
    [(b"1282113", b"1282113.0"), (b"1282113", b"true"), (b"1690337", b"1690337.0")],
)
def test_benchmark_sdk_contract_rejects_nonexact_artifact_size_scalars(
    old: bytes,
    new: bytes,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    marker = b'[[package]]\nname = "openai"'
    start = lock.index(marker)
    end = lock.find(b"\n[[package]]", start + len(marker))
    member = lock[start : end if end >= 0 else len(lock)]
    assert member.count(old) == 1
    mutated = lock[:start] + member.replace(old, new) + lock[start + len(member) :]
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=mutated,
            expected_c0_uv_lock_sha256=hashlib.sha256(mutated).hexdigest(),
        )
    _assert_sdk_error(caught.value, "lock-entry")


@pytest.mark.parametrize("field", ["lock_sdist_size", "lock_wheel_size"])
@pytest.mark.parametrize("kind", ["float", "bool", "subclass"])
def test_verified_sdk_record_rejects_nonexact_artifact_size(field: str, kind: str) -> None:
    from pydantic import ValidationError

    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    record = provider_openai._build_verified_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )
    payload = record.model_dump(mode="json")
    expected = 1_282_113 if field == "lock_sdist_size" else 1_690_337
    value: object = {
        "float": float(expected),
        "bool": True,
        "subclass": _IntSubclass(expected),
    }[kind]
    payload[field] = value
    with pytest.raises(ValidationError):
        provider_openai.VerifiedBenchmarkSDKContractV1.model_validate(payload)


def test_benchmark_sdk_contract_rejects_sdk_type_and_projection_drift(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    lock = Path("uv.lock").read_bytes()
    digest = hashlib.sha256(lock).hexdigest()
    original_response_type = provider_openai._load_sdk_response_contract_type
    monkeypatch.setattr(
        provider_openai,
        "_load_sdk_response_contract_type",
        lambda: object,
    )
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock, expected_c0_uv_lock_sha256=digest
        )
    _assert_sdk_error(caught.value, "response-model")
    monkeypatch.setattr(provider_openai, "_load_sdk_response_contract_type", original_response_type)
    original_builder = provider_openai._public_benchmark_responses_kwargs

    def changed_builder(request: object) -> dict[str, object]:
        result = original_builder(request)  # type: ignore[arg-type]
        result["service_tier"] = "flex"
        return result

    monkeypatch.setattr(provider_openai, "_public_benchmark_responses_kwargs", changed_builder)
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock, expected_c0_uv_lock_sha256=digest
        )
    _assert_sdk_error(caught.value, "serializer-projection")


@pytest.mark.parametrize(
    ("seam", "code"),
    [
        ("_load_sdk_request_contract_types", "request-model"),
        ("_load_sdk_response_contract_type", "response-model"),
    ],
)
def test_sdk_type_loader_failures_map_to_matching_public_code(
    monkeypatch: pytest.MonkeyPatch, seam: str, code: str, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    monkeypatch.setattr(
        provider_openai,
        seam,
        lambda: (_ for _ in ()).throw(RuntimeError("private loader detail")),
    )
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, code)


def test_sdk_contract_response_anchor_import_failure_maps_only_response_model(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    monkeypatch.setattr(
        provider_openai,
        "_load_sdk_expected_response_anchor",
        lambda: (_ for _ in ()).throw(ImportError("private response import detail")),
    )
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "response-model")


def test_sdk_contract_response_identity_rejects_spoofed_qualified_name(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    fake_response = type(
        "Response",
        (),
        {"__module__": "openai.types.responses.response", "model_fields": {}},
    )
    monkeypatch.setattr(provider_openai, "_load_sdk_response_contract_type", lambda: fake_response)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "response-model")


def test_sdk_request_anchor_identity_is_independent_of_spoofed_names(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    fields = {name: object for name in provider_openai.BENCHMARK_OPENAI_REQUEST_FIELDS_V1}
    fake_nonstreaming = typing.TypedDict("ResponseCreateParamsNonStreaming", fields)
    fake_streaming = typing.TypedDict("ResponseCreateParamsStreaming", fields)
    fake_nonstreaming.__module__ = "openai.types.responses.response_create_params"
    fake_streaming.__module__ = "openai.types.responses.response_create_params"
    alias = fake_nonstreaming | fake_streaming
    monkeypatch.setattr(
        provider_openai,
        "_load_sdk_request_contract_types",
        lambda: (alias, (fake_nonstreaming, fake_streaming)),
    )

    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


@pytest.mark.parametrize("member_index", [0, 1])
@pytest.mark.parametrize("field", tuple(range(10)))
@pytest.mark.parametrize("mutation", ["delete", "replace"])
def test_sdk_contract_request_union_rejects_each_field_mutation(
    monkeypatch: pytest.MonkeyPatch,
    member_index: int,
    field: int,
    mutation: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._load_sdk_request_contract_types

    def mutated_member() -> tuple[object, tuple[object, ...]]:
        alias, members = original()
        annotations = members[member_index].__annotations__
        name = provider_openai.BENCHMARK_OPENAI_REQUEST_FIELDS_V1[field]
        annotation = annotations.pop(name)
        if mutation == "replace":
            annotations[f"{name}_changed"] = annotation
        return alias, members

    monkeypatch.setattr(provider_openai, "_load_sdk_request_contract_types", mutated_member)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


@pytest.mark.parametrize("member_index", [0, 1])
def test_sdk_contract_request_union_rejects_each_replaced_member(
    monkeypatch: pytest.MonkeyPatch, member_index: int, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._load_sdk_request_contract_types

    def replaced_member() -> tuple[object, tuple[object, ...]]:
        alias, members = original()
        changed = list(members)
        changed[member_index] = object
        return alias, tuple(changed)

    monkeypatch.setattr(provider_openai, "_load_sdk_request_contract_types", replaced_member)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


@pytest.mark.parametrize("mutation", ["reverse", "replace"])
def test_sdk_contract_request_alias_rejects_order_or_membership_drift(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._load_sdk_request_contract_types

    def changed_alias() -> tuple[object, tuple[object, ...]]:
        _alias, members = original()
        if mutation == "reverse":
            return members[1] | members[0], members
        return members[0], members

    monkeypatch.setattr(provider_openai, "_load_sdk_request_contract_types", changed_alias)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


def test_sdk_contract_request_member_identity_ignores_adversarial_equality(
    monkeypatch: pytest.MonkeyPatch, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    class EqualType(type):
        def __eq__(cls, other: object) -> bool:
            return True

        __hash__ = type.__hash__

    annotations = {name: object for name in provider_openai.BENCHMARK_OPENAI_REQUEST_FIELDS_V1}
    fake_nonstreaming = EqualType(
        "ResponseCreateParamsNonStreaming",
        (),
        {"__annotations__": annotations, "__module__": "forged.sdk"},
    )
    fake_streaming = EqualType(
        "ResponseCreateParamsStreaming",
        (),
        {"__annotations__": annotations, "__module__": "forged.sdk"},
    )
    original = provider_openai._load_sdk_request_contract_types

    def equal_candidates() -> tuple[object, tuple[object, ...]]:
        alias, _members = original()
        return alias, (fake_nonstreaming, fake_streaming)

    monkeypatch.setattr(provider_openai, "_load_sdk_request_contract_types", equal_candidates)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "request-model")


@pytest.mark.parametrize("seam", ["builder", "canonicalizer"])
def test_sdk_contract_contains_serializer_failures(
    monkeypatch: pytest.MonkeyPatch, seam: str, precredential_guard: None
) -> None:
    from laconian_eval.providers import openai as provider_openai

    if seam == "builder":
        monkeypatch.setattr(
            provider_openai,
            "_public_benchmark_responses_kwargs",
            lambda _request: (_ for _ in ()).throw(RuntimeError("secret builder detail")),
        )
    else:
        monkeypatch.setattr(
            provider_openai,
            "_canonical_json_v1",
            lambda _value: (_ for _ in ()).throw(UnicodeError("secret encoding detail")),
        )
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "serializer-projection")


@pytest.mark.parametrize("result_kind", ["non_mapping", "unsupported_value"])
def test_sdk_contract_contains_invalid_builder_results(
    monkeypatch: pytest.MonkeyPatch,
    result_kind: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    result: object = object() if result_kind == "non_mapping" else {"model": object()}
    monkeypatch.setattr(
        provider_openai, "_public_benchmark_responses_kwargs", lambda _request: result
    )
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "serializer-projection")


@pytest.mark.parametrize("member_index", tuple(range(9)))
@pytest.mark.parametrize("mutation", ["omit", "rename", "add", "reorder", "change"])
def test_sdk_contract_rejects_each_serializer_projection_mutation(
    monkeypatch: pytest.MonkeyPatch,
    member_index: int,
    mutation: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._public_benchmark_responses_kwargs

    def mutated_builder(request: object) -> dict[str, object]:
        original_projection = original(request)  # type: ignore[arg-type]
        items = list(original_projection.items())
        key, value = items[member_index]
        if mutation == "omit":
            items.pop(member_index)
        elif mutation == "rename":
            items[member_index] = (f"{key}_changed", value)
        elif mutation == "add":
            items.insert(member_index + 1, (f"{key}_extra", value))
        elif mutation == "reorder":
            item = items.pop(member_index)
            items.insert(0 if member_index else len(items), item)
        else:
            items[member_index] = (key, None)
        return dict(items)

    monkeypatch.setattr(provider_openai, "_public_benchmark_responses_kwargs", mutated_builder)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "serializer-projection")


def test_benchmark_sdk_contract_freezes_response_content_roots(
    precredential_guard: None,
) -> None:
    from pydantic import ValidationError

    from laconian_eval.capsule.canonical import stable_digest
    from laconian_eval.providers import openai as provider_openai

    expected = (
        "response.id",
        "response.status",
        "response.error",
        "response.output",
    )
    assert expected == provider_openai.BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1
    with provider_openai._isolated_openai_type_modules():
        response_model = provider_openai._load_sdk_response_contract_type()
        assert all(provider_openai._typed_path_exists(response_model, path) for path in expected)
        assert not provider_openai._typed_path_exists(response_model, "response.output_text")

    lock = Path("uv.lock").read_bytes()
    record = provider_openai._build_verified_benchmark_sdk_contract(
        c0_uv_lock_bytes=lock,
        expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
    )
    base_payload = record.model_dump(mode="json")
    mutations = []
    for ordinal in range(len(expected)):
        missing = list(expected)
        missing.pop(ordinal)
        mutations.append(missing)
        replaced = list(expected)
        replaced[ordinal] = "response.output_text"
        mutations.append(replaced)
    mutations.append(list(reversed(expected)))
    for content_paths in mutations:
        payload = dict(base_payload)
        payload["response_content_paths"] = content_paths
        digest_payload = dict(payload)
        digest_payload.pop("contract_sha256")
        payload["contract_sha256"] = stable_digest(
            "laconian-benchmark-sdk-contract-v1", digest_payload
        )
        with pytest.raises(ValidationError):
            provider_openai.VerifiedBenchmarkSDKContractV1.model_validate(payload)


_RESPONSE_GRAPH_NODE_CASES = tuple(
    (path, component_index)
    for path in (
        "response.id",
        "response.status",
        "response.error",
        "response.output",
        "response.service_tier",
        "response.prompt_cache_options.mode",
        "response.prompt_cache_options.ttl",
        "response.usage.input_tokens",
        "response.usage.input_tokens_details.cached_tokens",
        "response.usage.input_tokens_details.cache_write_tokens",
        "response.usage.output_tokens",
        "response.usage.output_tokens_details.reasoning_tokens",
        "response.usage.total_tokens",
        "response.model",
    )
    for component_index in range(1, len(path.split(".")))
)


@pytest.mark.parametrize(("target_path", "component_index"), _RESPONSE_GRAPH_NODE_CASES)
@pytest.mark.parametrize("mutation", ["delete", "replace"])
def test_sdk_contract_response_graph_rejects_each_required_node_mutation(
    monkeypatch: pytest.MonkeyPatch,
    target_path: str,
    component_index: int,
    mutation: str,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    original = provider_openai._load_sdk_response_contract_type

    def mutated_response_model() -> object:
        root = original()
        branch = root
        components = target_path.split(".")[1:]
        for component in components[: component_index - 1]:
            assert isinstance(branch, type)
            annotation = provider_openai._sdk_model_field_annotation(branch, component)
            branch = provider_openai._annotation_branches(annotation)[0]
        assert isinstance(branch, type)
        target = components[component_index - 1]
        fields = vars(branch)["__pydantic_fields__"]
        assert type(fields) is dict
        if mutation == "delete":
            fields.pop(target)
        else:
            fields[target].annotation = typing.Any
        return root

    monkeypatch.setattr(provider_openai, "_load_sdk_response_contract_type", mutated_response_model)
    lock = Path("uv.lock").read_bytes()
    with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=lock,
            expected_c0_uv_lock_sha256=hashlib.sha256(lock).hexdigest(),
        )
    _assert_sdk_error(caught.value, "response-model")


class StubResponses:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubClient:
    def __init__(self, outcome: object) -> None:
        self.responses = StubResponses(outcome)


def request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "case_id": "case-001-en",
        "arm": "concise",
        "repetition": 0,
        "model": "test-model",
        "instructions": "Answer concisely.",
        "prompt": "Prompt",
        "max_output_tokens": 128,
        "temperature": None,
        "timeout_seconds": 60.0,
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def response(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "output_text": "Complete answer.",
        "_request_id": "req_123",
        "status": "completed",
        "model": "gpt-5.5-2026-08-01",
        "error": None,
        "usage": SimpleNamespace(
            input_tokens=15,
            output_tokens=4,
            total_tokens=19,
            input_tokens_details=SimpleNamespace(cached_tokens=6),
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def benchmark_request(**overrides: object) -> object:
    from laconian_eval.providers.base import (
        PublicBenchmarkRequestPolicyV1,
        PublicBenchmarkRequestV1,
    )

    values: dict[str, object] = {
        "case_id": "case-en",
        "arm": "if",
        "repetition": 0,
        "requested_model_id": "gpt-5.6-sol",
        "instructions": "instruction",
        "prompt": "prompt",
        "max_output_tokens": 1024,
        "temperature": None,
        "timeout_seconds": 60.0,
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "policy": PublicBenchmarkRequestPolicyV1(
            schema_version="PublicBenchmarkRequestPolicyV1",
            reasoning_mode="omitted",
            prompt_cache_mode="explicit",
            prompt_cache_ttl="30m",
            service_tier="default",
            input_token_bound_version="openai-utf8-envelope-v1",
            max_input_tokens=272000,
        ),
    }
    values.update(overrides)
    return PublicBenchmarkRequestV1(**values)  # type: ignore[arg-type]


_ABSENT = object()


def _sdk_node(**values: object) -> _SDKModel:
    return _SDKModel.model_construct(**values)


def _benchmark_output(text: object = "Complete answer.") -> list[object]:
    return [
        _sdk_node(
            type="message",
            content=[_sdk_node(type="output_text", text=text)],
        )
    ]


def benchmark_usage(
    *,
    input_tokens: object = 10,
    cached_tokens: object = 2,
    cache_write_tokens: object = 0,
    output_tokens: object = 4,
    reasoning_tokens: object = 1,
    total_tokens: object = 14,
) -> SimpleNamespace:
    input_details: dict[str, object] = {}
    if cached_tokens is not _ABSENT:
        input_details["cached_tokens"] = cached_tokens
    if cache_write_tokens is not _ABSENT:
        input_details["cache_write_tokens"] = cache_write_tokens
    output_details: dict[str, object] = {}
    if reasoning_tokens is not _ABSENT:
        output_details["reasoning_tokens"] = reasoning_tokens
    values: dict[str, object] = {
        "input_tokens_details": SimpleNamespace(**input_details),
        "output_tokens_details": SimpleNamespace(**output_details),
    }
    for name, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
        ("total_tokens", total_tokens),
    ):
        if value is not _ABSENT:
            values[name] = value
    return SimpleNamespace(**values)


def benchmark_response(**overrides: object) -> _BenchmarkResponse:
    values: dict[str, object] = {
        "id": "resp_123",
        "_request_id": "req_123",
        "status": "completed",
        "error": None,
        "output": _benchmark_output(),
        "model": "gpt-5.6-sol-2026-08-01",
        "service_tier": "default",
        "prompt_cache_options": SimpleNamespace(mode="explicit", ttl="30m"),
        "usage": benchmark_usage(),
    }
    for name, value in overrides.items():
        if value is _ABSENT:
            values.pop(name, None)
        else:
            values[name] = value
    return _BenchmarkResponse(**values)


def _stub_benchmark_parser(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: object,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    monkeypatch.setattr(
        provider_openai,
        "_parse_benchmark_response",
        lambda _response, _request: result,
        raising=False,
    )


_HUGE_INTEGER = 10**10_000


def sdk_error_type(name: str) -> type[Exception]:
    openai_error = type(
        "OpenAIError",
        (Exception,),
        {"__module__": "openai"},
    )
    api_error = type("APIError", (openai_error,), {"__module__": "openai"})
    api_status_error = type(
        "APIStatusError",
        (api_error,),
        {"__module__": "openai"},
    )
    api_connection_error = type(
        "APIConnectionError",
        (api_error,),
        {"__module__": "openai"},
    )
    if name == "OpenAIError":
        return openai_error
    if name == "APIError":
        return api_error
    if name == "APIStatusError":
        return api_status_error
    if name == "APIConnectionError":
        return api_connection_error
    if name == "APITimeoutError":
        return type(name, (api_connection_error,), {"__module__": "openai"})
    return type(name, (api_status_error,), {"__module__": "openai"})


def test_confirmatory_request_sends_exact_reasoning_verbosity_cache_and_service_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.providers.base import PublicBenchmarkRequestPolicyV1

    parsed = object()
    _stub_benchmark_parser(monkeypatch, result=parsed)
    monkeypatch.setenv("OPENAI_SERVICE_TIER", "priority")
    client = StubClient(response())
    provider = OpenAIProvider(client=client)

    assert provider.generate_benchmark(benchmark_request()) is parsed
    assert client.responses.calls == [
        {
            "model": "gpt-5.6-sol",
            "instructions": "instruction",
            "input": "prompt",
            "max_output_tokens": 1024,
            "store": False,
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "medium"},
            "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
            "service_tier": "default",
        }
    ]
    forbidden = {
        "reasoning_mode",
        "prompt_cache_key",
        "prompt_cache_retention",
        "prompt_cache_breakpoint",
        "tools",
        "previous_response_id",
        "temperature",
    }
    assert forbidden.isdisjoint(client.responses.calls[0])

    without_nested = StubClient(response())
    assert (
        OpenAIProvider(client=without_nested).generate_benchmark(
            benchmark_request(reasoning_effort=None, text_verbosity=None)
        )
        is parsed
    )
    assert without_nested.responses.calls == [
        {
            "model": "gpt-5.6-sol",
            "instructions": "instruction",
            "input": "prompt",
            "max_output_tokens": 1024,
            "store": False,
            "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
            "service_tier": "default",
        }
    ]

    for invalid_tier in (None, True, 1, object(), "auto", "flex", "priority", "ultrafast"):
        policy = PublicBenchmarkRequestPolicyV1.model_construct(
            schema_version="PublicBenchmarkRequestPolicyV1",
            reasoning_mode="omitted",
            prompt_cache_mode="explicit",
            prompt_cache_ttl="30m",
            service_tier=invalid_tier,
            input_token_bound_version="openai-utf8-envelope-v1",
            max_input_tokens=272000,
        )
        rejected_client = StubClient(response())
        with pytest.raises(ProviderError, match="service_tier") as caught:
            OpenAIProvider(client=rejected_client).generate_benchmark(
                benchmark_request(policy=policy)
            )
        assert caught.value.kind == "configuration"
        assert caught.value.delivery_certainty == "definitely_not_sent"
        assert rejected_client.responses.calls == []


@pytest.mark.parametrize("temperature", [0.0, 0.25, -0.25])
def test_nonnull_benchmark_temperature_rejects_before_responses_call(
    monkeypatch: pytest.MonkeyPatch,
    temperature: float,
) -> None:
    network_calls: list[object] = []

    def reject_network(*args: object, **kwargs: object) -> object:
        network_calls.append((args, kwargs))
        raise AssertionError("benchmark request crossed the network boundary")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    client = StubClient(response())

    with pytest.raises(ProviderError, match="temperature") as caught:
        OpenAIProvider(client=client).generate_benchmark(benchmark_request(temperature=temperature))

    assert caught.value.kind == "configuration"
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []
    assert network_calls == []


def test_benchmark_request_bytes_provider_kwargs_and_capture_projection_are_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import benchmark
    from laconian_eval.benchmark import attachments
    from laconian_eval.providers import openai as provider_openai

    assert benchmark.CanonicalJSONV1Error is attachments.CanonicalJSONV1Error
    assert benchmark.canonical_json_v1 is attachments.canonical_json_v1
    assert benchmark.parse_canonical_json_v1 is attachments.parse_canonical_json_v1
    assert provider_openai._canonical_json_v1 is attachments.canonical_json_v1

    expected_projection = {
        "model": "gpt-5.6-sol",
        "instructions": "instruction",
        "input": "prompt",
        "max_output_tokens": 1024,
        "store": False,
        "reasoning": {"effort": "medium"},
        "text": {"verbosity": "medium"},
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "service_tier": "default",
    }
    expected_bytes = (
        b'{"input":"prompt","instructions":"instruction","max_output_tokens":1024,'
        b'"model":"gpt-5.6-sol","prompt_cache_options":{"mode":"explicit","ttl":"30m"},'
        b'"reasoning":{"effort":"medium"},"service_tier":"default","store":false,'
        b'"text":{"verbosity":"medium"}}'
    )
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()
    assert benchmark.canonical_json_v1(expected_projection) == expected_bytes

    original_builder = provider_openai._public_benchmark_responses_kwargs
    original_canonicalizer = provider_openai._canonical_json_v1
    original_sha256 = hashlib.sha256
    builder_results: list[dict[str, object]] = []
    canonicalized: list[object] = []
    hashed: list[bytes] = []

    def capture_builder(value: object) -> dict[str, object]:
        result = original_builder(value)  # type: ignore[arg-type]
        builder_results.append(result)
        return result

    def capture_canonical(value: object) -> bytes:
        canonicalized.append(value)
        return original_canonicalizer(value)

    def capture_sha256(data: bytes = b"") -> Any:
        hashed.append(data)
        return original_sha256(data)

    monkeypatch.setattr(provider_openai, "_public_benchmark_responses_kwargs", capture_builder)
    monkeypatch.setattr(provider_openai, "_canonical_json_v1", capture_canonical)
    monkeypatch.setattr(provider_openai.hashlib, "sha256", capture_sha256)
    parsed = object()
    _stub_benchmark_parser(monkeypatch, result=parsed)
    client = StubClient(response())

    assert OpenAIProvider(client=client).generate_benchmark(benchmark_request()) is parsed

    assert len(builder_results) == 1
    assert tuple(builder_results[0]) == (
        "model",
        "instructions",
        "input",
        "max_output_tokens",
        "store",
        "reasoning",
        "text",
        "prompt_cache_options",
        "service_tier",
    )
    assert builder_results[0] == expected_projection
    assert canonicalized == [builder_results[0]]
    assert canonicalized[0] is builder_results[0]
    assert hashed == [expected_bytes]
    assert original_sha256(hashed[0]).hexdigest() == expected_sha256
    assert client.responses.calls == [expected_projection]


def test_recursive_cache_control_helper_rejects_synthetic_trees_without_widening_request_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    from laconian_eval.providers import openai as provider_openai
    from laconian_eval.providers.base import PublicBenchmarkRequestV1

    forbidden_keys = (
        "prompt_cache_breakpoint",
        "prompt_cache_key",
        "prompt_cache_retention",
        "prompt_cache_options",
        "prompt_cache_unknown",
    )
    for key in forbidden_keys:
        for tree in (
            {key: None},
            {"outer": [{key: None}]},
            {"outer": ({"middle": ({key: None},)},)},
        ):
            with pytest.raises(ProviderError, match="prompt_cache_") as caught:
                provider_openai._assert_no_public_benchmark_cache_control(tree)
            assert caught.value.kind == "configuration"
            assert caught.value.delivery_certainty == "definitely_not_sent"

    for tree in ({1: "value"}, {_StrSubclass("safe"): "value"}):
        with pytest.raises(ProviderError, match="mapping key"):
            provider_openai._assert_no_public_benchmark_cache_control(tree)

    provider_openai._assert_no_public_benchmark_cache_control("instruction")
    provider_openai._assert_no_public_benchmark_cache_control("prompt")

    annotations = typing.get_type_hints(PublicBenchmarkRequestV1)
    assert annotations["instructions"] == (str | None)
    assert annotations["prompt"] is str
    checked = benchmark_request()
    assert type(checked.instructions) is str
    assert type(checked.prompt) is str

    parsed = object()
    _stub_benchmark_parser(monkeypatch, result=parsed)
    client = StubClient(response())
    synthetic_request = benchmark_request()
    object.__setattr__(synthetic_request, "prompt", {"safe": "value"})
    with pytest.raises(ProviderError, match="prompt"):
        OpenAIProvider(client=client).generate_benchmark(synthetic_request)
    assert client.responses.calls == []

    provider_openai._assert_no_public_benchmark_cache_control(
        types.MappingProxyType({"safe": ["leaf", ("leaf",)]})
    )


def test_standard_tier_bound_rejects_before_client_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.providers.base import (
        OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE,
        OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS,
        conservative_input_token_bound,
    )

    assert conservative_input_token_bound(instruction_utf8_bytes=2, prompt_utf8_bytes=1) == (
        OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE + 3
    )
    assert len("é".encode()) == 2
    exact_payload_bytes = (
        OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS - OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE
    )
    exact = benchmark_request(instructions=None, prompt="a" * exact_payload_bytes)
    over = benchmark_request(instructions=None, prompt="a" * (exact_payload_bytes + 1))
    parsed = object()
    _stub_benchmark_parser(monkeypatch, result=parsed)

    accepted_client = StubClient(response())
    assert OpenAIProvider(client=accepted_client).generate_benchmark(exact) is parsed
    assert len(accepted_client.responses.calls) == 1

    rejected_client = StubClient(response())
    with pytest.raises(ProviderError, match="272000") as caught:
        OpenAIProvider(client=rejected_client).generate_benchmark(over)
    assert caught.value.kind == "configuration"
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert rejected_client.responses.calls == []

    for invalid in (True, -1):
        with pytest.raises(ValueError, match="nonnegative"):
            conservative_input_token_bound(
                instruction_utf8_bytes=invalid,  # type: ignore[arg-type]
                prompt_utf8_bytes=0,
            )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("case_id", _StrSubclass("case-en"), "case_id"),
        ("arm", _StrSubclass("if"), "arm"),
        ("arm", "unknown", "arm"),
        ("repetition", True, "repetition"),
        ("repetition", -1, "repetition"),
        ("requested_model_id", _StrSubclass("gpt-5.6-sol"), "requested_model_id"),
        ("requested_model_id", "gpt-5.6-unknown", "requested_model_id"),
        ("instructions", _StrSubclass("instruction"), "instructions"),
        ("instructions", "\ud800", "UTF-8"),
        ("prompt", _StrSubclass("prompt"), "prompt"),
        ("prompt", "e\u0301", "canonical"),
        ("prompt", "\ud800", "UTF-8"),
        ("max_output_tokens", True, "max_output_tokens"),
        ("max_output_tokens", 0, "max_output_tokens"),
        ("reasoning_effort", _StrSubclass("medium"), "reasoning_effort"),
        ("reasoning_effort", "extreme", "reasoning_effort"),
        ("text_verbosity", _StrSubclass("medium"), "text_verbosity"),
        ("text_verbosity", "extreme", "text_verbosity"),
        ("timeout_seconds", True, "timeout_seconds"),
        ("timeout_seconds", 30.0, "does not match"),
    ],
)
def test_benchmark_request_validation_is_exact_and_preclient(
    field: str,
    value: object,
    message: str,
) -> None:
    client = StubClient(benchmark_response())
    candidate = benchmark_request()
    object.__setattr__(candidate, field, value)

    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=client).generate_benchmark(candidate)

    assert caught.value.kind == "configuration"
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", _StrSubclass("PublicBenchmarkRequestPolicyV1")),
        ("reasoning_mode", _StrSubclass("omitted")),
        ("reasoning_mode", "explicit"),
        ("prompt_cache_mode", _StrSubclass("explicit")),
        ("prompt_cache_mode", "auto"),
        ("prompt_cache_ttl", _StrSubclass("30m")),
        ("prompt_cache_ttl", "1h"),
        ("input_token_bound_version", _StrSubclass("openai-utf8-envelope-v1")),
        ("input_token_bound_version", "unknown"),
        ("max_input_tokens", True),
        ("max_input_tokens", 271999),
    ],
)
def test_benchmark_policy_validation_is_exact_and_preclient(field: str, value: object) -> None:
    from laconian_eval.providers.base import PublicBenchmarkRequestPolicyV1

    policy_values: dict[str, object] = {
        "schema_version": "PublicBenchmarkRequestPolicyV1",
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
        "input_token_bound_version": "openai-utf8-envelope-v1",
        "max_input_tokens": 272000,
    }
    policy_values[field] = value
    policy = PublicBenchmarkRequestPolicyV1.model_construct(**policy_values)
    client = StubClient(benchmark_response())

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=client).generate_benchmark(benchmark_request(policy=policy))

    assert caught.value.kind == "configuration"
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []


_BENCHMARK_RAW_RESPONSE_PATHS = (
    "response.id",
    "response.status",
    "response.error",
    "response.output",
    "response.model",
    "response.service_tier",
    "response.prompt_cache_options.mode",
    "response.prompt_cache_options.ttl",
    "response.usage.input_tokens",
    "response.usage.input_tokens_details.cached_tokens",
    "response.usage.input_tokens_details.cache_write_tokens",
    "response.usage.output_tokens",
    "response.usage.output_tokens_details.reasoning_tokens",
    "response.usage.total_tokens",
)


def test_openai_benchmark_response_binds_exact_raw_source_output_and_accounting() -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkResponseEvidenceV1,
        public_benchmark_raw_response_sha256,
    )

    result = OpenAIProvider(client=StubClient(benchmark_response())).generate_benchmark(
        benchmark_request()
    )

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert tuple(type(result).model_fields) == (
        "schema_version",
        "response_id",
        "raw_response_sha256",
        "output_text",
        "raw_response_source",
        "usage",
        "requested_model_id",
        "returned_model_id",
        "returned_model_source_sha256",
        "requested_service_tier",
        "returned_service_tier",
        "service_tier_status",
        "service_tier_source_sha256",
        "applied_prompt_cache_mode",
        "applied_prompt_cache_ttl",
        "applied_cache_control_status",
        "applied_cache_control_source_sha256",
        "cache_read_source_sha256",
        "cache_write_source_sha256",
        "usage_source_sha256",
        "reasoning_tokens_source_sha256",
    )
    assert result.response_id == "resp_123"
    assert result.output_text == "Complete answer."
    assert result.requested_model_id == "gpt-5.6-sol"
    assert result.returned_model_id == "gpt-5.6-sol-2026-08-01"
    assert result.requested_service_tier == "default"
    assert result.returned_service_tier == "default"
    assert result.service_tier_status == "reported_default"
    assert result.applied_prompt_cache_mode == "explicit"
    assert result.applied_prompt_cache_ttl == "30m"
    assert result.applied_cache_control_status == "reported_exact"
    assert result.usage.model_dump(mode="json") == {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "cache_read_tokens": 2,
        "cache_write_tokens": 0,
        "ordinary_uncached_input_tokens": 8,
        "reasoning_tokens": 1,
        "availability": "complete",
        "source": "provider",
        "cache_read_status": "reported_nonzero",
        "cache_write_status": "reported_zero",
        "reasoning_token_accounting": "reported",
    }
    source = result.raw_response_source
    assert tuple(entry.path for entry in source.entries) == _BENCHMARK_RAW_RESPONSE_PATHS
    assert tuple(entry.present for entry in source.entries) == (True,) * 14
    assert tuple(entry.value for entry in source.entries) == (
        "resp_123",
        "completed",
        None,
        [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Complete answer."}],
            }
        ],
        "gpt-5.6-sol-2026-08-01",
        "default",
        "explicit",
        "30m",
        10,
        2,
        0,
        4,
        1,
        14,
    )
    assert result.raw_response_sha256 == public_benchmark_raw_response_sha256(source)
    assert not hasattr(result, "output_text_source_sha256")
    assert (
        result.returned_model_source_sha256
        == result.service_tier_source_sha256
        == result.applied_cache_control_source_sha256
        == result.cache_read_source_sha256
        == result.cache_write_source_sha256
        == result.usage_source_sha256
        == result.reasoning_tokens_source_sha256
        == result.raw_response_sha256
    )


def test_generate_benchmark_has_the_attempts_owned_outcome_annotation() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderOutcomeV1
    from laconian_eval.providers.base import PublicBenchmarkRequestV1

    annotations = typing.get_type_hints(OpenAIProvider.generate_benchmark)

    assert annotations["request"] is PublicBenchmarkRequestV1
    assert annotations["return"] is PublicBenchmarkProviderOutcomeV1


def test_openai_structured_output_serializer_emits_exact_nine_key_wire_and_hash() -> None:
    from laconian_eval.benchmark import canonical_json_v1
    from laconian_eval.providers.base import StructuredOutputProviderRequestV1
    from laconian_eval.providers.openai import _structured_output_responses_kwargs

    request = StructuredOutputProviderRequestV1(
        model="gpt-5.6-sol",
        rendered_input="sdk-contract-structured-input-v1",
        reasoning_effort="low",
        text_verbosity="low",
        structured_output_name="sdk_contract_probe_v1",
        structured_output_schema_canonical_json=(
            b'{"additionalProperties":false,"properties":{"value":{"type":"string"}},'
            b'"required":["value"],"type":"object"}'
        ),
        max_output_tokens=768,
        store=False,
        tools=(),
        service_tier="default",
        prompt_cache_mode="explicit",
        prompt_cache_ttl="30m",
    )

    wire = _structured_output_responses_kwargs(request)

    assert tuple(wire) == (
        "model",
        "input",
        "reasoning",
        "text",
        "max_output_tokens",
        "store",
        "tools",
        "service_tier",
        "prompt_cache_options",
    )
    assert "instructions" not in wire
    assert hashlib.sha256(canonical_json_v1(wire)).hexdigest() == (
        "6de8042f2e010f4e7128abe836374b60fa6b4f0c1818935ff1ab5095db148ab0"
    )


def test_structured_output_request_is_frozen_neutral_exact_and_rejects_instructions_or_extras(
) -> None:
    from laconian_eval.providers.base import StructuredOutputProviderRequestV1
    from laconian_eval.providers.openai import _structured_output_responses_kwargs

    values: dict[str, object] = {
        "model": "gpt-5.6-sol",
        "rendered_input": "judge input",
        "reasoning_effort": "low",
        "text_verbosity": "low",
        "structured_output_name": "laconian_structured_judgment_v1",
        "structured_output_schema_canonical_json": (
            b'{"additionalProperties":false,"properties":{},"required":[],"type":"object"}'
        ),
        "max_output_tokens": 768,
        "store": False,
        "tools": (),
        "service_tier": "default",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
    }
    request = StructuredOutputProviderRequestV1(**values)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        request.model = "gpt-5.6-terra"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        StructuredOutputProviderRequestV1(  # type: ignore[call-arg]
            **values,
            instructions="forbidden",
        )
    for false_like in (0, 0.0):
        with pytest.raises(ValidationError):
            StructuredOutputProviderRequestV1(  # type: ignore[arg-type]
                **(values | {"store": false_like})
            )

    forged = StructuredOutputProviderRequestV1.model_construct(
        **(
            values
            | {
                "max_output_tokens": True,
                "store": True,
                "service_tier": "priority",
            }
        )
    )
    with pytest.raises(ProviderError) as caught:
        _structured_output_responses_kwargs(forged)
    assert caught.value.kind == "configuration"
    assert caught.value.delivery_certainty == "definitely_not_sent"

    client = StubClient(benchmark_response())
    with pytest.raises(ProviderError):
        OpenAIProvider(client=client).generate_structured_output(forged)
    assert client.responses.calls == []


def test_openai_structured_output_dispatch_reuses_attempts_owned_response_and_error_evidence(
) -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        PublicBenchmarkResponseEvidenceV1,
    )
    from laconian_eval.providers.base import StructuredOutputProviderRequestV1

    request = StructuredOutputProviderRequestV1(
        model="gpt-5.6-sol",
        rendered_input="judge input",
        reasoning_effort="low",
        text_verbosity="low",
        structured_output_name="laconian_structured_judgment_v1",
        structured_output_schema_canonical_json=(
            b'{"additionalProperties":false,"properties":{},"required":[],"type":"object"}'
        ),
        max_output_tokens=768,
        store=False,
        tools=(),
        service_tier="default",
        prompt_cache_mode="explicit",
        prompt_cache_ttl="30m",
    )

    result = OpenAIProvider(client=StubClient(benchmark_response())).generate_structured_output(
        request
    )

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."

    error = sdk_error_type("RateLimitError")("rate limited")
    error.status_code = 429  # type: ignore[attr-defined]
    error.request_id = "req-structured"  # type: ignore[attr-defined]
    failure = OpenAIProvider(client=StubClient(error)).generate_structured_output(request)

    assert type(failure) is PublicBenchmarkProviderErrorEvidenceV1
    assert failure.requested_model_id == "gpt-5.6-sol"
    assert failure.requested_service_tier == "default"
    assert failure.structured_status == 429
    assert failure.delivery_certainty == "definitely_rejected"
    assert failure.provider_request_id == "req-structured"


def test_sdk_contract_requires_typed_tools_text_format_members_and_structured_serializer_probe(
    monkeypatch: pytest.MonkeyPatch,
    precredential_guard: None,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    assert provider_openai.BENCHMARK_OPENAI_STRUCTURED_REQUEST_PATHS_V1 == (
        "request.tools",
        "request.text",
        "request.text.verbosity",
        "request.text.format",
        "request.text.format.type",
        "request.text.format.name",
        "request.text.format.strict",
        "request.text.format.schema",
    )
    assert provider_openai.BENCHMARK_OPENAI_STRUCTURED_SERIALIZER_PROJECTION_SHA256_V1 == (
        "6de8042f2e010f4e7128abe836374b60fa6b4f0c1818935ff1ab5095db148ab0"
    )

    lock = Path("uv.lock").read_bytes()
    lock_digest = hashlib.sha256(lock).hexdigest()

    def require_contract(candidate: bytes = lock) -> None:
        provider_openai.require_benchmark_sdk_contract(
            c0_uv_lock_bytes=candidate,
            expected_c0_uv_lock_sha256=hashlib.sha256(candidate).hexdigest(),
        )

    def lock_member(name: str) -> tuple[int, int, bytes]:
        marker = f'[[package]]\nname = "{name}"'.encode()
        start = lock.index(marker)
        end = lock.find(b"\n[[package]]", start + len(marker))
        if end < 0:
            end = len(lock)
        return start, end, lock[start:end]

    expected_versions = {
        "pydantic": provider_openai.BENCHMARK_PYDANTIC_VERSION_V1,
        "pydantic-core": provider_openai.BENCHMARK_PYDANTIC_CORE_VERSION_V1,
    }
    real_installed_distribution_version = provider_openai._installed_distribution_version
    for distribution, expected_version in expected_versions.items():
        for installed_value in (
            f"{expected_version}-mismatch",
            (expected_version, expected_version),
        ):
            with monkeypatch.context() as case_patch:

                def installed_version(
                    name: str,
                    *,
                    target: str = distribution,
                    value: object = installed_value,
                ) -> object:
                    if name == target:
                        return value
                    return real_installed_distribution_version(name)

                case_patch.setattr(
                    provider_openai,
                    "_installed_distribution_version",
                    installed_version,
                )
                with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
                    require_contract()
                _assert_sdk_error(caught.value, "installed-version")

        start, end, member = lock_member(distribution)
        version_line = f'version = "{expected_version}"'.encode()
        assert member.count(version_line) == 1
        locked_mismatch = (
            lock[:start]
            + member.replace(
                version_line,
                f'version = "{expected_version}-mismatch"'.encode(),
                1,
            )
            + lock[end:]
        )
        locked_duplicate = lock[:end] + b"\n" + member + lock[end:]
        for candidate in (locked_mismatch, locked_duplicate):
            with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
                require_contract(candidate)
            _assert_sdk_error(caught.value, "lock-entry")

    original_hints = provider_openai._sdk_type_hints
    original_structured_verifier = provider_openai._verify_structured_request_type_paths
    request_member_names = (
        "ResponseCreateParamsNonStreaming",
        "ResponseCreateParamsStreaming",
    )
    for member_name in request_member_names:
        for path in provider_openai.BENCHMARK_OPENAI_STRUCTURED_REQUEST_PATHS_V1:
            mutation_target: list[tuple[object, str] | None] = [None]
            mutation_applied: list[str] = []

            def hints_with_one_missing_path(
                owner: type[object],
                *,
                target_ref: list[tuple[object, str] | None] = mutation_target,
                applied: list[str] = mutation_applied,
                target_path: str = path,
            ) -> dict[str, object]:
                hints = dict(original_hints(owner))
                target = target_ref[0]
                if target is not None and owner is target[0]:
                    applied.append(target_path)
                    hints.pop(target[1])
                return hints

            def verify_with_one_missing_path(
                root: object,
                *,
                target_member: str = member_name,
                target_path: str = path,
                target_ref: list[tuple[object, str] | None] = mutation_target,
            ) -> bool:
                if getattr(root, "__qualname__", None) != target_member:
                    return original_structured_verifier(root)
                root_hints = original_hints(root)  # type: ignore[arg-type]
                text_owner = root_hints["text"]
                text_hints = original_hints(text_owner)  # type: ignore[arg-type]
                format_owner = provider_openai._json_schema_format_branch(text_hints["format"])
                owner_and_field = {
                    "request.tools": (root, "tools"),
                    "request.text": (root, "text"),
                    "request.text.verbosity": (text_owner, "verbosity"),
                    "request.text.format": (text_owner, "format"),
                    "request.text.format.type": (format_owner, "type"),
                    "request.text.format.name": (format_owner, "name"),
                    "request.text.format.strict": (format_owner, "strict"),
                    "request.text.format.schema": (format_owner, "schema"),
                }
                target_ref[0] = owner_and_field[target_path]
                try:
                    return original_structured_verifier(root)
                finally:
                    target_ref[0] = None

            with monkeypatch.context() as case_patch:
                case_patch.setattr(provider_openai, "_sdk_type_hints", hints_with_one_missing_path)
                case_patch.setattr(
                    provider_openai,
                    "_verify_structured_request_type_paths",
                    verify_with_one_missing_path,
                )
                with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
                    provider_openai.require_benchmark_sdk_contract(
                        c0_uv_lock_bytes=lock,
                        expected_c0_uv_lock_sha256=lock_digest,
                    )
                _assert_sdk_error(caught.value, "request-model")
            if not mutation_applied or set(mutation_applied) != {path}:
                raise RuntimeError(
                    f"unexpected structured path visits: {member_name=} {path=} "
                    f"{mutation_applied=}"
                )

    for member_index in range(9):
        with monkeypatch.context() as case_patch:
            original_structured_builder = provider_openai._structured_output_responses_kwargs

            def changed_member(
                request: object,
                *,
                index: int = member_index,
                builder: Any = original_structured_builder,
            ) -> dict[str, object]:
                projection = builder(request)
                items = list(projection.items())
                key, _value = items[index]
                items[index] = (key, None)
                return dict(items)

            case_patch.setattr(
                provider_openai,
                "_structured_output_responses_kwargs",
                changed_member,
            )
            with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
                require_contract()
            _assert_sdk_error(caught.value, "serializer-projection")

    with monkeypatch.context() as case_patch:
        original_structured_builder = provider_openai._structured_output_responses_kwargs

        def changed_order(request: object) -> dict[str, object]:
            items = list(original_structured_builder(request).items())  # type: ignore[arg-type]
            items[0], items[1] = items[1], items[0]
            return dict(items)

        case_patch.setattr(
            provider_openai,
            "_structured_output_responses_kwargs",
            changed_order,
        )
        with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
            require_contract()
        _assert_sdk_error(caught.value, "serializer-projection")

    with monkeypatch.context() as case_patch:
        case_patch.setattr(
            provider_openai,
            "BENCHMARK_OPENAI_STRUCTURED_SERIALIZER_PROJECTION_SHA256_V1",
            "0" * 64,
        )
        with pytest.raises(provider_openai.BenchmarkSDKContractError) as caught:
            require_contract()
        _assert_sdk_error(caught.value, "serializer-projection")


def test_structured_format_union_rejects_untyped_missing_or_overlapping_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.providers import openai as provider_openai

    class GoodJSONSchema(typing.TypedDict):
        type: typing.Literal["json_schema"]
        name: str
        strict: bool
        schema: dict[str, object]

    class BroadFormat(typing.TypedDict):
        type: Any

    class MissingDiscriminator(typing.TypedDict):
        value: str

    class OverlappingFormat(typing.TypedDict):
        type: typing.Literal["json_schema", "vendor_json_schema"]

    monkeypatch.setattr(provider_openai, "_sdk_type_hints", typing.get_type_hints)

    for unsafe_sibling in (BroadFormat, MissingDiscriminator, OverlappingFormat):
        annotation = GoodJSONSchema | unsafe_sibling
        with pytest.raises(TypeError):
            provider_openai._json_schema_format_branch(annotation)


def test_openai_benchmark_ignores_every_alternate_accounting_and_model_path() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    raw_usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        input_tokens_details=SimpleNamespace(
            cached_input_tokens=2,
            cache_write_input_tokens=1,
        ),
        output_tokens_details=SimpleNamespace(reasoning_output_tokens=1),
        cached_tokens=2,
        cache_write_tokens=1,
        reasoning_tokens=1,
    )
    response_object = benchmark_response(
        model=_ABSENT,
        service_tier=_ABSENT,
        prompt_cache_options=_ABSENT,
        usage=raw_usage,
    )
    response_object.response_model = "gpt-5.6-sol-alternate"
    response_object.tier = "default"
    response_object.applied_prompt_cache_options = SimpleNamespace(
        mode="explicit",
        ttl="30m",
    )

    result = OpenAIProvider(client=StubClient(response_object)).generate_benchmark(
        benchmark_request()
    )

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.returned_model_id is None
    assert result.returned_service_tier is None
    assert result.service_tier_status == "missing"
    assert result.applied_prompt_cache_mode is None
    assert result.applied_prompt_cache_ttl is None
    assert result.applied_cache_control_status == "missing"
    assert result.usage.cache_read_tokens is None
    assert result.usage.cache_read_status == "missing"
    assert result.usage.cache_write_tokens is None
    assert result.usage.cache_write_status == "missing"
    assert result.usage.reasoning_tokens is None
    assert result.usage.reasoning_token_accounting == "not_reported"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 14


@pytest.mark.parametrize(
    (
        "cached_tokens",
        "cache_write_tokens",
        "expected_read",
        "expected_read_status",
        "expected_write",
        "expected_write_status",
        "ordinary_uncached",
    ),
    [
        (0, 0, 0, "reported_zero", 0, "reported_zero", 10),
        (2, 0, 2, "reported_nonzero", 0, "reported_zero", 8),
        (0, 2, 0, "reported_zero", 2, "reported_nonzero", 8),
        (2, 3, 2, "reported_nonzero", 3, "reported_nonzero", 5),
        (_ABSENT, 0, None, "missing", 0, "reported_zero", 10),
        (2, _ABSENT, 2, "reported_nonzero", None, "missing", 8),
        (True, 0, None, "invalid", 0, "reported_zero", 10),
        (-1, 0, None, "invalid", 0, "reported_zero", 10),
        (11, 0, None, "invalid", 0, "reported_zero", 10),
        (2, True, 2, "reported_nonzero", None, "invalid", 8),
        (2, -1, 2, "reported_nonzero", None, "invalid", 8),
        (2, 11, 2, "reported_nonzero", None, "invalid", 8),
        (8, 3, None, "invalid", None, "invalid", 10),
    ],
)
def test_openai_cache_read_and_cache_write_tokens_degrade_independently(
    cached_tokens: object,
    cache_write_tokens: object,
    expected_read: int | None,
    expected_read_status: str,
    expected_write: int | None,
    expected_write_status: str,
    ordinary_uncached: int,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    raw_usage = benchmark_usage(
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    result = OpenAIProvider(
        client=StubClient(benchmark_response(usage=raw_usage))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."
    assert result.usage.cache_read_tokens == expected_read
    assert result.usage.cache_read_status == expected_read_status
    assert result.usage.cache_write_tokens == expected_write
    assert result.usage.cache_write_status == expected_write_status
    assert result.usage.ordinary_uncached_input_tokens == ordinary_uncached
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 14
    assert result.usage.reasoning_tokens == 1
    assert result.usage.reasoning_token_accounting == "reported"
    assert result.response_id == "resp_123"
    assert result.requested_model_id == "gpt-5.6-sol"
    assert result.returned_model_id == "gpt-5.6-sol-2026-08-01"
    assert result.requested_service_tier == "default"
    assert result.returned_service_tier == "default"
    assert result.service_tier_status == "reported_default"
    assert result.applied_prompt_cache_mode == "explicit"
    assert result.applied_prompt_cache_ttl == "30m"
    assert result.applied_cache_control_status == "reported_exact"


@pytest.mark.parametrize(
    ("raw_reasoning", "expected_count", "expected_accounting"),
    [
        (7, 7, "reported"),
        (0, 0, "reported"),
        (_ABSENT, None, "not_reported"),
        (None, None, "not_reported"),
        (-1, None, "invalid"),
        (True, None, "invalid"),
        (11, None, "invalid"),
    ],
)
def test_openai_reasoning_tokens_preserve_valid_response_evidence(
    raw_reasoning: object,
    expected_count: int | None,
    expected_accounting: str,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    result = OpenAIProvider(
        client=StubClient(
            benchmark_response(
                usage=benchmark_usage(
                    output_tokens=10,
                    reasoning_tokens=raw_reasoning,
                    total_tokens=20,
                )
            )
        )
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."
    assert result.usage.output_tokens == 10
    assert result.usage.total_tokens == 20
    assert result.usage.reasoning_tokens == expected_count
    assert result.usage.reasoning_token_accounting == expected_accounting
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cache_write_tokens == 0


@pytest.mark.parametrize(
    ("raw_tier", "expected_tier", "expected_status"),
    [
        ("default", "default", "reported_default"),
        ("priority", "priority", "mismatch"),
        (_ABSENT, None, "missing"),
        (None, None, "missing"),
        ("", None, "missing"),
        (True, None, "missing"),
        (_sdk_node(unexpected="tree"), None, "missing"),
        ("x" * 1025, None, "missing"),
    ],
)
def test_openai_returned_service_tier_is_preserved_and_classified(
    raw_tier: object,
    expected_tier: str | None,
    expected_status: str,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    result = OpenAIProvider(
        client=StubClient(benchmark_response(service_tier=raw_tier))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."
    assert result.requested_service_tier == "default"
    assert result.returned_service_tier == expected_tier
    assert result.service_tier_status == expected_status
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cache_write_tokens == 0


@pytest.mark.parametrize(
    ("mode", "ttl", "expected_mode", "expected_ttl", "expected_status"),
    [
        ("explicit", "30m", "explicit", "30m", "reported_exact"),
        ("auto", "30m", "auto", "30m", "mismatch"),
        ("explicit", "1h", "explicit", "1h", "mismatch"),
        (_ABSENT, "30m", None, "30m", "missing"),
        ("explicit", _ABSENT, "explicit", None, "missing"),
        (None, None, None, None, "missing"),
        (True, "30m", None, "30m", "invalid"),
        ("explicit", _sdk_node(value="bad"), "explicit", None, "invalid"),
        ("", "30m", None, "30m", "invalid"),
    ],
)
def test_openai_applied_cache_policy_is_derived_from_exact_paths(
    mode: object,
    ttl: object,
    expected_mode: str | None,
    expected_ttl: str | None,
    expected_status: str,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    options: dict[str, object] = {}
    if mode is not _ABSENT:
        options["mode"] = mode
    if ttl is not _ABSENT:
        options["ttl"] = ttl
    result = OpenAIProvider(
        client=StubClient(benchmark_response(prompt_cache_options=SimpleNamespace(**options)))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."
    assert result.applied_prompt_cache_mode == expected_mode
    assert result.applied_prompt_cache_ttl == expected_ttl
    assert result.applied_cache_control_status == expected_status
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cache_write_tokens == 0


def test_openai_committed_output_uses_ordered_response_output_only() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    output = [
        _sdk_node(
            type="message",
            content=[
                _sdk_node(type="output_text", text="A"),
                _sdk_node(type="refusal", refusal="ignored"),
                _sdk_node(type="output_text", text="B"),
            ],
        ),
        _sdk_node(type="computer_call", id="ignored"),
        _sdk_node(
            type="message",
            content=[
                _sdk_node(type="input_text", text="ignored"),
                _sdk_node(type="output_text", text="C"),
            ],
        ),
    ]
    result = OpenAIProvider(
        client=StubClient(benchmark_response(output=output))
    ).generate_benchmark(benchmark_request())
    reordered = OpenAIProvider(
        client=StubClient(benchmark_response(output=list(reversed(output))))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert type(reordered) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "ABC"
    assert reordered.output_text == "CAB"
    assert result.raw_response_source.entries[3].value == [
        item.model_dump(mode="json") for item in output
    ]


@pytest.mark.parametrize(
    "bad_output",
    [
        _ABSENT,
        None,
        b"bytes",
        True,
        object(),
        [],
        [_sdk_node(content=[_sdk_node(type="output_text", text="missing message discriminator")])],
        [_sdk_node(type="message", content=[])],
        [_sdk_node(type=_StrSubclass("message"), content=_benchmark_output())],
        [_sdk_node(type="message")],
        [_sdk_node(type="message", content=b"bad")],
        [_sdk_node(type="message", content=[_sdk_node(text="bad")])],
        [_sdk_node(type="message", content=[_sdk_node(type="output_text")])],
        [_sdk_node(type="message", content=[_sdk_node(type="output_text", text=b"bad")])],
        [
            _sdk_node(
                type="message",
                content=[_sdk_node(type="output_text", text=_StrSubclass("bad"))],
            )
        ],
        [_sdk_node(type="message", content=[_sdk_node(type="output_text", text=" \n\t")])],
    ],
)
def test_openai_malformed_or_blank_committed_output_returns_output_free_error(
    bad_output: object,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1

    result = OpenAIProvider(
        client=StubClient(benchmark_response(output=bad_output))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == "response_received"
    assert not hasattr(result, "output_text")


@pytest.mark.parametrize(
    "bad_text",
    (b"bad", _StrSubclass("bad")),
)
def test_openai_nonfaithful_output_projection_becomes_projection_failure(
    bad_text: object,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1

    result = OpenAIProvider(
        client=StubClient(benchmark_response(output=_benchmark_output(bad_text)))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == "response_received"
    assert result.raw_response_source is None
    assert result.raw_response_sha256 is None
    assert result.response_id is None
    assert result.returned_model_id is None
    assert result.returned_service_tier is None
    assert result.usage.availability == "unavailable"
    assert not hasattr(result, "output_text")


def test_openai_completed_output_accepts_absent_error_member() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkResponseEvidenceV1

    result = OpenAIProvider(
        client=StubClient(benchmark_response(error=_ABSENT))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkResponseEvidenceV1
    assert result.output_text == "Complete answer."


def test_openai_missing_response_id_preserves_source_tier_and_usage_error_evidence() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1

    result = OpenAIProvider(
        client=StubClient(benchmark_response(id=_ABSENT, service_tier="priority"))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.response_id is None
    assert result.raw_response_source is not None
    assert result.returned_service_tier == "priority"
    assert result.service_tier_status == "mismatch"
    assert result.usage.availability == "complete"


def test_openai_output_bound_and_ephemeral_exact_text_are_enforced() -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        PublicBenchmarkResponseEvidenceV1,
    )
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

    accepted_text = "A\x00e\u0301"
    accepted = OpenAIProvider(
        client=StubClient(benchmark_response(output=_benchmark_output(accepted_text)))
    ).generate_benchmark(benchmark_request())
    over_limit = "x" * (RESOURCE_LIMITS_V1.output_utf8_bytes + 1)
    rejected = OpenAIProvider(
        client=StubClient(benchmark_response(output=_benchmark_output(over_limit)))
    ).generate_benchmark(benchmark_request())

    assert type(accepted) is PublicBenchmarkResponseEvidenceV1
    assert accepted.output_text == accepted_text
    assert type(rejected) is PublicBenchmarkProviderErrorEvidenceV1
    assert not hasattr(rejected, "output_text")


def test_raw_response_source_projection_distinguishes_missing_null_and_sdk_models() -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkResponseEvidenceV1,
        public_benchmark_raw_response_sha256,
    )

    error_model = _sdk_node(code="synthetic", message="bound")
    response_object = benchmark_response(error=error_model, service_tier=_ABSENT)
    response_object.status = "failed"
    result = OpenAIProvider(client=StubClient(response_object)).generate_benchmark(
        benchmark_request()
    )

    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert type(result) is not PublicBenchmarkResponseEvidenceV1
    assert result.raw_response_source is not None
    entries = result.raw_response_source.entries
    assert entries[2].present is True
    assert entries[2].value == {"code": "synthetic", "message": "bound"}
    assert entries[5].present is False
    assert entries[5].value is None
    assert result.raw_response_sha256 == public_benchmark_raw_response_sha256(
        result.raw_response_source
    )


def test_unrepresentable_raw_response_projection_returns_closed_error_evidence() -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        public_benchmark_provider_error_source_sha256,
    )

    result = OpenAIProvider(
        client=StubClient(benchmark_response(service_tier=object()))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == "response_received"
    assert result.response_id is None
    assert result.raw_response_source is None
    assert result.raw_response_sha256 is None
    assert result.returned_model_id is None
    assert result.returned_service_tier is None
    assert result.service_tier_status == "missing"
    assert result.applied_prompt_cache_mode is None
    assert result.applied_prompt_cache_ttl is None
    assert result.applied_cache_control_status == "invalid"
    assert result.usage.availability == "unavailable"
    assert result.usage.cache_read_status == "invalid"
    assert result.usage.cache_write_status == "invalid"
    assert result.usage.reasoning_token_accounting == "invalid"
    assert result.error_source_sha256 == public_benchmark_provider_error_source_sha256(result)
    assert (
        result.returned_model_source_sha256
        == result.service_tier_source_sha256
        == result.applied_cache_control_source_sha256
        == result.cache_read_source_sha256
        == result.cache_write_source_sha256
        == result.usage_source_sha256
        == result.reasoning_tokens_source_sha256
        == result.error_source_sha256
    )


@pytest.mark.parametrize(
    "failure_kind",
    [
        "unsupported",
        "nonfinite",
        "nonstring-key",
        "cycle",
        "model-dump",
        "too-deep",
        "over-bound",
    ],
)
def test_raw_response_projection_failures_never_retain_partial_source_or_output(
    failure_kind: str,
) -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

    if failure_kind == "unsupported":
        bad_value: object = object()
    elif failure_kind == "nonfinite":
        bad_value = float("nan")
    elif failure_kind == "nonstring-key":
        bad_value = {1: "not canonical"}
    elif failure_kind == "cycle":
        cycle: list[object] = []
        cycle.append(cycle)
        bad_value = cycle
    elif failure_kind == "model-dump":
        bad_value = _sdk_node(value=object())
    elif failure_kind == "too-deep":
        nested: object = "leaf"
        for _ in range(RESOURCE_LIMITS_V1.nesting_depth + 2):
            nested = [nested]
        bad_value = nested
    else:
        bad_value = "x" * (RESOURCE_LIMITS_V1.raw_jsonl_row_bytes + 1)

    result = OpenAIProvider(
        client=StubClient(benchmark_response(service_tier=bad_value))
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == "response_received"
    assert result.provider_request_id == "req_123"
    assert result.raw_response_source is None
    assert result.raw_response_sha256 is None
    assert result.response_id is None
    assert result.returned_model_id is None
    assert result.returned_service_tier is None
    assert result.usage.availability == "unavailable"
    assert result.usage.cache_read_status == "invalid"
    assert result.usage.cache_write_status == "invalid"
    assert result.usage.reasoning_token_accounting == "invalid"
    assert not hasattr(result, "output_text")


@pytest.mark.parametrize("projection_failure", [False, True])
def test_benchmark_response_request_id_accessor_failure_is_fail_closed(
    projection_failure: bool,
) -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        PublicBenchmarkResponseEvidenceV1,
    )

    class RequestIdTrapResponse(_BenchmarkResponse):
        @property
        def _request_id(self) -> object:
            raise RuntimeError("request ID accessor failed")

    values = dict(benchmark_response().__dict__)
    values.pop("_request_id")
    if projection_failure:
        values["service_tier"] = object()
    response_object = RequestIdTrapResponse(**values)

    result = OpenAIProvider(client=StubClient(response_object)).generate_benchmark(
        benchmark_request()
    )

    if projection_failure:
        assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
        assert result.delivery_certainty == "response_received"
        assert result.provider_request_id is None
        assert result.raw_response_source is None
    else:
        assert type(result) is PublicBenchmarkResponseEvidenceV1
        assert result.response_id == "resp_123"


@pytest.mark.parametrize(
    ("error_name", "status", "expected_delivery", "expected_not_applicable"),
    [
        (
            "RateLimitError",
            429,
            "definitely_rejected",
            "not_applicable_definitely_rejected",
        ),
        (
            "AuthenticationError",
            401,
            "definitely_rejected",
            "not_applicable_definitely_rejected",
        ),
        ("APITimeoutError", None, "unknown", "missing"),
    ],
)
def test_benchmark_sdk_errors_return_source_bound_no_response_evidence(
    error_name: str,
    status: int | None,
    expected_delivery: str,
    expected_not_applicable: str,
) -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        public_benchmark_provider_error_source_sha256,
    )

    exception = sdk_error_type(error_name)("provider-controlled diagnostic")
    if status is not None:
        exception.status_code = status  # type: ignore[attr-defined]
    exception.request_id = "req-safe"  # type: ignore[attr-defined]

    result = OpenAIProvider(client=StubClient(exception)).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == expected_delivery
    assert result.provider_request_id == "req-safe"
    assert result.response_id is None
    assert result.raw_response_source is None
    assert result.raw_response_sha256 is None
    assert result.structured_status == status
    assert result.returned_service_tier is None
    assert result.service_tier_status == expected_not_applicable
    assert result.applied_cache_control_status == expected_not_applicable
    assert result.usage.availability == "unavailable"
    assert result.usage.cache_read_status == expected_not_applicable
    assert result.usage.cache_write_status == expected_not_applicable
    assert result.error_source_sha256 == public_benchmark_provider_error_source_sha256(result)


def test_invalid_completed_output_preserves_safe_tier_model_usage_and_common_raw_source() -> None:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderErrorEvidenceV1

    result = OpenAIProvider(
        client=StubClient(
            benchmark_response(
                output=[],
                service_tier="priority",
                model="gpt-5.6-sol-other",
            )
        )
    ).generate_benchmark(benchmark_request())

    assert type(result) is PublicBenchmarkProviderErrorEvidenceV1
    assert result.delivery_certainty == "response_received"
    assert result.response_id == "resp_123"
    assert result.returned_model_id == "gpt-5.6-sol-other"
    assert result.returned_service_tier == "priority"
    assert result.service_tier_status == "mismatch"
    assert result.usage.input_tokens == 10
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cache_write_tokens == 0
    assert result.raw_response_source is not None
    assert (
        result.returned_model_source_sha256
        == result.service_tier_source_sha256
        == result.applied_cache_control_source_sha256
        == result.cache_read_source_sha256
        == result.cache_write_source_sha256
        == result.usage_source_sha256
        == result.reasoning_tokens_source_sha256
        == result.raw_response_sha256
    )


def test_injected_client_uses_exact_responses_contract_and_maps_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def reject_openai_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("injected clients must not import the optional SDK")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_openai_import)
    client = StubClient(response())

    result = OpenAIProvider(client=client).generate(request())

    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": "Answer concisely.",
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
        }
    ]
    assert result.output_text == "Complete answer."
    assert result.request_id == "req_123"
    assert result.finish_reason == "completed"
    assert result.response_model == "gpt-5.5-2026-08-01"
    assert result.delivery_certainty == "response_received"
    assert result.usage is not None
    assert result.usage.input_tokens == 15
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 19
    assert result.usage.cached_input_tokens == 6
    assert not hasattr(result, "response")


def test_nullable_fields_are_explicit_and_temperature_is_only_sent_when_present() -> None:
    client = StubClient(response(_request_id=None, usage=None, output_text="No metadata."))
    provider = OpenAIProvider(client=client)

    result = provider.generate(request(instructions=None, temperature=0.25, arm="baseline"))

    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": None,
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
            "temperature": 0.25,
        }
    ]
    assert result.usage is None
    assert result.request_id is None
    assert result.finish_reason == "completed"
    assert result.delivery_certainty == "response_received"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"model": "  "}, "model"),
        ({"model": 7}, "model"),
        ({"prompt": "\t"}, "prompt"),
        ({"prompt": None}, "prompt"),
        ({"instructions": ""}, "instructions"),
        ({"instructions": 3}, "instructions"),
        ({"max_output_tokens": 0}, "max_output_tokens"),
        ({"max_output_tokens": True}, "max_output_tokens"),
        ({"temperature": -0.1}, "temperature"),
        ({"temperature": 2.1}, "temperature"),
        ({"temperature": _HUGE_INTEGER}, "temperature"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": _HUGE_INTEGER}, "timeout_seconds"),
        ({"timeout_seconds": 30}, "does not match"),
    ],
)
def test_invalid_local_requests_are_rejected_before_the_api_call(
    overrides: dict[str, object], message: str
) -> None:
    client = StubClient(response())

    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=client).generate(request(**overrides))

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []


@pytest.mark.parametrize(
    ("bad_response", "message", "invalid_field"),
    [
        (response(output_text=None), "output_text", "output"),
        (response(_request_id=123), "request ID", "request_id"),
        (response(status=7), "status", "status"),
        (response(model=None), "model", "model"),
        (response(usage=SimpleNamespace(input_tokens=1)), "usage", "usage"),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=True,
                    output_tokens=1,
                    total_tokens=2,
                    input_tokens_details=None,
                )
            ),
            "input_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=3,
                    total_tokens=4,
                    input_tokens_details=None,
                )
            ),
            "total_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=4,
                    input_tokens_details=None,
                )
            ),
            "total_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=3,
                    input_tokens_details=SimpleNamespace(cached_tokens=3),
                )
            ),
            "cached_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=3,
                    input_tokens_details=5,
                )
            ),
            "input_tokens_details",
            "usage",
        ),
    ],
)
def test_malformed_responses_become_nonretryable_provider_errors(
    bad_response: object,
    message: str,
    invalid_field: str,
) -> None:
    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=StubClient(bad_response)).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == (None if invalid_field == "request_id" else "req_123")
    assert caught.value.response_model == (
        None if invalid_field == "model" else "gpt-5.5-2026-08-01"
    )
    assert caught.value.finish_reason == (None if invalid_field == "status" else "completed")
    assert caught.value.usage == (
        None
        if invalid_field == "usage"
        else TokenUsage(
            input_tokens=15,
            output_tokens=4,
            total_tokens=19,
            cached_input_tokens=6,
        )
    )


@pytest.mark.parametrize(
    (
        "exception_name",
        "status_code",
        "kind",
        "retryable",
        "delivery_certainty",
        "safe_retry_candidate",
    ),
    [
        (
            "AuthenticationError",
            401,
            "authentication",
            False,
            "definitely_rejected",
            False,
        ),
        ("PermissionDeniedError", 403, "permission", False, "definitely_rejected", False),
        ("BadRequestError", 400, "bad_request", False, "definitely_rejected", False),
        ("RateLimitError", 429, "rate_limit", True, "definitely_rejected", True),
        ("APITimeoutError", None, "timeout", True, "unknown", False),
        ("APIConnectionError", None, "connection", True, "unknown", False),
        ("InternalServerError", 500, "server_error", True, "unknown", False),
        ("APIStatusError", 408, "provider_status", True, "unknown", False),
        ("APIStatusError", 503, "server_error", True, "unknown", False),
        ("APIStatusError", 409, "provider_status", True, "definitely_rejected", True),
        ("APIStatusError", 422, "provider_status", False, "definitely_rejected", False),
        ("OpenAIError", None, "provider_error", False, "unknown", False),
    ],
)
def test_recognized_sdk_errors_are_classified_and_preserve_request_ids(
    exception_name: str,
    status_code: int | None,
    kind: str,
    retryable: bool,
    delivery_certainty: str,
    safe_retry_candidate: bool,
) -> None:
    exception = sdk_error_type(exception_name)("synthetic API failure")
    exception.request_id = "req_error"  # type: ignore[attr-defined]
    if status_code is not None:
        exception.status_code = status_code  # type: ignore[attr-defined]

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == delivery_certainty
    assert caught.value.request_id == "req_error"
    assert (
        caught.value.kind != "authentication"
        and caught.value.retryable
        and caught.value.delivery_certainty in {"definitely_not_sent", "definitely_rejected"}
    ) is safe_retry_candidate


@pytest.mark.parametrize(
    ("exception_name", "status_code", "kind", "retryable"),
    [
        ("AuthenticationError", 500, "authentication", False),
        ("RateLimitError", 500, "rate_limit", True),
        ("APITimeoutError", 400, "timeout", True),
    ],
)
def test_ambiguous_transport_evidence_precedes_rejection_classification(
    exception_name: str,
    status_code: int,
    kind: str,
    retryable: bool,
) -> None:
    exception = sdk_error_type(exception_name)("contradictory synthetic failure")
    exception.status_code = status_code  # type: ignore[attr-defined]

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == "unknown"


def test_unrelated_exceptions_and_base_exceptions_are_not_reclassified() -> None:
    unrelated = RuntimeError("programming defect")
    with pytest.raises(RuntimeError, match="programming defect"):
        OpenAIProvider(client=StubClient(unrelated)).generate(request())

    with pytest.raises(KeyboardInterrupt):
        OpenAIProvider(client=StubClient(KeyboardInterrupt())).generate(request())


@pytest.mark.parametrize("collision_name", ["AuthenticationError", "OpenAIError"])
def test_unrelated_exception_name_collisions_propagate_unchanged(
    collision_name: str,
) -> None:
    collision_type = type(collision_name, (RuntimeError,), {})
    collision = collision_type("application failure")
    collision.status_code = 401  # type: ignore[attr-defined]

    with pytest.raises(collision_type) as caught:
        OpenAIProvider(client=StubClient(collision)).generate(request())

    assert caught.value is collision


@pytest.mark.parametrize(
    "collision_name",
    [
        "AuthenticationError",
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
    ],
)
def test_non_sdk_subclass_name_collisions_on_openai_root_fail_closed(
    collision_name: str,
) -> None:
    collision_type = type(
        collision_name,
        (sdk_error_type("OpenAIError"),),
        {"__module__": __name__},
    )
    collision = collision_type("application-defined OpenAI failure")

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(collision)).generate(request())

    assert caught.value.kind == "provider_error"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "unknown"


def test_incomplete_response_is_a_nonretryable_provider_error() -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status="incomplete"))).generate(request())

    assert caught.value.kind == "incomplete_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "incomplete"
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )
    assert "gpt-5.5-2026-08-01" in caught.value.message


@pytest.mark.parametrize("output_text", ["", " \n\t"])
def test_completed_response_rejects_blank_output_with_request_id(output_text: str) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(output_text=output_text))).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "completed"
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )


@pytest.mark.parametrize(
    ("status", "public_error", "kind", "retryable", "message"),
    [
        (
            "failed",
            SimpleNamespace(
                code="server_error",
                message="Public server failure.",
                private_detail="must-not-leak",
            ),
            "server_error",
            True,
            "Public server failure.",
        ),
        (
            "failed",
            SimpleNamespace(
                code="rate_limit_exceeded",
                message="Public rate-limit failure.",
            ),
            "rate_limit_exceeded",
            True,
            "Public rate-limit failure.",
        ),
        (
            "failed",
            SimpleNamespace(
                code="authentication",
                message="Public authentication failure.",
            ),
            "authentication",
            False,
            "Public authentication failure.",
        ),
        ("cancelled", None, "cancelled", False, "cancelled"),
    ],
)
def test_failed_and_cancelled_responses_become_public_provider_errors(
    status: str,
    public_error: object | None,
    kind: str,
    retryable: bool,
    message: str,
) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status=status, error=public_error))).generate(
            request()
        )

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == status
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )
    assert message in caught.value.message
    assert "must-not-leak" not in caught.value.message


@pytest.mark.parametrize("status", ["queued", "in_progress", "unknown"])
def test_nonterminal_or_unknown_response_status_is_rejected_with_request_id(status: str) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status=status))).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == status
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )


def test_failed_response_with_invalid_usage_retains_other_valid_metadata() -> None:
    bad_usage = SimpleNamespace(
        input_tokens=2,
        output_tokens=1,
        total_tokens=4,
        input_tokens_details=None,
    )
    public_error = SimpleNamespace(code="server_error", message="Public failure.")

    with pytest.raises(ProviderError, match="total_tokens") as caught:
        OpenAIProvider(
            client=StubClient(response(status="failed", error=public_error, usage=bad_usage))
        ).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "failed"
    assert caught.value.usage is None


def test_live_client_is_configured_with_timeout_and_sdk_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client_calls: list[dict[str, object]] = []
    openai_calls: list[dict[str, object]] = []
    constructed_http_client = object()
    client = StubClient(response())
    module = ModuleType("openai")

    def make_http_client(**kwargs: object) -> object:
        http_client_calls.append(kwargs)
        return constructed_http_client

    def make_client(**kwargs: object) -> StubClient:
        openai_calls.append(kwargs)
        return client

    module.DefaultHttpxClient = make_http_client  # type: ignore[attr-defined]
    module.OpenAI = make_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://ambient.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "https://ambient.invalid:8443")
    monkeypatch.setenv("ALL_PROXY", "socks5://ambient.invalid:1080")
    monkeypatch.setenv("NO_PROXY", "api.openai.com")
    monkeypatch.setenv("SSL_CERT_FILE", "/ambient/cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/ambient/certs")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/ambient/requests.pem")
    monkeypatch.setenv("CURL_CA_BUNDLE", "/ambient/curl.pem")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.invalid/v9")
    monkeypatch.setenv("OPENAI_ORG_ID", "ambient-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "ambient-project")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "ambient-admin")
    monkeypatch.setenv("OPENAI_WEBHOOK_SECRET", "ambient-webhook")

    provider = OpenAIProvider(api_key="test-key", timeout_seconds=120)
    provider.generate(request(timeout_seconds=120))

    assert http_client_calls == [{"trust_env": False}]
    assert openai_calls == [
        {
            "api_key": "test-key",
            "timeout": 120.0,
            "max_retries": 0,
            "base_url": "https://api.openai.com/v1",
            "organization": "",
            "project": "",
            "admin_api_key": "",
            "webhook_secret": "",
            "http_client": constructed_http_client,
        }
    ]
    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": "Answer concisely.",
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
        }
    ]


def test_live_client_rejects_ambient_custom_headers_before_sdk_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    module = ModuleType("openai")

    def make_client(**kwargs: object) -> StubClient:
        calls.append(kwargs)
        return StubClient(response())

    module.OpenAI = make_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", '{"X-Ambient": "unsafe"}')

    with pytest.raises(ProviderError, match="OPENAI_CUSTOM_HEADERS") as caught:
        OpenAIProvider(api_key="configured-key")

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert calls == []


def test_live_client_requires_nonblank_key_and_the_optional_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ProviderError, match="API key") as blank:
        OpenAIProvider(api_key=" ")
    assert blank.value.kind == "configuration"
    assert blank.value.delivery_certainty == "definitely_not_sent"
    with pytest.raises(ProviderError, match="API key"):
        OpenAIProvider(api_key=3)  # type: ignore[arg-type]

    original_import = builtins.__import__

    def missing_openai(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "openai":
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "openai", raising=False)
    monkeypatch.setattr(builtins, "__import__", missing_openai)
    with pytest.raises(ProviderError, match="openai") as missing:
        OpenAIProvider(api_key="test-key")
    assert missing.value.kind == "configuration"
    assert missing.value.retryable is False
    assert missing.value.delivery_certainty == "definitely_not_sent"


def test_huge_provider_timeout_is_a_local_configuration_error() -> None:
    client = StubClient(response())

    with pytest.raises(ProviderError, match="timeout_seconds") as caught:
        OpenAIProvider(client=client, timeout_seconds=_HUGE_INTEGER)

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []


def test_injected_openai_result_flows_through_content_free_normalization() -> None:
    patterns = SanitizerPatterns(
        credential_values=("TOP-SECRET",),
        cwd_roots=("/private/build",),
    )
    parsed = OpenAIProvider(
        client=StubClient(
            response(
                output_text="TOP-SECRET answer",
                _request_id="/private/build/request",
            )
        )
    ).generate(request())

    evidence = normalize_provider_outcome(parsed, patterns=patterns)

    assert evidence.delivery_certainty == "response_received"
    assert evidence.output is None
    assert evidence.response_model == "gpt-5.5-2026-08-01"
    assert evidence.request_id is None
    assert evidence.finish_reason == "completed"
    assert evidence.error is not None
    assert evidence.error.kind == "unsafe_provider_metadata"
    assert evidence.error.message == "unsafe_provider_metadata"
    assert evidence.error.retryable is False
    assert "TOP-SECRET" not in repr(evidence)
    assert "/private/build" not in repr(evidence)


def test_injected_openai_error_flows_through_diagnostic_normalization() -> None:
    patterns = SanitizerPatterns(
        credential_values=("TOP-SECRET",),
        cwd_roots=("/private/build",),
    )
    exception = sdk_error_type("RateLimitError")("TOP-SECRET failed at /private/build/job")
    exception.status_code = 429  # type: ignore[attr-defined]
    exception.request_id = "req-safe"  # type: ignore[attr-defined]
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    evidence = normalize_provider_outcome(caught.value, patterns=patterns)

    assert evidence.delivery_certainty == "definitely_rejected"
    assert evidence.output is None
    assert evidence.request_id == "req-safe"
    assert evidence.error is not None
    assert evidence.error.kind == "rate_limit"
    assert evidence.error.message == "[REDACTED] failed at [CWD]/job"
    assert evidence.error.retryable is True
    assert "TOP-SECRET" not in repr(evidence)
    assert "/private/build" not in repr(evidence)
