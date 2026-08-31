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
        "response_paths",
        "returned_model_path",
        "response_content_paths",
        "serializer_projection_sha256",
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
