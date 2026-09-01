"""Captured-only execution for prepared generation capsules.

The public boundary deliberately accepts one exact repository-owned provider factory.  Test-only
providers and clocks enter through the private orchestration seam below; they are not part of the
executed provenance accepted by :func:`resume_capsule`.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import importlib
import os
import pwd
import socket
import sys
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import CodeType, FunctionType, ModuleType
from typing import Literal, NoReturn, cast
from uuid import RFC_4122, UUID, uuid4

from pydantic import BaseModel

import laconian_eval.providers.fake as _fake_provider_module
import laconian_eval.providers.openai as _openai_provider_module
import laconian_eval.providers.replay as _replay_provider_module
import laconian_eval.yaml_io as _yaml_io_module
from laconian_eval import __version__
from laconian_eval import capsule as _capsule_module
from laconian_eval.capsule import attempts as _attempts_module
from laconian_eval.capsule import canonical as _canonical_module
from laconian_eval.capsule import sanitizer as _sanitizer_module
from laconian_eval.capsule.attempts import (
    NormalizedProviderEvidenceV2,
    PublicBenchmarkProvider,
    PublicBenchmarkProviderOutcomeV1,
    RawAttemptV2,
    TerminalReason,
    _derive_response_id_fields,
    derive_attempt_id,
    normalize_provider_outcome,
    normalize_public_benchmark_outcome,
    raw_attempt_bytes,
    raw_record_sha256,
)
from laconian_eval.capsule.bounded_io import BoundedIOError, open_directory_no_follow
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.events import EventKind, EventV1, event_jsonl, make_event
from laconian_eval.capsule.filesystem import (
    FilesystemPosixOps,
    LockHandle,
    OwnedStagingError,
    UnsupportedFilesystemError,
    classify_filesystem,
    try_acquire_mutator_lock,
)
from laconian_eval.capsule.history import (
    HistoryContextV1,
    LifecycleProjectionV1,
)
from laconian_eval.capsule.import_policy import (
    ImportPolicy,
    ImportPolicyError,
    build_import_policy,
    install_import_guard,
    revalidate_import_environment,
    revalidate_import_policy,
    revalidate_import_state,
)
from laconian_eval.capsule.journal import (
    JournalError,
    JournalPairSnapshotV1,
    JournalTransaction,
    _snapshot_transaction_pair,
    append_event,
    append_raw_attempt,
)
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    reserve_attempt_transaction,
)
from laconian_eval.capsule.planning import plan_item_id, request_config_sha256
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.provenance import (
    InstalledProvenance,
    ProvenanceError,
    capture_resume_provenance,
    project_environment,
)
from laconian_eval.capsule.record_models import (
    EnvironmentV1,
    PlanRowV1,
    SessionEnvironmentV1,
    VerifyResultV1,
)
from laconian_eval.capsule.recovery import (
    RecoveryError,
    _apply_recovery_plan_v1,
    _make_mutator_session_v1,
    _MutatorSessionV1,
    _plan_mutator_session_v1,
    _revalidate_mutator_session_v1,
)
from laconian_eval.capsule.sanitizer import SanitizerPatterns
from laconian_eval.capsule.schema import PublicBenchmarkModelId, ServiceTier
from laconian_eval.capsule.verify import (
    _busy_result,
    _check_lock_identity,
    _check_public_root_identity,
    _Identity,
    _invalid_result,
    _unsupported_result,
    _VerifiedCapsuleContext,
    _VerifiedRecoveryContext,
)
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase
from laconian_eval.providers.base import (
    GenerationRequest,
    GenerationResult,
    Provider,
    ProviderError,
    PublicBenchmarkRequestPolicyV1,
    PublicBenchmarkRequestV1,
)
from laconian_eval.providers.fake import FakeProvider
from laconian_eval.providers.openai import OpenAIProvider
from laconian_eval.providers.replay import ReplayProvider

ProviderKind = Literal["fake", "replay", "openai"]
TransportPolicy = Literal["offline", "openai-direct-v1"]
ResumeCode = Literal[
    "complete",
    "operational_stop",
    "invalid",
    "busy",
    "unsupported_filesystem",
    "producer_runtime_differs",
    "sealed",
]

_GENERIC_RESUME_ERROR = "capsule resume rejected"
_GENERIC_CREDENTIAL_ERROR = "provider credential unavailable"
_GENERIC_PROVIDER_ERROR = "provider unavailable"
_AUTHORED_INPUT_ROLES = frozenset({"case", "arm", "replay", "protocol"})
_EVENT_ROW_RESERVATION = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
_RAW_ROW_RESERVATION = RESOURCE_LIMITS_V1.raw_jsonl_row_bytes + 1
_REAL_GUARD_STATE: Literal["fresh", "installing", "installed", "poisoned"] = "fresh"
_FAKE_PROVIDER_TYPE = FakeProvider
_REPLAY_PROVIDER_TYPE = ReplayProvider
_OPENAI_PROVIDER_TYPE = OpenAIProvider
_NORMALIZE_PROVIDER_OUTCOME = normalize_provider_outcome
_NORMALIZE_PUBLIC_BENCHMARK_OUTCOME = normalize_public_benchmark_outcome
_OPENAI_HASHLIB_MODULE = cast(ModuleType, vars(_openai_provider_module)["hashlib"])
_OPENAI_UNICODEDATA_MODULE = cast(
    ModuleType,
    vars(_openai_provider_module)["unicodedata"],
)
_CANONICAL_JSON_MODULE = cast(ModuleType, vars(_canonical_module)["json"])
_CANONICAL_MATH_MODULE = cast(ModuleType, vars(_canonical_module)["math"])
_FAKE_PROVIDER_INIT = FakeProvider.__init__
_FAKE_PROVIDER_GENERATE = FakeProvider.generate
_REPLAY_PROVIDER_INIT = ReplayProvider.__init__
_REPLAY_PROVIDER_FROM_MAPPING = ReplayProvider.__dict__["_from_mapping"].__func__
_REPLAY_PROVIDER_FROM_BYTES = ReplayProvider.__dict__["from_bytes"].__func__
_REPLAY_PROVIDER_FROM_BENCHMARK_BYTES = ReplayProvider.__dict__["from_benchmark_bytes"].__func__
_REPLAY_PROVIDER_GENERATE = ReplayProvider.generate
_REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST = ReplayProvider._validate_benchmark_request
_REPLAY_PROVIDER_GENERATE_BENCHMARK = ReplayProvider.generate_benchmark
_OPENAI_PROVIDER_INIT = OpenAIProvider.__init__
_OPENAI_PROVIDER_VALIDATE_REQUEST = OpenAIProvider._validate_request
_OPENAI_PROVIDER_GENERATE = OpenAIProvider.generate
_OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST = OpenAIProvider._validate_benchmark_request
_OPENAI_PROVIDER_GENERATE_BENCHMARK = OpenAIProvider.generate_benchmark


class ResumeError(ValueError):
    """A content-free resume failure with one stable code."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_RESUME_ERROR)


class CredentialUnavailable(RuntimeError):
    """The exact authored credential is absent or unusable."""

    __slots__ = ()
    code = "credential_unavailable"

    def __init__(self) -> None:
        super().__init__(_GENERIC_CREDENTIAL_ERROR)


class ProviderUnavailable(RuntimeError):
    """The captured provider adapter cannot be constructed."""

    __slots__ = ()
    code = "provider_unavailable"

    def __init__(self) -> None:
        super().__init__(_GENERIC_PROVIDER_ERROR)


@dataclass(frozen=True, slots=True)
class _FunctionSeal:
    function: FunctionType = field(repr=False)
    code: CodeType = field(repr=False)
    defaults: object = field(repr=False)
    kwdefaults: object = field(repr=False)
    closure: object = field(repr=False)
    globals_id: int
    builtins_id: int


@dataclass(frozen=True, slots=True)
class _ClassSeal:
    class_type: type[object] = field(repr=False)
    metaclass: type[object] = field(repr=False)
    mro: tuple[type[object], ...] = field(repr=False)
    namespace: tuple[tuple[str, object], ...] = field(repr=False)
    functions: tuple[tuple[str, str, _FunctionSeal], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _AttributeSeal:
    owner: object = field(repr=False)
    name: str
    value: object = field(repr=False)
    function: _FunctionSeal | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class _DescriptorSeal:
    owner: type[object] = field(repr=False)
    name: str
    kind: Literal["function", "classmethod", "staticmethod"]
    descriptor: object = field(repr=False)
    function: _FunctionSeal = field(repr=False)


@dataclass(frozen=True, slots=True)
class _ModuleNamespaceSeal:
    module: ModuleType = field(repr=False)
    bindings: tuple[tuple[str, object], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _OpenAISdkSeal:
    module: ModuleType = field(repr=False)
    client_type: type[object] = field(repr=False)
    http_client_type: type[object] = field(repr=False)
    class_seals: tuple[_ClassSeal, ...] = field(repr=False)


def _default_identity_seal(value: object) -> object:
    if value is None:
        return None
    if type(value) is not tuple:
        raise TypeError
    return (id(value), tuple(id(item) for item in value))


def _kwdefault_identity_seal(value: object) -> object:
    if value is None:
        return None
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise TypeError
    return (
        id(value),
        tuple(
            (key, id(value[key])) for key in sorted(value, key=lambda item: item.encode("utf-8"))
        ),
    )


def _closure_identity_seal(value: object) -> object:
    if value is None:
        return None
    if type(value) is not tuple:
        raise TypeError
    return (
        id(value),
        tuple((id(cell), id(cell.cell_contents)) for cell in value),
    )


def _function_globals(value: FunctionType) -> tuple[object, object]:
    return (
        value.__globals__,
        object.__getattribute__(value, "__builtins__"),
    )


def _function_descriptor_seals(
    namespace: tuple[tuple[str, object], ...],
) -> tuple[tuple[str, str, _FunctionSeal], ...]:
    functions: list[tuple[str, str, _FunctionSeal]] = []
    for name, member in namespace:
        if type(member) is FunctionType:
            functions.append((name, "function", _seal_function(member)))
        elif type(member) is classmethod:
            functions.append((name, "classmethod", _seal_function(member.__func__)))
        elif type(member) is staticmethod:
            functions.append((name, "staticmethod", _seal_function(member.__func__)))
        elif type(member) is property:
            for accessor_name in ("fget", "fset", "fdel"):
                accessor = getattr(member, accessor_name)
                if accessor is not None:
                    functions.append(
                        (
                            name,
                            f"property:{accessor_name}",
                            _seal_function(accessor),
                        )
                    )
    return tuple(functions)


def _seal_function(value: object) -> _FunctionSeal:
    if type(value) is not FunctionType:
        raise TypeError
    function_globals, function_builtins = _function_globals(value)
    return _FunctionSeal(
        value,
        value.__code__,
        _default_identity_seal(value.__defaults__),
        _kwdefault_identity_seal(value.__kwdefaults__),
        _closure_identity_seal(value.__closure__),
        id(function_globals),
        id(function_builtins),
    )


def _function_matches_seal(value: object, seal: _FunctionSeal) -> bool:
    try:
        return (
            type(value) is FunctionType
            and value is seal.function
            and value.__code__ is seal.code
            and _default_identity_seal(value.__defaults__) == seal.defaults
            and _kwdefault_identity_seal(value.__kwdefaults__) == seal.kwdefaults
            and _closure_identity_seal(value.__closure__) == seal.closure
            and id(value.__globals__) == seal.globals_id
            and id(object.__getattribute__(value, "__builtins__")) == seal.builtins_id
        )
    except Exception:
        return False


def _seal_attribute(owner: object, name: str) -> _AttributeSeal:
    value = getattr(owner, name)
    function = _seal_function(value) if type(value) is FunctionType else None
    return _AttributeSeal(owner, name, value, function)


def _attribute_matches_seal(seal: _AttributeSeal) -> bool:
    try:
        value = getattr(seal.owner, seal.name)
        return value is seal.value and (
            seal.function is None or _function_matches_seal(value, seal.function)
        )
    except Exception:
        return False


def _seal_descriptor(owner: type[object], name: str) -> _DescriptorSeal:
    descriptor = vars(owner)[name]
    if type(descriptor) is FunctionType:
        kind: Literal["function", "classmethod", "staticmethod"] = "function"
        function = descriptor
    elif type(descriptor) is classmethod:
        kind = "classmethod"
        function = cast(FunctionType, descriptor.__func__)
    elif type(descriptor) is staticmethod:
        kind = "staticmethod"
        function = cast(FunctionType, descriptor.__func__)
    else:
        raise TypeError
    return _DescriptorSeal(owner, name, kind, descriptor, _seal_function(function))


def _descriptor_matches_seal(seal: _DescriptorSeal) -> bool:
    try:
        descriptor = vars(seal.owner).get(seal.name)
        if descriptor is not seal.descriptor:
            return False
        if seal.kind == "function":
            function = descriptor
        elif (seal.kind == "classmethod" and type(descriptor) is classmethod) or (
            seal.kind == "staticmethod" and type(descriptor) is staticmethod
        ):
            function = descriptor.__func__
        else:
            return False
        return _function_matches_seal(function, seal.function)
    except Exception:
        return False


def _seal_module_namespace(module: ModuleType) -> _ModuleNamespaceSeal:
    if type(module) is not ModuleType:
        raise TypeError
    bindings = tuple(
        (name, value)
        for name, value in sorted(vars(module).items(), key=lambda item: item[0].encode("utf-8"))
        if not name.startswith("__")
    )
    return _ModuleNamespaceSeal(module, bindings)


def _module_namespace_matches_seal(seal: _ModuleNamespaceSeal) -> bool:
    try:
        namespace = vars(seal.module)
        return sum(not name.startswith("__") for name in namespace) == len(seal.bindings) and all(
            name in namespace and namespace[name] is expected for name, expected in seal.bindings
        )
    except Exception:
        return False


def _seal_class(value: object) -> _ClassSeal:
    if not isinstance(value, type):
        raise TypeError
    namespace = tuple(sorted(vars(value).items(), key=lambda item: item[0].encode("utf-8")))
    return _ClassSeal(
        value,
        type(value),
        value.__mro__,
        namespace,
        _function_descriptor_seals(namespace),
    )


def _class_matches_seal(value: object, seal: _ClassSeal) -> bool:
    try:
        if value is not seal.class_type or type(value) is not seal.metaclass:
            return False
        if value.__mro__ != seal.mro:
            return False
        current = vars(value)
        if len(current) != len(seal.namespace) or any(
            name not in current or current[name] is not expected
            for name, expected in seal.namespace
        ):
            return False
        for name, descriptor_kind, function_seal in seal.functions:
            member = current.get(name)
            if descriptor_kind == "function":
                function = member
            elif (descriptor_kind == "classmethod" and type(member) is classmethod) or (
                descriptor_kind == "staticmethod" and type(member) is staticmethod
            ):
                function = member.__func__
            elif descriptor_kind.startswith("property:") and type(member) is property:
                function = getattr(member, descriptor_kind.removeprefix("property:"))
            else:
                return False
            if not _function_matches_seal(function, function_seal):
                return False
        return True
    except Exception:
        return False


def _resolve_openai_sdk() -> _OpenAISdkSeal:
    """Resolve and seal the SDK construction surface before any credential read."""

    try:
        module = importlib.import_module("openai")
        if type(module) is not ModuleType or module.__name__ != "openai":
            raise TypeError
        namespace = vars(module)
        client_type = namespace.get("OpenAI")
        http_client_type = namespace.get("DefaultHttpxClient")
        if (
            type(client_type) is not type
            or client_type.__module__ != "openai"
            or client_type.__qualname__ != "OpenAI"
            or type(http_client_type) is not type
            or http_client_type.__module__ != "openai"
            or http_client_type.__qualname__ != "_DefaultHttpxClient"
        ):
            raise TypeError
        hierarchy: list[type[object]] = []
        seen: set[int] = set()
        for leaf in (client_type, http_client_type):
            for owner in leaf.__mro__:
                if owner is object or id(owner) in seen:
                    continue
                if type(owner) is not type:
                    raise TypeError
                seen.add(id(owner))
                hierarchy.append(owner)
        return _OpenAISdkSeal(
            module,
            client_type,
            http_client_type,
            tuple(_seal_class(owner) for owner in hierarchy),
        )
    except ProviderUnavailable:
        raise
    except Exception:
        raise ProviderUnavailable() from None


def _openai_sdk_matches_seal(seal: _OpenAISdkSeal) -> bool:
    try:
        namespace = vars(seal.module)
        return (
            namespace.get("OpenAI") is seal.client_type
            and namespace.get("DefaultHttpxClient") is seal.http_client_type
            and all(
                _class_matches_seal(class_seal.class_type, class_seal)
                for class_seal in seal.class_seals
            )
        )
    except Exception:
        return False


def _provider_kind(value: object) -> ProviderKind:
    if type(value) is not str or value not in {"fake", "replay", "openai"}:
        raise ResumeError("invalid_provider_factory_request")
    return cast(ProviderKind, value)


def _required_text(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ResumeError("invalid_provider_factory_request")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ResumeError("invalid_provider_factory_request") from None
    if len(encoded) > RESOURCE_LIMITS_V1.bounded_string_bytes:
        raise ResumeError("invalid_provider_factory_request")
    return value


@dataclass(frozen=True, slots=True)
class ProviderFactoryRequest:
    provider_kind: ProviderKind
    requested_model: str
    api_key_env: str | None
    timeout_seconds: float
    adapter_source_sha256: str
    transport_policy: TransportPolicy
    sdk_distribution: Literal["openai"] | None
    sdk_version: str | None
    captured_replay_bytes: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        kind = _provider_kind(self.provider_kind)
        model = _required_text(self.requested_model)
        adapter = self.adapter_source_sha256
        timeout = self.timeout_seconds
        api_key_env = self.api_key_env
        transport = self.transport_policy
        sdk_distribution = self.sdk_distribution
        sdk_version = self.sdk_version
        if (
            type(adapter) is not str
            or len(adapter) != 64
            or any(character not in "0123456789abcdef" for character in adapter)
            or type(timeout) is not float
            or not 0.0 < timeout <= 600.0
            or (api_key_env is not None and type(api_key_env) is not str)
            or type(transport) is not str
            or transport not in {"offline", "openai-direct-v1"}
            or (sdk_distribution is not None and type(sdk_distribution) is not str)
            or (sdk_version is not None and type(sdk_version) is not str)
        ):
            raise ResumeError("invalid_provider_factory_request")
        replay = self.captured_replay_bytes
        if replay is not None and type(replay) is not bytes:
            raise ResumeError("invalid_provider_factory_request")
        if kind == "fake":
            valid = (
                self.api_key_env is None
                and replay is None
                and transport == "offline"
                and sdk_distribution is None
                and sdk_version is None
            )
        elif kind == "replay":
            valid = (
                self.api_key_env is None
                and type(replay) is bytes
                and transport == "offline"
                and sdk_distribution is None
                and sdk_version is None
            )
        else:
            valid = (
                type(api_key_env) is str
                and replay is None
                and transport == "openai-direct-v1"
                and sdk_distribution == "openai"
                and type(sdk_version) is str
            )
            if valid:
                _required_text(api_key_env)
                _required_text(sdk_version)
        if not valid:
            raise ResumeError("invalid_provider_factory_request")
        object.__setattr__(self, "provider_kind", kind)
        object.__setattr__(self, "requested_model", model)
        object.__setattr__(self, "adapter_source_sha256", adapter)


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    provider_kind: ProviderKind
    adapter_source_sha256: str
    provider: Provider = field(repr=False)
    credential_values: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        kind = _provider_kind(self.provider_kind)
        adapter = self.adapter_source_sha256
        credentials = self.credential_values
        expected_type: type[object]
        if kind == "fake":
            expected_type = _FAKE_PROVIDER_TYPE
        elif kind == "replay":
            expected_type = _REPLAY_PROVIDER_TYPE
        else:
            expected_type = _OPENAI_PROVIDER_TYPE
        if (
            type(adapter) is not str
            or len(adapter) != 64
            or any(character not in "0123456789abcdef" for character in adapter)
            or type(self.provider) is not expected_type
            or type(credentials) is not tuple
            or any(type(value) is not str or not value for value in credentials)
            or (kind == "openai") != (len(credentials) == 1)
            or (kind != "openai" and credentials)
        ):
            raise ResumeError("invalid_provider_binding")
        object.__setattr__(self, "provider_kind", kind)
        object.__setattr__(self, "credential_values", tuple(credentials))


class ProviderFactory:
    """Exact repository capability for constructing captured provider adapters."""

    __slots__ = ()

    def create(self, request: ProviderFactoryRequest) -> ProviderBinding:
        if type(self) is not ProviderFactory or type(request) is not ProviderFactoryRequest:
            raise ProviderUnavailable()
        try:
            if not _provider_adapter_runtime_intact():
                raise ProviderUnavailable()
            if request.provider_kind == "fake":
                provider: Provider = _FAKE_PROVIDER_TYPE({})
                credentials: tuple[str, ...] = ()
            elif request.provider_kind == "replay":
                replay = request.captured_replay_bytes
                if type(replay) is not bytes:
                    raise ProviderUnavailable()
                if request.requested_model in {
                    "gpt-5.6-sol",
                    "gpt-5.6-terra",
                    "gpt-5.6-luna",
                }:
                    provider = _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES(
                        _REPLAY_PROVIDER_TYPE,
                        replay,
                    )
                else:
                    provider = _REPLAY_PROVIDER_FROM_BYTES(_REPLAY_PROVIDER_TYPE, replay)
                credentials = ()
            else:
                sdk = _resolve_openai_sdk()
                variable = request.api_key_env
                if type(variable) is not str:
                    raise ProviderUnavailable()
                value = os.environ.get(variable)
                if type(value) is not str or not value.strip():
                    raise CredentialUnavailable()
                if os.environ.get("OPENAI_CUSTOM_HEADERS", "").strip():
                    raise ProviderUnavailable()
                if not _openai_sdk_matches_seal(sdk):
                    raise ProviderUnavailable()
                credentials = (value,)
                http_constructor = cast(Callable[..., object], sdk.http_client_type)
                client_constructor = cast(Callable[..., object], sdk.client_type)
                http_client = http_constructor(trust_env=False)
                if not _openai_sdk_matches_seal(sdk):
                    raise ProviderUnavailable()
                client = client_constructor(
                    api_key=value,
                    timeout=request.timeout_seconds,
                    max_retries=0,
                    base_url="https://api.openai.com/v1",
                    organization="",
                    project="",
                    admin_api_key="",
                    webhook_secret="",
                    http_client=http_client,
                )
                if not _openai_sdk_matches_seal(sdk):
                    raise ProviderUnavailable()
                provider = _OPENAI_PROVIDER_TYPE(
                    client=client,
                    timeout_seconds=request.timeout_seconds,
                )
            return ProviderBinding(
                provider_kind=request.provider_kind,
                adapter_source_sha256=request.adapter_source_sha256,
                provider=provider,
                credential_values=credentials,
            )
        except CredentialUnavailable:
            raise
        except ProviderUnavailable:
            raise
        except Exception:
            raise ProviderUnavailable() from None


_PROVIDER_FACTORY_CREATE = ProviderFactory.create


def _module_function_seals(
    module: ModuleType,
) -> tuple[tuple[str, _FunctionSeal], ...]:
    return tuple(
        (name, _seal_function(value))
        for name, value in sorted(vars(module).items(), key=lambda item: item[0].encode("utf-8"))
        if type(value) is FunctionType and value.__module__ == module.__name__
    )


def _module_class_seals(
    module: ModuleType,
) -> tuple[tuple[str, _ClassSeal], ...]:
    return tuple(
        (name, _seal_class(value))
        for name, value in sorted(vars(module).items(), key=lambda item: item[0].encode("utf-8"))
        if isinstance(value, type) and value.__module__ == module.__name__
    )


_PROVIDER_EVIDENCE_MODULES = (
    _attempts_module,
    _canonical_module,
    _sanitizer_module,
    _yaml_io_module,
)
_PROVIDER_EVIDENCE_BUILTIN_NAMES = (
    "AttributeError",
    "Exception",
    "NotImplemented",
    "TypeError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "UnicodeError",
    "ValueError",
    "all",
    "any",
    "bool",
    "bytearray",
    "bytes",
    "chr",
    "classmethod",
    "dict",
    "enumerate",
    "float",
    "getattr",
    "hash",
    "id",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "next",
    "object",
    "ord",
    "property",
    "range",
    "set",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "super",
    "tuple",
    "type",
    "vars",
    "zip",
)
_PROVIDER_EVIDENCE_BUILTINS = cast(
    dict[str, object],
    object.__getattribute__(_NORMALIZE_PUBLIC_BENCHMARK_OUTCOME, "__builtins__"),
)
_PROVIDER_CHECK_ALL = all
_PROVIDER_CHECK_TUPLE: Callable[[Iterable[object]], tuple[object, ...]] = tuple
_PROVIDER_CHECK_TYPE = type
_PROVIDER_RUNTIME_HELPER_ROOTS = tuple(
    (function, function.__code__)
    for function in (
        _function_matches_seal,
        _class_matches_seal,
        _default_identity_seal,
        _kwdefault_identity_seal,
        _closure_identity_seal,
        _attribute_matches_seal,
        _descriptor_matches_seal,
        _module_namespace_matches_seal,
    )
)
_PROVIDER_EVIDENCE_BUILTIN_BINDINGS = tuple(
    (_PROVIDER_EVIDENCE_BUILTINS, name, _PROVIDER_EVIDENCE_BUILTINS[name])
    for name in _PROVIDER_EVIDENCE_BUILTIN_NAMES
)
_PROVIDER_EVIDENCE_MODULE_NAMESPACE_SEALS = tuple(
    _seal_module_namespace(module) for module in _PROVIDER_EVIDENCE_MODULES
)
_PROVIDER_TRANSITIVE_ATTRIBUTE_SEALS = tuple(
    _seal_attribute(owner, name)
    for owner, name in (
        (vars(_openai_provider_module)["hashlib"], "sha256"),
        (vars(_openai_provider_module)["math"], "isfinite"),
        (vars(_openai_provider_module)["re"], "fullmatch"),
        (vars(_openai_provider_module)["unicodedata"], "normalize"),
        (vars(_attempts_module)["hashlib"], "sha256"),
        (vars(_attempts_module)["math"], "isfinite"),
        (vars(_canonical_module)["hashlib"], "sha256"),
        (vars(_canonical_module)["json"], "dumps"),
        (vars(_canonical_module)["math"], "isfinite"),
        (vars(_sanitizer_module)["hashlib"], "sha256"),
        (vars(_sanitizer_module)["heapq"], "heappop"),
        (vars(_sanitizer_module)["heapq"], "heappush"),
        (vars(_yaml_io_module)["yaml"], "SafeLoader"),
        (vars(_yaml_io_module)["yaml"], "compose"),
        (vars(_yaml_io_module)["yaml"], "load"),
        (vars(_yaml_io_module)["yaml"], "parse"),
        (vars(_yaml_io_module)["yaml"], "scan"),
    )
)
_PROVIDER_INHERITED_DESCRIPTOR_SEALS = tuple(
    _seal_descriptor(cast(type[object], BaseModel), name)
    for name in ("model_dump", "model_validate")
)
_PROVIDER_EXACT_CLASS_SEALS = tuple(
    _seal_class(class_type)
    for class_type in (
        ProviderFactory,
        _FAKE_PROVIDER_TYPE,
        _REPLAY_PROVIDER_TYPE,
        _OPENAI_PROVIDER_TYPE,
    )
)
_PROVIDER_CLASS_FUNCTION_SEALS = tuple(
    _seal_function(function)
    for function in (
        _PROVIDER_FACTORY_CREATE,
        _FAKE_PROVIDER_INIT,
        _FAKE_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_INIT,
        _REPLAY_PROVIDER_FROM_MAPPING,
        _REPLAY_PROVIDER_FROM_BYTES,
        _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES,
        _REPLAY_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _REPLAY_PROVIDER_GENERATE_BENCHMARK,
        _OPENAI_PROVIDER_INIT,
        _OPENAI_PROVIDER_VALIDATE_REQUEST,
        _OPENAI_PROVIDER_GENERATE,
        _OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _OPENAI_PROVIDER_GENERATE_BENCHMARK,
    )
)
_PROVIDER_MODULE_FUNCTION_SEALS = tuple(
    (module, _module_function_seals(module))
    for module in (
        _fake_provider_module,
        _replay_provider_module,
        _openai_provider_module,
        _attempts_module,
        _canonical_module,
        _sanitizer_module,
        _yaml_io_module,
    )
)
_PROVIDER_MODULE_CLASS_SEALS = tuple(
    (module, _module_class_seals(module))
    for module in (
        _fake_provider_module,
        _replay_provider_module,
        _openai_provider_module,
        _attempts_module,
        _canonical_module,
        _sanitizer_module,
        _yaml_io_module,
    )
)
_PROVIDER_TRANSITIVE_GLOBAL_BINDINGS = (
    *(
        (module, name, value)
        for module in (
            _attempts_module,
            _canonical_module,
            _sanitizer_module,
            _yaml_io_module,
        )
        for name, value in sorted(
            vars(module).items(),
            key=lambda item: item[0].encode("utf-8"),
        )
        if not name.startswith("__")
    ),
    (
        _OPENAI_HASHLIB_MODULE,
        "sha256",
        _OPENAI_HASHLIB_MODULE.sha256,
    ),
    (
        _OPENAI_UNICODEDATA_MODULE,
        "normalize",
        _OPENAI_UNICODEDATA_MODULE.normalize,
    ),
    (_CANONICAL_JSON_MODULE, "dumps", _CANONICAL_JSON_MODULE.dumps),
    (_CANONICAL_MATH_MODULE, "isfinite", _CANONICAL_MATH_MODULE.isfinite),
    (_capsule_module, "attempts", _attempts_module),
)
_PROVIDER_GLOBAL_BINDINGS = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            _fake_provider_module,
            ("FakeProvider", "GenerationRequest", "GenerationResult", "ProviderError"),
        ),
        (
            _replay_provider_module,
            (
                "GenerationRequest",
                "GenerationResult",
                "Mapping",
                "Path",
                "ProviderError",
                "PublicBenchmarkRequestPolicyV1",
                "PublicBenchmarkRequestV1",
                "RESOURCE_LIMITS_V1",
                "ReplayProvider",
                "TokenUsage",
                "YAMLError",
                "_BENCHMARK_CACHE_FIELDS",
                "_BENCHMARK_ERROR_FIELDS",
                "_BENCHMARK_INPUT_DETAIL_FIELDS",
                "_BENCHMARK_MESSAGE_FIELDS",
                "_BENCHMARK_MODEL_IDS",
                "_BENCHMARK_OUTPUT_DETAIL_FIELDS",
                "_BENCHMARK_OUTPUT_TEXT_FIELDS",
                "_BENCHMARK_RAW_RESPONSE_PATHS",
                "_BENCHMARK_RESPONSE_FIELDS",
                "_BENCHMARK_ROW_FIELDS",
                "_BENCHMARK_SOURCE_DIGEST_FIELDS",
                "_BENCHMARK_USAGE_FIELDS",
                "safe_load_unique",
                "safe_load_unique_bytes",
            ),
        ),
        (
            _openai_provider_module,
            (
                "GenerationRequest",
                "GenerationResult",
                "OpenAIProvider",
                "ProviderError",
                "PublicBenchmarkRequestPolicyV1",
                "PublicBenchmarkRequestV1",
                "ReasoningTokenAccounting",
                "RESOURCE_LIMITS_V1",
                "ServiceTierStatus",
                "TokenUsage",
                "Any",
                "AppliedCacheControlStatus",
                "CacheReadStatus",
                "CacheWriteStatus",
                "DeliveryCertainty",
                "Mapping",
                "_MISSING_RESPONSE_MEMBER",
                "_PUBLIC_BENCHMARK_RAW_RESPONSE_PATHS",
                "_PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS",
                "_canonical_json_v1",
                "bounded_utf8_length",
                "cast",
                "conservative_input_token_bound",
                "hashlib",
                "laconian_eval",
                "math",
                "os",
                "re",
                "suppress",
                "typing",
                "unicodedata",
            ),
        ),
        (
            _attempts_module,
            (
                "AttemptUsageV2",
                "PublicBenchmarkProviderErrorEvidenceV1",
                "PublicBenchmarkProviderOutcomeV1",
                "PublicBenchmarkRawResponseSourceEntryV1",
                "PublicBenchmarkRawResponseSourceV1",
                "PublicBenchmarkResponseEvidenceV1",
                "public_benchmark_provider_error_source_sha256",
                "public_benchmark_raw_response_sha256",
            ),
        ),
    )
    for name in names
)


def _provider_adapter_runtime_intact() -> bool:
    """Reject ordinary in-process rebinding of the executed repository adapters."""

    replay_from_mapping = _REPLAY_PROVIDER_TYPE.__dict__.get("_from_mapping")
    replay_from_bytes = _REPLAY_PROVIDER_TYPE.__dict__.get("from_bytes")
    replay_from_benchmark_bytes = _REPLAY_PROVIDER_TYPE.__dict__.get("from_benchmark_bytes")
    replay_validate_benchmark_request = _REPLAY_PROVIDER_TYPE.__dict__.get(
        "_validate_benchmark_request"
    )
    exact_class_roots = _PROVIDER_CHECK_TUPLE(
        class_seal.class_type for class_seal in _PROVIDER_EXACT_CLASS_SEALS
    )
    class_functions = (
        _PROVIDER_FACTORY_CREATE,
        _UNGUARDED_PROVIDER_FACTORY_CREATE,
        _FAKE_PROVIDER_INIT,
        _FAKE_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_INIT,
        _REPLAY_PROVIDER_FROM_MAPPING,
        _REPLAY_PROVIDER_FROM_BYTES,
        _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES,
        _REPLAY_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _REPLAY_PROVIDER_GENERATE_BENCHMARK,
        _OPENAI_PROVIDER_INIT,
        _OPENAI_PROVIDER_VALIDATE_REQUEST,
        _OPENAI_PROVIDER_GENERATE,
        _OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _OPENAI_PROVIDER_GENERATE_BENCHMARK,
    )
    return (
        (
            ProviderFactory,
            _FAKE_PROVIDER_TYPE,
            _REPLAY_PROVIDER_TYPE,
            _OPENAI_PROVIDER_TYPE,
        )
        == exact_class_roots
        and FakeProvider is _FAKE_PROVIDER_TYPE
        and ReplayProvider is _REPLAY_PROVIDER_TYPE
        and OpenAIProvider is _OPENAI_PROVIDER_TYPE
        and _FAKE_PROVIDER_TYPE.__init__ is _FAKE_PROVIDER_INIT
        and _FAKE_PROVIDER_TYPE.generate is _FAKE_PROVIDER_GENERATE
        and _REPLAY_PROVIDER_TYPE.__init__ is _REPLAY_PROVIDER_INIT
        and _PROVIDER_CHECK_TYPE(replay_from_mapping) is classmethod
        and replay_from_mapping.__func__ is _REPLAY_PROVIDER_FROM_MAPPING
        and _PROVIDER_CHECK_TYPE(replay_from_bytes) is classmethod
        and replay_from_bytes.__func__ is _REPLAY_PROVIDER_FROM_BYTES
        and _PROVIDER_CHECK_TYPE(replay_from_benchmark_bytes) is classmethod
        and replay_from_benchmark_bytes.__func__ is _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES
        and _REPLAY_PROVIDER_TYPE.generate is _REPLAY_PROVIDER_GENERATE
        and _PROVIDER_CHECK_TYPE(replay_validate_benchmark_request) is staticmethod
        and replay_validate_benchmark_request.__func__
        is _REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST
        and _REPLAY_PROVIDER_TYPE.generate_benchmark is _REPLAY_PROVIDER_GENERATE_BENCHMARK
        and _OPENAI_PROVIDER_TYPE.__init__ is _OPENAI_PROVIDER_INIT
        and _OPENAI_PROVIDER_TYPE._validate_request is _OPENAI_PROVIDER_VALIDATE_REQUEST
        and _OPENAI_PROVIDER_TYPE.generate is _OPENAI_PROVIDER_GENERATE
        and _OPENAI_PROVIDER_TYPE._validate_benchmark_request
        is _OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST
        and _OPENAI_PROVIDER_TYPE.generate_benchmark is _OPENAI_PROVIDER_GENERATE_BENCHMARK
        and normalize_provider_outcome is _NORMALIZE_PROVIDER_OUTCOME
        and normalize_public_benchmark_outcome is _NORMALIZE_PUBLIC_BENCHMARK_OUTCOME
        and _PROVIDER_CHECK_ALL(
            namespace.get(name) is expected
            for namespace, name, expected in _PROVIDER_EVIDENCE_BUILTIN_BINDINGS
        )
        and (
            _function_matches_seal,
            _class_matches_seal,
            _default_identity_seal,
            _kwdefault_identity_seal,
            _closure_identity_seal,
            _attribute_matches_seal,
            _descriptor_matches_seal,
            _module_namespace_matches_seal,
        )
        == _PROVIDER_CHECK_TUPLE(function for function, _code in _PROVIDER_RUNTIME_HELPER_ROOTS)
        and _PROVIDER_CHECK_ALL(
            function.__code__ is code for function, code in _PROVIDER_RUNTIME_HELPER_ROOTS
        )
        and _PROVIDER_CHECK_ALL(
            _module_namespace_matches_seal(seal)
            for seal in _PROVIDER_EVIDENCE_MODULE_NAMESPACE_SEALS
        )
        and _PROVIDER_CHECK_ALL(
            _attribute_matches_seal(seal) for seal in _PROVIDER_TRANSITIVE_ATTRIBUTE_SEALS
        )
        and _PROVIDER_CHECK_ALL(
            _descriptor_matches_seal(seal) for seal in _PROVIDER_INHERITED_DESCRIPTOR_SEALS
        )
        and _PROVIDER_CHECK_ALL(
            _class_matches_seal(class_seal.class_type, class_seal)
            for class_seal in _PROVIDER_EXACT_CLASS_SEALS
        )
        and _PROVIDER_CHECK_ALL(
            _function_matches_seal(function, seal)
            for function, seal in zip(
                class_functions,
                _PROVIDER_CLASS_FUNCTION_SEALS,
                strict=True,
            )
        )
        and _PROVIDER_CHECK_ALL(
            _function_matches_seal(getattr(module, name, None), seal)
            for module, seals in _PROVIDER_MODULE_FUNCTION_SEALS
            for name, seal in seals
        )
        and _PROVIDER_CHECK_ALL(
            _class_matches_seal(getattr(module, name, None), seal)
            for module, seals in _PROVIDER_MODULE_CLASS_SEALS
            for name, seal in seals
        )
        and _PROVIDER_CHECK_ALL(
            getattr(module, name, None) is expected
            for module, name, expected in _PROVIDER_GLOBAL_BINDINGS
        )
        and _PROVIDER_CHECK_ALL(
            getattr(module, name, None) is expected
            for module, name, expected in _PROVIDER_TRANSITIVE_GLOBAL_BINDINGS
        )
    )


def _make_captured_provider_runtime_check(
    namespace: dict[str, object],
    factory_type: type[ProviderFactory],
    original_create: FunctionType,
) -> tuple[Callable[[], bool], Callable[[FunctionType], None]]:
    """Capture adapter authority without trusting replaceable seal-table globals."""

    type_of = type
    dict_type = dict
    dict_get = dict.get
    all_of = all
    len_of = len
    getattr_of = getattr
    vars_of = vars
    tuple_of = tuple
    sorted_of = sorted
    function_type = FunctionType
    seal_function = _seal_function
    seal_class = _seal_class
    seal_attribute = _seal_attribute
    seal_descriptor = _seal_descriptor
    seal_module_namespace = _seal_module_namespace
    function_matches = _function_matches_seal
    class_matches = _class_matches_seal
    attribute_matches = _attribute_matches_seal
    descriptor_matches = _descriptor_matches_seal
    module_namespace_matches = _module_namespace_matches_seal
    default_identity_seal = _default_identity_seal
    kwdefault_identity_seal = _kwdefault_identity_seal
    closure_identity_seal = _closure_identity_seal
    function_globals = _function_globals
    raw_getattribute = object.__getattribute__
    zip_of = zip
    ordinary_exception = Exception
    fake_type = _FAKE_PROVIDER_TYPE
    replay_type = _REPLAY_PROVIDER_TYPE
    openai_type = _OPENAI_PROVIDER_TYPE
    normalize_provider = _NORMALIZE_PROVIDER_OUTCOME
    normalize_public_benchmark = _NORMALIZE_PUBLIC_BENCHMARK_OUTCOME
    openai_hashlib_module = _OPENAI_HASHLIB_MODULE
    openai_unicodedata_module = _OPENAI_UNICODEDATA_MODULE
    canonical_json_module = _CANONICAL_JSON_MODULE
    canonical_math_module = _CANONICAL_MATH_MODULE
    attempts_module = _attempts_module
    canonical_module = _canonical_module
    sanitizer_module = _sanitizer_module
    yaml_io_module = _yaml_io_module
    openai_provider_module = _openai_provider_module
    capsule_module = _capsule_module
    base_model = cast(type[object], BaseModel)
    adapter_class_seals = tuple_of(
        seal_class(class_type) for class_type in (fake_type, replay_type, openai_type)
    )
    adapter_functions = (
        _FAKE_PROVIDER_INIT,
        _FAKE_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_INIT,
        _REPLAY_PROVIDER_FROM_MAPPING,
        _REPLAY_PROVIDER_FROM_BYTES,
        _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES,
        _REPLAY_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _REPLAY_PROVIDER_GENERATE_BENCHMARK,
        _OPENAI_PROVIDER_INIT,
        _OPENAI_PROVIDER_VALIDATE_REQUEST,
        _OPENAI_PROVIDER_GENERATE,
        _OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _OPENAI_PROVIDER_GENERATE_BENCHMARK,
    )
    adapter_function_seals = tuple_of(seal_function(function) for function in adapter_functions)
    provider_modules = (
        _fake_provider_module,
        _replay_provider_module,
        _openai_provider_module,
        _attempts_module,
        _canonical_module,
        _sanitizer_module,
        _yaml_io_module,
    )
    module_function_seals = tuple_of(
        (module, _module_function_seals(module)) for module in provider_modules
    )
    module_class_seals = tuple_of(
        (module, _module_class_seals(module)) for module in provider_modules
    )
    evidence_modules = (
        attempts_module,
        canonical_module,
        sanitizer_module,
        yaml_io_module,
    )
    module_namespace_seals = tuple_of(seal_module_namespace(module) for module in evidence_modules)
    transitive_attribute_seals = tuple_of(
        seal_attribute(owner, name)
        for owner, name in (
            (vars_of(openai_provider_module)["hashlib"], "sha256"),
            (vars_of(openai_provider_module)["math"], "isfinite"),
            (vars_of(openai_provider_module)["re"], "fullmatch"),
            (vars_of(openai_provider_module)["unicodedata"], "normalize"),
            (vars_of(attempts_module)["hashlib"], "sha256"),
            (vars_of(attempts_module)["math"], "isfinite"),
            (vars_of(canonical_module)["hashlib"], "sha256"),
            (vars_of(canonical_module)["json"], "dumps"),
            (vars_of(canonical_module)["math"], "isfinite"),
            (vars_of(sanitizer_module)["hashlib"], "sha256"),
            (vars_of(sanitizer_module)["heapq"], "heappop"),
            (vars_of(sanitizer_module)["heapq"], "heappush"),
            (vars_of(yaml_io_module)["yaml"], "SafeLoader"),
            (vars_of(yaml_io_module)["yaml"], "compose"),
            (vars_of(yaml_io_module)["yaml"], "load"),
            (vars_of(yaml_io_module)["yaml"], "parse"),
            (vars_of(yaml_io_module)["yaml"], "scan"),
        )
    )
    inherited_descriptor_seals = tuple_of(
        seal_descriptor(base_model, name) for name in ("model_dump", "model_validate")
    )
    runtime_helper_roots = tuple_of(
        (name, function, raw_getattribute(function, "__code__"))
        for name, function in (
            ("_function_matches_seal", function_matches),
            ("_class_matches_seal", class_matches),
            ("_default_identity_seal", default_identity_seal),
            ("_kwdefault_identity_seal", kwdefault_identity_seal),
            ("_closure_identity_seal", closure_identity_seal),
            ("_attribute_matches_seal", attribute_matches),
            ("_descriptor_matches_seal", descriptor_matches),
            ("_module_namespace_matches_seal", module_namespace_matches),
        )
    )
    provider_global_bindings = tuple_of(
        (module, name, getattr_of(module, name))
        for module, names in (
            (
                _fake_provider_module,
                ("FakeProvider", "GenerationRequest", "GenerationResult", "ProviderError"),
            ),
            (
                _replay_provider_module,
                (
                    "GenerationRequest",
                    "GenerationResult",
                    "Mapping",
                    "Path",
                    "ProviderError",
                    "PublicBenchmarkRequestPolicyV1",
                    "PublicBenchmarkRequestV1",
                    "RESOURCE_LIMITS_V1",
                    "ReplayProvider",
                    "TokenUsage",
                    "YAMLError",
                    "_BENCHMARK_CACHE_FIELDS",
                    "_BENCHMARK_ERROR_FIELDS",
                    "_BENCHMARK_INPUT_DETAIL_FIELDS",
                    "_BENCHMARK_MESSAGE_FIELDS",
                    "_BENCHMARK_MODEL_IDS",
                    "_BENCHMARK_OUTPUT_DETAIL_FIELDS",
                    "_BENCHMARK_OUTPUT_TEXT_FIELDS",
                    "_BENCHMARK_RAW_RESPONSE_PATHS",
                    "_BENCHMARK_RESPONSE_FIELDS",
                    "_BENCHMARK_ROW_FIELDS",
                    "_BENCHMARK_SOURCE_DIGEST_FIELDS",
                    "_BENCHMARK_USAGE_FIELDS",
                    "safe_load_unique",
                    "safe_load_unique_bytes",
                ),
            ),
            (
                _openai_provider_module,
                (
                    "GenerationRequest",
                    "GenerationResult",
                    "OpenAIProvider",
                    "ProviderError",
                    "PublicBenchmarkRequestPolicyV1",
                    "PublicBenchmarkRequestV1",
                    "ReasoningTokenAccounting",
                    "RESOURCE_LIMITS_V1",
                    "ServiceTierStatus",
                    "TokenUsage",
                    "Any",
                    "AppliedCacheControlStatus",
                    "CacheReadStatus",
                    "CacheWriteStatus",
                    "DeliveryCertainty",
                    "Mapping",
                    "_MISSING_RESPONSE_MEMBER",
                    "_PUBLIC_BENCHMARK_RAW_RESPONSE_PATHS",
                    "_PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS",
                    "_canonical_json_v1",
                    "bounded_utf8_length",
                    "cast",
                    "conservative_input_token_bound",
                    "hashlib",
                    "laconian_eval",
                    "math",
                    "os",
                    "re",
                    "suppress",
                    "typing",
                    "unicodedata",
                ),
            ),
            (
                attempts_module,
                (
                    "AttemptUsageV2",
                    "PublicBenchmarkProviderErrorEvidenceV1",
                    "PublicBenchmarkProviderOutcomeV1",
                    "PublicBenchmarkRawResponseSourceEntryV1",
                    "PublicBenchmarkRawResponseSourceV1",
                    "PublicBenchmarkResponseEvidenceV1",
                    "public_benchmark_provider_error_source_sha256",
                    "public_benchmark_raw_response_sha256",
                ),
            ),
        )
        for name in names
    )
    transitive_global_bindings = (
        *tuple_of(
            (module, name, value)
            for module in (
                attempts_module,
                _canonical_module,
                _sanitizer_module,
                _yaml_io_module,
            )
            for name, value in sorted_of(
                vars_of(module).items(),
                key=lambda item: item[0].encode("utf-8"),
            )
            if not name.startswith("__")
        ),
        (
            openai_hashlib_module,
            "sha256",
            openai_hashlib_module.sha256,
        ),
        (
            openai_unicodedata_module,
            "normalize",
            openai_unicodedata_module.normalize,
        ),
        (canonical_json_module, "dumps", canonical_json_module.dumps),
        (canonical_math_module, "isfinite", canonical_math_module.isfinite),
        (capsule_module, "attempts", attempts_module),
    )
    execution_bindings = (
        ("ProviderFactory", factory_type),
        ("FakeProvider", fake_type),
        ("ReplayProvider", replay_type),
        ("OpenAIProvider", openai_type),
        ("_FAKE_PROVIDER_TYPE", fake_type),
        ("_REPLAY_PROVIDER_TYPE", replay_type),
        ("_OPENAI_PROVIDER_TYPE", openai_type),
        ("normalize_provider_outcome", normalize_provider),
        ("normalize_public_benchmark_outcome", normalize_public_benchmark),
        ("_NORMALIZE_PROVIDER_OUTCOME", normalize_provider),
        ("_NORMALIZE_PUBLIC_BENCHMARK_OUTCOME", normalize_public_benchmark),
        ("_OPENAI_HASHLIB_MODULE", openai_hashlib_module),
        ("_OPENAI_UNICODEDATA_MODULE", openai_unicodedata_module),
        ("_CANONICAL_JSON_MODULE", canonical_json_module),
        ("_CANONICAL_MATH_MODULE", canonical_math_module),
        ("_FAKE_PROVIDER_INIT", adapter_functions[0]),
        ("_FAKE_PROVIDER_GENERATE", adapter_functions[1]),
        ("_REPLAY_PROVIDER_INIT", adapter_functions[2]),
        ("_REPLAY_PROVIDER_FROM_MAPPING", adapter_functions[3]),
        ("_REPLAY_PROVIDER_FROM_BYTES", adapter_functions[4]),
        ("_REPLAY_PROVIDER_FROM_BENCHMARK_BYTES", adapter_functions[5]),
        ("_REPLAY_PROVIDER_GENERATE", adapter_functions[6]),
        ("_REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST", adapter_functions[7]),
        ("_REPLAY_PROVIDER_GENERATE_BENCHMARK", adapter_functions[8]),
        ("_OPENAI_PROVIDER_INIT", adapter_functions[9]),
        ("_OPENAI_PROVIDER_VALIDATE_REQUEST", adapter_functions[10]),
        ("_OPENAI_PROVIDER_GENERATE", adapter_functions[11]),
        ("_OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST", adapter_functions[12]),
        ("_OPENAI_PROVIDER_GENERATE_BENCHMARK", adapter_functions[13]),
        ("_function_matches_seal", function_matches),
        ("_class_matches_seal", class_matches),
        ("_attribute_matches_seal", attribute_matches),
        ("_descriptor_matches_seal", descriptor_matches),
        ("_module_namespace_matches_seal", module_namespace_matches),
        ("_default_identity_seal", default_identity_seal),
        ("_kwdefault_identity_seal", kwdefault_identity_seal),
        ("_closure_identity_seal", closure_identity_seal),
        ("_function_globals", function_globals),
        ("FunctionType", function_type),
    )
    builtins_namespace = cast(
        dict[str, object],
        object.__getattribute__(original_create, "__builtins__"),
    )
    evidence_builtin_bindings = tuple_of(
        (name, builtins_namespace[name]) for name in _PROVIDER_EVIDENCE_BUILTIN_NAMES
    )
    builtin_resolutions = tuple_of(
        (name, dict_get(namespace, name, builtins_namespace[name]))
        for name in (
            "all",
            "any",
            "classmethod",
            "dict",
            "Exception",
            "getattr",
            "id",
            "len",
            "object",
            "property",
            "sorted",
            "staticmethod",
            "str",
            "sum",
            "tuple",
            "type",
            "vars",
            "zip",
        )
    )
    original_create_seal = seal_function(original_create)
    factory_state: list[tuple[FunctionType, _FunctionSeal, _ClassSeal]] = []
    runtime_closure_state: list[
        tuple[Callable[[], bool], tuple[tuple[str, object, type[object]], ...]]
    ] = []

    def install_factory_create(function: FunctionType) -> None:
        if factory_state or type_of(function) is not function_type:
            raise TypeError
        factory_state.append(
            (
                function,
                seal_function(function),
                seal_class(factory_type),
            )
        )

    def runtime_intact() -> bool:
        try:
            # This state cell is the sole exclusion: it owns both the self-reference and
            # the finite expected seal. Every other closure cell is checked without the
            # compositional helpers that the closure itself is responsible for validating.
            runtime_function, runtime_closure_seal = runtime_closure_state[0]
            runtime_closure = raw_getattribute(runtime_function, "__closure__")
            runtime_code = raw_getattribute(runtime_function, "__code__")
            runtime_freevars = raw_getattribute(runtime_code, "co_freevars")
            if (
                type_of(runtime_closure) is not tuple_of
                or type_of(runtime_freevars) is not tuple_of
                or len_of(runtime_closure) != len_of(runtime_freevars)
            ):
                return False
            closure_index = 0
            seal_index = 0
            while closure_index < len_of(runtime_freevars):
                name = runtime_freevars[closure_index]
                cell = runtime_closure[closure_index]
                closure_index += 1
                if name == "runtime_closure_state":
                    continue
                if seal_index >= len_of(runtime_closure_seal):
                    return False
                expected_name, expected_value, expected_type = runtime_closure_seal[seal_index]
                seal_index += 1
                value = raw_getattribute(cell, "cell_contents")
                if (
                    name != expected_name
                    or value is not expected_value
                    or type_of(value) is not expected_type
                ):
                    return False
            if seal_index != len_of(runtime_closure_seal):
                return False
            if type_of(namespace) is not dict_type or len_of(factory_state) != 1:
                return False
            factory_create, factory_create_seal, factory_class_seal = factory_state[0]
            return (
                all_of(
                    dict_get(namespace, name) is expected for name, expected in execution_bindings
                )
                and dict_get(namespace, "_UNGUARDED_PROVIDER_FACTORY_CREATE") is original_create
                and dict_get(namespace, "_PROVIDER_FACTORY_CREATE") is factory_create
                and all_of(
                    dict_get(namespace, name, expected) is expected
                    for name, expected in builtin_resolutions
                )
                and all_of(
                    dict_get(builtins_namespace, name) is expected
                    for name, expected in evidence_builtin_bindings
                )
                and all_of(
                    dict_get(namespace, name) is function
                    and type_of(function) is function_type
                    and raw_getattribute(function, "__code__") is code
                    for name, function, code in runtime_helper_roots
                )
                and class_matches(factory_type, factory_class_seal)
                and function_matches(factory_create, factory_create_seal)
                and function_matches(original_create, original_create_seal)
                and all_of(module_namespace_matches(seal) for seal in module_namespace_seals)
                and all_of(attribute_matches(seal) for seal in transitive_attribute_seals)
                and all_of(descriptor_matches(seal) for seal in inherited_descriptor_seals)
                and all_of(
                    class_matches(class_seal.class_type, class_seal)
                    for class_seal in adapter_class_seals
                )
                and all_of(
                    function_matches(function, seal)
                    for function, seal in zip_of(
                        adapter_functions,
                        adapter_function_seals,
                        strict=True,
                    )
                )
                and all_of(
                    function_matches(getattr_of(module, name, None), seal)
                    for module, seals in module_function_seals
                    for name, seal in seals
                )
                and all_of(
                    class_matches(getattr_of(module, name, None), seal)
                    for module, seals in module_class_seals
                    for name, seal in seals
                )
                and all_of(
                    getattr_of(module, name, None) is expected
                    for module, name, expected in provider_global_bindings
                )
                and all_of(
                    getattr_of(module, name, None) is expected
                    for module, name, expected in transitive_global_bindings
                )
            )
        except ordinary_exception:
            return False

    runtime_closure = raw_getattribute(runtime_intact, "__closure__")
    runtime_freevars = raw_getattribute(
        raw_getattribute(runtime_intact, "__code__"),
        "co_freevars",
    )
    if (
        type_of(runtime_closure) is not tuple_of
        or type_of(runtime_freevars) is not tuple_of
        or len_of(runtime_closure) != len_of(runtime_freevars)
    ):
        raise TypeError
    runtime_closure_state.append(
        (
            runtime_intact,
            tuple_of(
                (
                    name,
                    raw_getattribute(cell, "cell_contents"),
                    type_of(raw_getattribute(cell, "cell_contents")),
                )
                for name, cell in zip_of(runtime_freevars, runtime_closure, strict=True)
                if name != "runtime_closure_state"
            ),
        )
    )
    return runtime_intact, install_factory_create


def _guard_provider_factory_create(
    original_create: Callable[[ProviderFactory, ProviderFactoryRequest], ProviderBinding],
    runtime_check: FunctionType,
) -> Callable[[ProviderFactory, ProviderFactoryRequest], ProviderBinding]:
    """Bind the original integrity checker so rebinding its module name cannot bypass it."""

    function_type = FunctionType
    type_of = type
    all_of = all
    bool_type = bool
    dict_type = dict
    dict_get = dict.get
    raw_getattribute = object.__getattribute__
    ordinary_exception = Exception
    unavailable_type = ProviderUnavailable
    original_seal = (
        original_create.__code__,
        original_create.__defaults__,
        original_create.__kwdefaults__,
        original_create.__closure__,
        original_create.__globals__,
        raw_getattribute(original_create, "__builtins__"),
    )
    runtime_seal = (
        runtime_check.__code__,
        runtime_check.__defaults__,
        runtime_check.__kwdefaults__,
        runtime_check.__closure__,
        runtime_check.__globals__,
        raw_getattribute(runtime_check, "__builtins__"),
    )
    builtins_namespace = cast(dict[str, object], runtime_seal[5])
    builtin_roots = tuple(
        (name, builtins_namespace[name]) for name in ("all", "classmethod", "tuple", "type", "zip")
    )

    def matches(function: object, seal: tuple[object, ...]) -> bool:
        return (
            type_of(function) is function_type
            and raw_getattribute(function, "__code__") is seal[0]
            and raw_getattribute(function, "__defaults__") is seal[1]
            and raw_getattribute(function, "__kwdefaults__") is seal[2]
            and raw_getattribute(function, "__closure__") is seal[3]
            and raw_getattribute(function, "__globals__") is seal[4]
            and raw_getattribute(function, "__builtins__") is seal[5]
        )

    def guarded_create(
        self: ProviderFactory,
        request: ProviderFactoryRequest,
    ) -> ProviderBinding:
        try:
            namespace = runtime_seal[4]
            intact = (
                type_of(namespace) is dict_type
                and matches(original_create, original_seal)
                and matches(runtime_check, runtime_seal)
                and all_of(
                    dict_get(namespace, name, expected) is expected
                    for name, expected in builtin_roots
                )
                and runtime_check()
            )
        except ordinary_exception:
            intact = False
        if type_of(intact) is not bool_type or not intact:
            raise unavailable_type()
        return original_create(self, request)

    return guarded_create


_UNGUARDED_PROVIDER_FACTORY_CREATE = ProviderFactory.create
(
    _CAPTURED_PROVIDER_RUNTIME_CHECK,
    _install_provider_factory_runtime_seal,
) = _make_captured_provider_runtime_check(
    globals(),
    ProviderFactory,
    cast(FunctionType, _UNGUARDED_PROVIDER_FACTORY_CREATE),
)
ProviderFactory.create = _guard_provider_factory_create(  # type: ignore[assignment]
    _UNGUARDED_PROVIDER_FACTORY_CREATE,
    cast(FunctionType, _CAPTURED_PROVIDER_RUNTIME_CHECK),
)
_PROVIDER_FACTORY_CREATE = ProviderFactory.create
_install_provider_factory_runtime_seal(cast(FunctionType, _PROVIDER_FACTORY_CREATE))
del _install_provider_factory_runtime_seal
_PROVIDER_EXACT_CLASS_SEALS = tuple(
    _seal_class(class_type)
    for class_type in (
        ProviderFactory,
        _FAKE_PROVIDER_TYPE,
        _REPLAY_PROVIDER_TYPE,
        _OPENAI_PROVIDER_TYPE,
    )
)
_PROVIDER_CLASS_FUNCTION_SEALS = tuple(
    _seal_function(function)
    for function in (
        _PROVIDER_FACTORY_CREATE,
        _UNGUARDED_PROVIDER_FACTORY_CREATE,
        _FAKE_PROVIDER_INIT,
        _FAKE_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_INIT,
        _REPLAY_PROVIDER_FROM_MAPPING,
        _REPLAY_PROVIDER_FROM_BYTES,
        _REPLAY_PROVIDER_FROM_BENCHMARK_BYTES,
        _REPLAY_PROVIDER_GENERATE,
        _REPLAY_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _REPLAY_PROVIDER_GENERATE_BENCHMARK,
        _OPENAI_PROVIDER_INIT,
        _OPENAI_PROVIDER_VALIDATE_REQUEST,
        _OPENAI_PROVIDER_GENERATE,
        _OPENAI_PROVIDER_VALIDATE_BENCHMARK_REQUEST,
        _OPENAI_PROVIDER_GENERATE_BENCHMARK,
    )
)


@dataclass(frozen=True, slots=True)
class _PrivateProviderBinding:
    provider: Provider | PublicBenchmarkProvider = field(repr=False)
    credential_values: tuple[str, ...] = field(default=(), repr=False)


@dataclass(slots=True)
class _ExecutionCheckpointDispatch:
    complete: Callable[..., None] = field(repr=False)
    complete_seal: _FunctionSeal = field(repr=False)
    runtime: Callable[..., None] = field(repr=False)
    runtime_seal: _FunctionSeal = field(repr=False)
    revalidate: Callable[[_MutatorSessionV1], object] = field(repr=False)
    revalidate_seal: _FunctionSeal = field(repr=False)
    integrity: Callable[[], bool] = field(repr=False)
    integrity_seal: _FunctionSeal = field(repr=False)
    matches: Callable[[object, _FunctionSeal], bool] = field(repr=False)
    seal: Callable[[object], _FunctionSeal] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _ResumeOutcome:
    result: VerifyResultV1
    exit_code: Literal[0, 1, 2]
    code: ResumeCode


@dataclass(slots=True)
class _CapacityBudget:
    """Lock-scoped reservation for one epoch and its next complete attempt."""

    current_capsule_bytes: int
    raw_rows: int
    reserved_bytes: int = 0
    poisoned: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.current_capsule_bytes) is not int
            or self.current_capsule_bytes < 0
            or type(self.raw_rows) is not int
            or self.raw_rows < 0
            or type(self.reserved_bytes) is not int
            or self.reserved_bytes < 0
            or type(self.poisoned) is not bool
        ):
            raise ResumeError("invalid_capacity_budget")

    def _require_total(self, required: int) -> None:
        exceeds_limit = (
            self.current_capsule_bytes + required > RESOURCE_LIMITS_V1.mutable_capsule_bytes
        )
        if self.poisoned or exceeds_limit:
            raise ResumeError("resource_limit")

    def _reserve_at_least(self, required: int) -> None:
        self._require_total(max(self.reserved_bytes, required))
        self.reserved_bytes = max(self.reserved_bytes, required)

    def reserve_epoch_and_first_attempt(self) -> None:
        if self.raw_rows + 1 > RESOURCE_LIMITS_V1.raw_rows:
            raise ResumeError("resource_limit")
        try:
            target = reserve_attempt_transaction(
                self.current_capsule_bytes,
                reserved_bytes=self.reserved_bytes,
                include_epoch_events=True,
            )
        except ResourceLimitError:
            raise ResumeError("resource_limit") from None
        self._reserve_at_least(target)

    def reserve_next_attempt(self) -> None:
        if self.raw_rows + 1 > RESOURCE_LIMITS_V1.raw_rows:
            raise ResumeError("resource_limit")
        try:
            target = reserve_attempt_transaction(
                self.current_capsule_bytes,
                reserved_bytes=self.reserved_bytes,
            )
        except ResourceLimitError:
            raise ResumeError("resource_limit") from None
        self._reserve_at_least(target)

    def consume_exact(self, encoded_length: int, raw_delta: int) -> None:
        if (
            self.poisoned
            or type(encoded_length) is not int
            or encoded_length <= 0
            or type(raw_delta) is not int
            or raw_delta not in (0, 1)
            or encoded_length > self.reserved_bytes
            or self.raw_rows + raw_delta > RESOURCE_LIMITS_V1.raw_rows
        ):
            self.poisoned = True
            raise ResumeError("capacity_budget_mismatch")
        self.current_capsule_bytes += encoded_length
        self.reserved_bytes -= encoded_length
        self.raw_rows += raw_delta

    def release_attempt_headroom(self) -> None:
        if self.poisoned:
            raise ResumeError("capacity_budget_mismatch")
        self.reserved_bytes = min(self.reserved_bytes, 2 * _EVENT_ROW_RESERVATION)

    def poison(self) -> None:
        self.poisoned = True


RuntimeCheckpoint = Callable[[InstalledProvenance, ImportPolicy, EnvironmentV1], None]
PrivateProviderFactory = Callable[[ProviderFactoryRequest], _PrivateProviderBinding]
StopBeforeAttempt = Callable[[PlanRowV1], Literal["signal", "operator"] | None]


@dataclass(frozen=True, slots=True)
class _ExecutionSeams:
    new_uuid: Callable[[], UUID] = uuid4
    utc_now: Callable[[], datetime] = lambda: datetime.now(UTC)
    monotonic_ns: Callable[[], int] = time.monotonic_ns
    sleeper: Callable[[float], None] = time.sleep
    install_guard: Callable[[ImportPolicy], object] = install_import_guard
    checkpoint: RuntimeCheckpoint | None = None
    stop_before_attempt: StopBeforeAttempt = lambda _row: None
    private_provider_factory: PrivateProviderFactory | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class _RuntimeAuthority:
    provenance: InstalledProvenance = field(repr=False)
    policy: ImportPolicy = field(repr=False)
    filesystem_class: str
    session_environment: SessionEnvironmentV1


@dataclass(frozen=True, slots=True)
class _CapturedRequest:
    row: PlanRowV1
    case: ResponseCase
    instruction: str | None
    request: GenerationRequest | PublicBenchmarkRequestV1


def _fail(code: str) -> NoReturn:
    raise ResumeError(code)


def _require_fresh_execution_guard(seams: _ExecutionSeams) -> None:
    if seams.install_guard is install_import_guard and _REAL_GUARD_STATE != "fresh":
        raise ResumeError("execution_process_not_fresh")


def _install_execution_guard(policy: ImportPolicy, seams: _ExecutionSeams) -> None:
    global _REAL_GUARD_STATE
    if seams.install_guard is not install_import_guard:
        seams.install_guard(policy)
        return
    if _REAL_GUARD_STATE != "fresh":
        raise ResumeError("execution_process_not_fresh")
    _REAL_GUARD_STATE = "installing"
    try:
        seams.install_guard(policy)
    except BaseException:
        _REAL_GUARD_STATE = "poisoned"
        raise
    _REAL_GUARD_STATE = "installed"


def _uuid4(value: object, *, code: str) -> UUID:
    if (
        type(value) is not UUID
        or type(value.int) is not int
        or value.version != 4
        or value.variant != RFC_4122
    ):
        _fail(code)
    return value


def _timestamp(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        _fail("invalid_clock")
    try:
        normalized = value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        _fail("invalid_clock")
    if normalized.utcoffset() != UTC.utcoffset(normalized):
        _fail("invalid_clock")
    return normalized


def _python_major_minor(value: str) -> tuple[int, int]:
    try:
        head = value.split(maxsplit=1)[0]
        major, minor, *_rest = head.split(".")
        return int(major), int(minor)
    except Exception:
        _fail("producer_runtime_differs")


def _blocking_runtime_matches(live: EnvironmentV1, captured: EnvironmentV1) -> bool:
    """Compare producer identity while retaining current diagnostic platform disclosure."""

    return (
        live.package_name == captured.package_name
        and live.package_version == captured.package_version
        and live.runner_source_sha256 == captured.runner_source_sha256
        and live.runtime.runtime_fingerprint_sha256 == captured.runtime.runtime_fingerprint_sha256
        and live.runtime.dependencies == captured.runtime.dependencies
        and live.runtime.import_environment == captured.runtime.import_environment
        and live.provider == captured.provider
        and live.runtime.python_implementation == captured.runtime.python_implementation
        and _python_major_minor(live.runtime.python_version)
        == _python_major_minor(captured.runtime.python_version)
    )


def _capture_runtime_authority(
    context: _VerifiedCapsuleContext,
    *,
    authored_input_byte_count: int,
    filesystem_class: str,
    _runtime_integrity_check: Callable[[], bool] = _CAPTURED_PROVIDER_RUNTIME_CHECK,
) -> _RuntimeAuthority:
    try:
        if not _runtime_integrity_check():
            raise ResumeError("producer_runtime_differs")
        provenance = capture_resume_provenance(
            context.manifest,
            authored_input_byte_count=authored_input_byte_count,
        )
        policy = build_import_policy(provenance)
        revalidate_import_environment(policy, context.environment.runtime.import_environment)
        revalidate_import_state(policy, require_guard=False)
        live = project_environment(
            provenance,
            import_environment=policy.import_environment,
            filesystem_class=filesystem_class,
        )
    except (ImportPolicyError, ProvenanceError, TypeError, ValueError):
        raise ResumeError("producer_runtime_differs") from None
    if not _blocking_runtime_matches(live, context.environment):
        raise ResumeError("producer_runtime_differs")
    provider = context.environment.provider
    runtime = live.runtime
    try:
        session_environment = SessionEnvironmentV1.model_validate(
            {
                "schema_version": "1",
                "package_version": live.package_version,
                "runner_source_sha256": live.runner_source_sha256,
                "runtime_fingerprint_sha256": runtime.runtime_fingerprint_sha256,
                "python_implementation": runtime.python_implementation,
                "python_version": runtime.python_version,
                "os_family": runtime.os_family,
                "os_release": runtime.os_release,
                "architecture": runtime.architecture,
                "filesystem_class": filesystem_class,
                "adapter_source_sha256": provider.adapter_source_sha256,
                "sdk_distribution": provider.sdk_distribution,
                "sdk_version": provider.sdk_version,
            }
        )
    except Exception:
        raise ResumeError("producer_runtime_differs") from None
    return _RuntimeAuthority(provenance, policy, filesystem_class, session_environment)


def _runtime_checkpoint(
    authority: _RuntimeAuthority,
    context: _VerifiedCapsuleContext,
    *,
    authored_input_byte_count: int,
    seams: _ExecutionSeams,
    _runtime_integrity_check: Callable[[], bool] = _CAPTURED_PROVIDER_RUNTIME_CHECK,
) -> None:
    try:
        if not _runtime_integrity_check():
            raise ResumeError("producer_runtime_differs")
        live_provenance = capture_resume_provenance(
            context.manifest,
            authored_input_byte_count=authored_input_byte_count,
        )
        live = project_environment(
            live_provenance,
            import_environment=authority.policy.import_environment,
            filesystem_class=authority.filesystem_class,
        )
        if not _blocking_runtime_matches(live, context.environment):
            raise ResumeError("producer_runtime_differs")
        if seams.checkpoint is None:
            revalidate_import_policy(
                authority.policy,
                environment=context.environment.runtime.import_environment,
            )
        else:
            seams.checkpoint(live_provenance, authority.policy, context.environment)
    except ResumeError:
        raise
    except (ImportPolicyError, ProvenanceError, TypeError, ValueError):
        raise ResumeError("producer_runtime_differs") from None


def _complete_execution_checkpoint(
    session: _MutatorSessionV1,
    authority: _RuntimeAuthority,
    context: _VerifiedCapsuleContext,
    *,
    authored_input_byte_count: int,
    seams: _ExecutionSeams,
    dispatch: _ExecutionCheckpointDispatch,
) -> None:
    """Revalidate the exact capsule and installed runtime at one call boundary."""

    dispatch.runtime(
        authority,
        context,
        authored_input_byte_count=authored_input_byte_count,
        seams=seams,
    )
    try:
        dispatch.revalidate(session)
    except (RecoveryError, JournalError):
        raise ResumeError("producer_runtime_differs") from None


def _verified_context(session: _MutatorSessionV1) -> _VerifiedCapsuleContext:
    try:
        source = session.verified._source
        if type(source) is not _VerifiedRecoveryContext:
            raise TypeError
        context = source.context
        if type(context) is not _VerifiedCapsuleContext:
            raise TypeError
        # Rebuild the class-bound history context so forged private attributes cannot authorize
        # execution even if a test bypasses the public factory boundary.
        rebound = HistoryContextV1(
            context.capsule,
            context.manifest,
            context.environment,
            context.plan,
        )
        if rebound != session.history_context:
            raise TypeError
        return context
    except Exception:
        raise ResumeError("invalid_verified_context") from None


def _authored_input_byte_count(context: _VerifiedCapsuleContext) -> int:
    total = 0
    for captured in context.captured.files:
        record = captured.record
        if record.role in _AUTHORED_INPUT_ROLES:
            total += record.byte_length
    if total < 0 or total > RESOURCE_LIMITS_V1.captured_input_total_bytes:
        _fail("resource_limit")
    return total


def _result_for_lifecycle(
    context: _VerifiedCapsuleContext,
    lifecycle: LifecycleProjectionV1,
    *,
    producer_runtime_differs: bool = False,
) -> VerifyResultV1:
    warnings = list(context.warnings)
    if (
        producer_runtime_differs or context.capsule.runner_version != __version__
    ) and "producer_runtime_differs" not in warnings:
        warnings.append("producer_runtime_differs")
    return VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": "valid",
            "run_id": context.capsule.run_id,
            "state": lifecycle.state,
            "capsule_sha256": None,
            "missing_plan_item_ids": lifecycle.missing_plan_item_ids,
            "operational_blocker_codes": lifecycle.operational_blocker_codes,
            "warnings": warnings,
            "first_error": None,
        }
    )


def _pair(
    transaction: JournalTransaction,
    history_context: HistoryContextV1,
) -> JournalPairSnapshotV1:
    return _snapshot_transaction_pair(
        transaction,
        history_context=history_context,
        tail_policy="reject",
        reserved_operation_id=None,
    )


def _captured_request(
    context: _VerifiedCapsuleContext,
    row: PlanRowV1,
) -> _CapturedRequest:
    try:
        index_rows = tuple(item for item in context.case_index if item.case_uid == row.case_uid)
        if len(index_rows) != 1:
            raise TypeError
        index = index_rows[0]
        case_file = context.captured.case_files[index.source_ordinal]
        case = case_file.cases[index.record_ordinal]
        if type(case) is not ResponseCase:
            raise TypeError
        arms = tuple(item for item in context.captured.arms if item.name == row.arm)
        if len(arms) != 1:
            raise TypeError
        arm = arms[0]
        prompt_sha = hashlib.sha256(case.prompt.encode("utf-8", errors="strict")).hexdigest()
        definition_sha = response_case_sha256(case)
        instruction_bytes = b"" if arm.instruction is None else arm.instruction.encode("utf-8")
        instruction_sha = sha256_bytes(instruction_bytes)
        config_sha = request_config_sha256(context.manifest)
        expected_item = plan_item_id(
            context.capsule.run_id,
            row.case_uid,
            row.repetition,
            row.arm,
            instruction_sha,
            config_sha,
        )
        if (
            case.id != row.case_id
            or case.locale != row.locale
            or index.prompt_sha256 != row.prompt_sha256
            or index.case_definition_sha256 != row.case_definition_sha256
            or prompt_sha != row.prompt_sha256
            or definition_sha != row.case_definition_sha256
            or instruction_sha != row.instruction_sha256
            or config_sha != row.request_config_sha256
            or expected_item != row.plan_item_id
        ):
            raise TypeError
        manifest = context.manifest
        if manifest.provider.model in {
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
        }:
            policy = PublicBenchmarkRequestPolicyV1(
                schema_version="PublicBenchmarkRequestPolicyV1",
                reasoning_mode=manifest.generation.reasoning_mode,
                prompt_cache_mode=manifest.generation.prompt_cache_mode,
                prompt_cache_ttl=manifest.generation.prompt_cache_ttl,
                service_tier=manifest.generation.service_tier,
                input_token_bound_version="openai-utf8-envelope-v1",
                max_input_tokens=272_000,
            )
            request: GenerationRequest | PublicBenchmarkRequestV1 = PublicBenchmarkRequestV1(
                case_id=row.case_id,
                arm=row.arm,
                repetition=row.repetition,
                requested_model_id=cast(PublicBenchmarkModelId, manifest.provider.model),
                instructions=arm.instruction,
                prompt=case.prompt,
                max_output_tokens=manifest.generation.max_output_tokens,
                temperature=manifest.generation.temperature,
                timeout_seconds=manifest.retry.timeout_seconds,
                policy=policy,
                reasoning_effort=manifest.generation.reasoning_effort,
                text_verbosity=manifest.generation.text_verbosity,
            )
        else:
            request = GenerationRequest(
                case_id=row.case_id,
                arm=row.arm,
                repetition=row.repetition,
                model=manifest.provider.model,
                instructions=arm.instruction,
                prompt=case.prompt,
                max_output_tokens=manifest.generation.max_output_tokens,
                temperature=manifest.generation.temperature,
                timeout_seconds=manifest.retry.timeout_seconds,
            )
        return _CapturedRequest(row, case, arm.instruction, request)
    except Exception:
        raise ResumeError("captured_request_mismatch") from None


def _derive_captured_request(
    context: _VerifiedCapsuleContext,
    plan_ordinal: int,
) -> _CapturedRequest:
    """Testable captured-only projection for exactly one materialized plan ordinal."""

    if type(plan_ordinal) is not int or not 0 <= plan_ordinal < len(context.plan):
        raise ResumeError("captured_request_mismatch")
    return _captured_request(context, context.plan[plan_ordinal])


def _provider_request(context: _VerifiedCapsuleContext) -> ProviderFactoryRequest:
    replay = tuple(item.data for item in context.captured.files if item.record.role == "replay")
    manifest = context.manifest
    environment = context.environment.provider
    captured_replay: bytes | None
    if manifest.provider.kind == "replay":
        if len(replay) != 1:
            _fail("captured_request_mismatch")
        captured_replay = replay[0]
    else:
        if replay:
            _fail("captured_request_mismatch")
        captured_replay = None
    return ProviderFactoryRequest(
        provider_kind=manifest.provider.kind,
        requested_model=manifest.provider.model,
        api_key_env=manifest.provider.api_key_env,
        timeout_seconds=manifest.retry.timeout_seconds,
        adapter_source_sha256=environment.adapter_source_sha256,
        transport_policy=environment.transport_policy,
        sdk_distribution=environment.sdk_distribution,
        sdk_version=environment.sdk_version,
        captured_replay_bytes=captured_replay,
    )


def _descriptor_resolved_path(descriptor: int) -> str | None:
    try:
        if sys.platform == "darwin":
            command = getattr(fcntl, "F_GETPATH", 50)
            raw = fcntl.fcntl(descriptor, command, b"\0" * 1024)
            if type(raw) is not bytes or b"\0" not in raw:
                return None
            value = raw.split(b"\0", 1)[0].decode("utf-8", errors="strict")
        else:
            value = os.readlink(f"/proc/self/fd/{descriptor}")
        return value if value.startswith(os.sep) else None
    except (OSError, TypeError, ValueError, UnicodeError):
        return None


def _opened_directory_patterns(lexical: str) -> tuple[str, ...]:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            lexical,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY,
        )
        resolved = _descriptor_resolved_path(descriptor)
    except (OSError, TypeError, ValueError):
        resolved = None
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
    return tuple(dict.fromkeys(value for value in (lexical, resolved) if value))


def _sanitizer_patterns(
    path: Path,
    root_fd: int,
    credential_values: tuple[str, ...],
) -> SanitizerPatterns:
    def optional(call: Callable[[], str]) -> tuple[str, ...]:
        try:
            value = call()
        except Exception:
            return ()
        return (value,) if type(value) is str and value else ()

    lexical = os.fspath(path)
    resolved = _descriptor_resolved_path(root_fd)
    capsule_roots = tuple(dict.fromkeys(value for value in (lexical, resolved) if value))
    raw_hostname = optional(socket.gethostname)
    raw_fqdn = optional(socket.getfqdn)
    hostname_values: list[str] = []
    for value in raw_hostname:
        normalized = value[:-1] if value.endswith(".") else value
        if normalized:
            hostname_values.append(normalized)
            prefix = normalized.split(".", 1)[0]
            if prefix:
                hostname_values.append(prefix)
    fqdn = tuple(
        dict.fromkeys(
            value[:-1] if value.endswith(".") else value for value in raw_fqdn if value.rstrip(".")
        )
    )
    try:
        passwd = pwd.getpwuid(os.geteuid())
        home = passwd.pw_dir if type(passwd.pw_dir) is str else ""
        username = passwd.pw_name if type(passwd.pw_name) is str else ""
    except (KeyError, OSError, TypeError, ValueError):
        home = ""
        username = ""
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    return SanitizerPatterns(
        credential_values=credential_values,
        capsule_roots=capsule_roots,
        source_roots=(),
        input_roots=(),
        cwd_roots=_opened_directory_patterns(cwd) if cwd else (),
        home_roots=_opened_directory_patterns(home) if home else (),
        local_fqdns=fqdn,
        local_hostnames=tuple(dict.fromkeys(hostname_values)),
        local_usernames=(username,) if username else (),
    )


@dataclass(frozen=True, slots=True)
class _AttemptDecision:
    terminal: bool
    terminal_reason: TerminalReason | None
    backoff_ms: int | None
    marker: Literal["authentication_stopped", "delivery_ambiguous"] | None


def _attempt_decision(
    evidence: NormalizedProviderEvidenceV2,
    *,
    attempt_number: int,
    max_transient_retries: int,
) -> _AttemptDecision:
    error = evidence.error
    if error is None:
        return _AttemptDecision(True, "success", None, None)
    if evidence.delivery_certainty == "unknown":
        return _AttemptDecision(True, "ambiguous_delivery", None, "delivery_ambiguous")
    if error.kind == "authentication":
        return _AttemptDecision(
            True,
            "authentication_stopped",
            None,
            "authentication_stopped",
        )
    if error.retryable and evidence.delivery_certainty in {
        "definitely_not_sent",
        "definitely_rejected",
    }:
        if attempt_number <= max_transient_retries:
            return _AttemptDecision(
                False,
                None,
                100 * 2 ** (attempt_number - 1),
                None,
            )
        return _AttemptDecision(True, "retry_exhausted", None, None)
    return _AttemptDecision(True, "provider_rejected", None, None)


def _raw_attempt(
    *,
    context: _VerifiedCapsuleContext,
    captured: _CapturedRequest,
    evidence: NormalizedProviderEvidenceV2,
    decision: _AttemptDecision,
    attempt_number: int,
    call_sequence: int,
    started_at: datetime,
    elapsed_ms: int,
) -> RawAttemptV2:
    row = captured.row
    attempt_id = derive_attempt_id(context.capsule.run_id, row.plan_item_id, attempt_number)
    output = evidence.output
    success = evidence.error is None
    output_text = output.text if success and output is not None else None
    output_sha = output.sha256 if success and output is not None else None
    response_id = None
    if success:
        if output_text is None or output_sha is None:
            _fail("invalid_provider_evidence")
        response_id = _derive_response_id_fields(
            run_id=context.capsule.run_id,
            plan_item_id=row.plan_item_id,
            attempt_id=attempt_id,
            case_uid=row.case_uid,
            instruction_sha256=row.instruction_sha256,
            output_sha256=output_sha,
        )
    discarded_length = None
    discarded_sha = None
    if evidence.error is not None and evidence.error.kind == "response_too_large":
        if output is None or output.text is not None:
            _fail("invalid_provider_evidence")
        discarded_length = output.byte_length
        discarded_sha = output.sha256
    redaction_count = output.credential_replacement_count if output is not None else 0
    try:
        return RawAttemptV2(
            schema_version="2",
            runner_version=context.capsule.runner_version,
            run_id=context.capsule.run_id,
            manifest_sha256=context.capsule.manifest_sha256,
            plan_item_id=row.plan_item_id,
            attempt_id=attempt_id,
            scenario_uid=row.scenario_uid,
            case_uid=row.case_uid,
            case_id=row.case_id,
            locale=row.locale,
            case_definition_sha256=row.case_definition_sha256,
            arm=row.arm,
            repetition=row.repetition,
            attempt=attempt_number,
            terminal=decision.terminal,
            call_sequence=call_sequence,
            retry_of_attempt=None if attempt_number == 1 else attempt_number - 1,
            backoff_ms=decision.backoff_ms,
            delivery_certainty=evidence.delivery_certainty,
            prompt_sha256=row.prompt_sha256,
            instruction_sha256=row.instruction_sha256,
            request_config_sha256=row.request_config_sha256,
            provider=context.manifest.provider.kind,
            model=context.manifest.provider.model,
            response_model=evidence.response_model,
            requested_model_id=evidence.requested_model_id,
            returned_model_id=evidence.returned_model_id,
            returned_model_source_sha256=evidence.returned_model_source_sha256,
            requested_service_tier=evidence.requested_service_tier,
            returned_service_tier=evidence.returned_service_tier,
            service_tier_status=evidence.service_tier_status,
            service_tier_source_sha256=evidence.service_tier_source_sha256,
            applied_prompt_cache_mode=evidence.applied_prompt_cache_mode,
            applied_prompt_cache_ttl=evidence.applied_prompt_cache_ttl,
            applied_cache_control_status=evidence.applied_cache_control_status,
            applied_cache_control_source_sha256=(evidence.applied_cache_control_source_sha256),
            cache_read_source_sha256=evidence.cache_read_source_sha256,
            cache_write_source_sha256=evidence.cache_write_source_sha256,
            usage_source_sha256=evidence.usage_source_sha256,
            reasoning_tokens_source_sha256=evidence.reasoning_tokens_source_sha256,
            started_at=started_at,
            elapsed_ms=elapsed_ms,
            output_text=output_text,
            output_sha256=output_sha,
            response_id=response_id,
            output_was_redacted=redaction_count > 0,
            output_redaction_count=redaction_count,
            discarded_output_byte_length=discarded_length,
            discarded_output_sha256=discarded_sha,
            usage=evidence.usage,
            request_id=evidence.request_id,
            finish_reason=evidence.finish_reason,
            error=evidence.error,
            terminal_reason=decision.terminal_reason,
        )
    except Exception:
        raise ResumeError("invalid_provider_evidence") from None


def _append_budgeted_event(
    transaction: JournalTransaction,
    event: EventV1,
    budget: _CapacityBudget,
) -> None:
    framed_length = len(event_jsonl(event))
    try:
        append_event(transaction, event)
        budget.consume_exact(framed_length, 0)
    except BaseException:
        budget.poison()
        raise


def _append_budgeted_raw(
    transaction: JournalTransaction,
    attempt: RawAttemptV2,
    budget: _CapacityBudget,
) -> None:
    framed_length = len(raw_attempt_bytes(attempt)) + 1
    try:
        append_raw_attempt(transaction, attempt)
        budget.consume_exact(framed_length, 1)
    except BaseException:
        budget.poison()
        raise


def _new_event(
    *,
    transaction: JournalTransaction,
    context: _VerifiedCapsuleContext,
    operation_id: UUID,
    execution_session_id: UUID | None,
    kind: EventKind,
    payload: object,
    seams: _ExecutionSeams,
) -> EventV1:
    return make_event(
        sequence=transaction.events.row_count,
        run_id=context.capsule.run_id,
        occurred_at=_timestamp(seams.utc_now()),
        kind=kind,
        operation_id=operation_id,
        execution_session_id=execution_session_id,
        payload=payload,
    )


def _outcome_from_pair(
    context: _VerifiedCapsuleContext,
    pair: JournalPairSnapshotV1,
    *,
    exit_code: Literal[0, 1, 2],
    code: ResumeCode,
) -> _ResumeOutcome:
    return _ResumeOutcome(
        _result_for_lifecycle(context, pair.lifecycle),
        exit_code,
        code,
    )


def _require_request_free_append_authority(session: _MutatorSessionV1) -> None:
    """Do not turn lost immutable/lock authority into a terminal journal write."""

    try:
        _revalidate_mutator_session_v1(session)
    except (RecoveryError, JournalError):
        raise ResumeError("producer_runtime_differs") from None


def _ambiguous_after_durable_start(
    *,
    session: _MutatorSessionV1,
    context: _VerifiedCapsuleContext,
) -> _ResumeOutcome:
    """Project the retained unmatched start without inventing any later durable evidence."""

    pair = _pair(session.transaction, session.history_context)
    if pair.lifecycle.state != "AMBIGUOUS_INFLIGHT":
        raise ResumeError("lifecycle_mismatch")
    return _outcome_from_pair(
        context,
        pair,
        exit_code=1,
        code="operational_stop",
    )


def _append_interruption(
    *,
    session: _MutatorSessionV1,
    context: _VerifiedCapsuleContext,
    execution_session_id: UUID,
    next_plan_item_id: str,
    reason: Literal["signal", "operator", "internal_error"],
    budget: _CapacityBudget,
    seams: _ExecutionSeams,
) -> _ResumeOutcome:
    event = _new_event(
        transaction=session.transaction,
        context=context,
        operation_id=session.operation_id,
        execution_session_id=execution_session_id,
        kind="execution_interrupted",
        payload={"next_plan_item_id": next_plan_item_id, "reason": reason},
        seams=seams,
    )
    _require_request_free_append_authority(session)
    _append_budgeted_event(session.transaction, event, budget)
    budget.release_attempt_headroom()
    return _outcome_from_pair(
        context,
        _pair(session.transaction, session.history_context),
        exit_code=1,
        code="operational_stop",
    )


def _bind_provider(
    request: ProviderFactoryRequest,
    *,
    provider_factory: ProviderFactory,
    seams: _ExecutionSeams,
) -> _PrivateProviderBinding:
    if seams.private_provider_factory is not None:
        try:
            binding = seams.private_provider_factory(request)
            if type(binding) is not _PrivateProviderBinding:
                raise TypeError
            credentials = binding.credential_values
            if type(credentials) is not tuple or any(
                type(value) is not str or not value for value in credentials
            ):
                raise TypeError
            return _PrivateProviderBinding(binding.provider, tuple(credentials))
        except CredentialUnavailable:
            raise
        except ProviderUnavailable:
            raise
        except Exception:
            raise ProviderUnavailable() from None
    try:
        public_binding = provider_factory.create(request)
        if type(public_binding) is not ProviderBinding:
            raise TypeError
        checked = ProviderBinding(
            public_binding.provider_kind,
            public_binding.adapter_source_sha256,
            public_binding.provider,
            public_binding.credential_values,
        )
        if (
            checked.provider_kind != request.provider_kind
            or checked.adapter_source_sha256 != request.adapter_source_sha256
        ):
            raise TypeError
        return _PrivateProviderBinding(checked.provider, checked.credential_values)
    except CredentialUnavailable:
        raise
    except ProviderUnavailable:
        raise
    except Exception:
        raise ProviderUnavailable() from None


def _execute_provider_ready(
    *,
    path: Path,
    session: _MutatorSessionV1,
    context: _VerifiedCapsuleContext,
    authority: _RuntimeAuthority,
    authored_input_byte_count: int,
    provider_factory: ProviderFactory,
    seams: _ExecutionSeams,
    checkpoint_dispatch: _ExecutionCheckpointDispatch,
) -> _ResumeOutcome:
    _require_fresh_execution_guard(seams)
    pair = _pair(session.transaction, session.history_context)
    history = pair.history
    ordinal = history.next_unresolved_plan_ordinal
    if ordinal is None or not 0 <= ordinal < len(context.plan):
        _fail("lifecycle_mismatch")
    first_request = _captured_request(context, context.plan[ordinal])
    del first_request
    factory_request = _provider_request(context)
    budget = _CapacityBudget(
        session.transaction.total_capsule_bytes,
        session.transaction.raw.row_count,
    )
    budget.reserve_epoch_and_first_attempt()

    execution_session_id = _uuid4(
        seams.new_uuid(),
        code="invalid_execution_session_id",
    )
    if execution_session_id in {session.operation_id, context.capsule.run_id}:
        _fail("invalid_execution_session_id")
    reserved_pair = _snapshot_transaction_pair(
        session.transaction,
        history_context=session.history_context,
        tail_policy="reject",
        reserved_operation_id=execution_session_id,
    )
    if (
        reserved_pair.events != pair.events
        or reserved_pair.raw != pair.raw
        or reserved_pair.history != pair.history
        or reserved_pair.lifecycle != pair.lifecycle
        or reserved_pair.reserved_operation_id != execution_session_id
    ):
        _fail("identity_mismatch")
    started = _new_event(
        transaction=session.transaction,
        context=context,
        operation_id=session.operation_id,
        execution_session_id=execution_session_id,
        kind="execution_started",
        payload={
            "resume_from_plan_ordinal": ordinal,
            "session_environment": authority.session_environment.model_dump(mode="json"),
        },
        seams=seams,
    )
    _append_budgeted_event(session.transaction, started, budget)

    try:
        _install_execution_guard(authority.policy, seams)
        checkpoint_dispatch.complete(
            session,
            authority,
            context,
            authored_input_byte_count=authored_input_byte_count,
            seams=seams,
            dispatch=checkpoint_dispatch,
        )
    except KeyboardInterrupt:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="signal",
            budget=budget,
            seams=seams,
        )
    except ResumeError:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="internal_error",
            budget=budget,
            seams=seams,
        )
    except Exception:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="internal_error",
            budget=budget,
            seams=seams,
        )

    try:
        binding = _bind_provider(
            factory_request,
            provider_factory=provider_factory,
            seams=seams,
        )
    except KeyboardInterrupt:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="signal",
            budget=budget,
            seams=seams,
        )
    except (CredentialUnavailable, ProviderUnavailable) as error:
        reason = error.code
        blocked = _new_event(
            transaction=session.transaction,
            context=context,
            operation_id=session.operation_id,
            execution_session_id=execution_session_id,
            kind="execution_blocked",
            payload={"reason": reason},
            seams=seams,
        )
        _require_request_free_append_authority(session)
        _append_budgeted_event(session.transaction, blocked, budget)
        budget.release_attempt_headroom()
        return _outcome_from_pair(
            context,
            _pair(session.transaction, session.history_context),
            exit_code=1,
            code="operational_stop",
        )

    try:
        checkpoint_dispatch.complete(
            session,
            authority,
            context,
            authored_input_byte_count=authored_input_byte_count,
            seams=seams,
            dispatch=checkpoint_dispatch,
        )
    except KeyboardInterrupt:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="signal",
            budget=budget,
            seams=seams,
        )
    except ResumeError:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="internal_error",
            budget=budget,
            seams=seams,
        )
    except Exception:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="internal_error",
            budget=budget,
            seams=seams,
        )

    try:
        patterns = _sanitizer_patterns(
            path,
            session.transaction._capsule_fd,
            binding.credential_values,
        )
    except KeyboardInterrupt:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="signal",
            budget=budget,
            seams=seams,
        )
    except Exception:
        return _append_interruption(
            session=session,
            context=context,
            execution_session_id=execution_session_id,
            next_plan_item_id=context.plan[ordinal].plan_item_id,
            reason="internal_error",
            budget=budget,
            seams=seams,
        )
    final_finish_id: str | None = None
    for plan_ordinal in range(ordinal, len(context.plan)):
        row = context.plan[plan_ordinal]
        attempt_number = history.next_attempt_number if plan_ordinal == ordinal else 1
        maximum_attempts = context.manifest.retry.max_transient_retries + 1
        if attempt_number is None or not 1 <= attempt_number <= maximum_attempts:
            return _append_interruption(
                session=session,
                context=context,
                execution_session_id=execution_session_id,
                next_plan_item_id=row.plan_item_id,
                reason="internal_error",
                budget=budget,
                seams=seams,
            )
        while True:
            try:
                stop_reason = seams.stop_before_attempt(row)
            except KeyboardInterrupt:
                stop_reason = "signal"
            except Exception:
                stop_reason = "operator"
            if stop_reason is not None:
                if stop_reason not in {"signal", "operator"}:
                    stop_reason = "operator"
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason=stop_reason,
                    budget=budget,
                    seams=seams,
                )
            try:
                budget.reserve_next_attempt()
            except KeyboardInterrupt:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="signal",
                    budget=budget,
                    seams=seams,
                )
            except ResumeError:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="internal_error",
                    budget=budget,
                    seams=seams,
                )
            except Exception:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="internal_error",
                    budget=budget,
                    seams=seams,
                )
            try:
                checkpoint_dispatch.complete(
                    session,
                    authority,
                    context,
                    authored_input_byte_count=authored_input_byte_count,
                    seams=seams,
                    dispatch=checkpoint_dispatch,
                )
                captured = _captured_request(context, row)
            except KeyboardInterrupt:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="signal",
                    budget=budget,
                    seams=seams,
                )
            except Exception:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="internal_error",
                    budget=budget,
                    seams=seams,
                )
            try:
                attempt_id = derive_attempt_id(
                    context.capsule.run_id,
                    row.plan_item_id,
                    attempt_number,
                )
                call_sequence = session.transaction.raw.row_count
                request_started = _new_event(
                    transaction=session.transaction,
                    context=context,
                    operation_id=session.operation_id,
                    execution_session_id=execution_session_id,
                    kind="request_started",
                    payload={
                        "call_sequence": call_sequence,
                        "plan_item_id": row.plan_item_id,
                        "attempt_id": attempt_id,
                        "attempt": attempt_number,
                        "retry_of_attempt": (None if attempt_number == 1 else attempt_number - 1),
                        "request_config_sha256": row.request_config_sha256,
                        "prompt_sha256": row.prompt_sha256,
                        "case_definition_sha256": row.case_definition_sha256,
                        "instruction_sha256": row.instruction_sha256,
                        "provider": context.manifest.provider.kind,
                        "model": context.manifest.provider.model,
                    },
                    seams=seams,
                )
            except KeyboardInterrupt:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="signal",
                    budget=budget,
                    seams=seams,
                )
            except Exception:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="internal_error",
                    budget=budget,
                    seams=seams,
                )
            _append_budgeted_event(session.transaction, request_started, budget)

            try:
                started_at = _timestamp(seams.utc_now())
                start_ns = seams.monotonic_ns()
                if type(start_ns) is not int:
                    _fail("invalid_clock")
                checkpoint_dispatch.complete(
                    session,
                    authority,
                    context,
                    authored_input_byte_count=authored_input_byte_count,
                    seams=seams,
                    dispatch=checkpoint_dispatch,
                )
            except Exception:
                return _ambiguous_after_durable_start(
                    session=session,
                    context=context,
                )

            # A test seam may keep counters in its runtime-checkpoint closure. Renew the
            # full seals only after the final trusted pre-call invocation, immediately
            # before provider code gains control; provider-side changes then cannot be
            # accepted as legitimate dispatch state.
            checkpoint_dispatch.complete_seal = checkpoint_dispatch.seal(
                checkpoint_dispatch.complete
            )
            checkpoint_dispatch.runtime_seal = checkpoint_dispatch.seal(checkpoint_dispatch.runtime)
            checkpoint_dispatch.revalidate_seal = checkpoint_dispatch.seal(
                checkpoint_dispatch.revalidate
            )
            outcome: object
            try:
                benchmark_request = type(captured.request) is PublicBenchmarkRequestV1
                if benchmark_request:
                    captured_benchmark_request = cast(
                        PublicBenchmarkRequestV1,
                        captured.request,
                    )
                    requested_service_tier: ServiceTier | None = (
                        captured_benchmark_request.policy.service_tier
                    )
                    benchmark_provider = cast(PublicBenchmarkProvider, binding.provider)
                    outcome = benchmark_provider.generate_benchmark(captured_benchmark_request)
                else:
                    requested_service_tier = None
                    legacy_provider = cast(Provider, binding.provider)
                    outcome = legacy_provider.generate(cast(GenerationRequest, captured.request))
            except ProviderError as error:
                outcome = error
            except Exception as error:
                outcome = error
            try:
                if (
                    _complete_execution_checkpoint is not checkpoint_dispatch.complete
                    or _runtime_checkpoint is not checkpoint_dispatch.runtime
                    or _revalidate_mutator_session_v1 is not checkpoint_dispatch.revalidate
                    or not checkpoint_dispatch.matches(
                        checkpoint_dispatch.integrity,
                        checkpoint_dispatch.integrity_seal,
                    )
                    or not checkpoint_dispatch.matches(
                        checkpoint_dispatch.complete,
                        checkpoint_dispatch.complete_seal,
                    )
                    or not checkpoint_dispatch.matches(
                        checkpoint_dispatch.runtime,
                        checkpoint_dispatch.runtime_seal,
                    )
                    or not checkpoint_dispatch.matches(
                        checkpoint_dispatch.revalidate,
                        checkpoint_dispatch.revalidate_seal,
                    )
                ):
                    raise ResumeError("producer_runtime_differs")
                checkpoint_dispatch.complete(
                    session,
                    authority,
                    context,
                    authored_input_byte_count=authored_input_byte_count,
                    seams=seams,
                    dispatch=checkpoint_dispatch,
                )
                end_ns = seams.monotonic_ns()
                if type(end_ns) is not int:
                    _fail("invalid_clock")
                elapsed_ms = max(0, end_ns - start_ns) // 1_000_000
                if benchmark_request:
                    if requested_service_tier is None:
                        _fail("invalid_provider_evidence")
                    evidence = normalize_public_benchmark_outcome(
                        cast(PublicBenchmarkProviderOutcomeV1, outcome),
                        requested_service_tier=requested_service_tier,
                        patterns=patterns,
                    )
                else:
                    evidence = normalize_provider_outcome(
                        cast(GenerationResult | ProviderError, outcome),
                        patterns=patterns,
                    )
                checkpoint_dispatch.complete(
                    session,
                    authority,
                    context,
                    authored_input_byte_count=authored_input_byte_count,
                    seams=seams,
                    dispatch=checkpoint_dispatch,
                )
            except Exception:
                return _ambiguous_after_durable_start(
                    session=session,
                    context=context,
                )
            try:
                decision = _attempt_decision(
                    evidence,
                    attempt_number=attempt_number,
                    max_transient_retries=context.manifest.retry.max_transient_retries,
                )
                raw = _raw_attempt(
                    context=context,
                    captured=captured,
                    evidence=evidence,
                    decision=decision,
                    attempt_number=attempt_number,
                    call_sequence=call_sequence,
                    started_at=started_at,
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                return _ambiguous_after_durable_start(
                    session=session,
                    context=context,
                )
            _append_budgeted_raw(session.transaction, raw, budget)
            finished = _new_event(
                transaction=session.transaction,
                context=context,
                operation_id=session.operation_id,
                execution_session_id=execution_session_id,
                kind="request_finished",
                payload={
                    "call_sequence": call_sequence,
                    "plan_item_id": row.plan_item_id,
                    "attempt_id": attempt_id,
                    "request_started_event_id": request_started.event_id,
                    "raw_record_sha256": raw_record_sha256(raw),
                    "recovered": False,
                },
                seams=seams,
            )
            _append_budgeted_event(session.transaction, finished, budget)
            final_finish_id = finished.event_id

            if decision.marker is not None:
                marker = _new_event(
                    transaction=session.transaction,
                    context=context,
                    operation_id=session.operation_id,
                    execution_session_id=execution_session_id,
                    kind=decision.marker,
                    payload={
                        "plan_item_id": row.plan_item_id,
                        "attempt_id": attempt_id,
                        "origin_request_started_event_id": request_started.event_id,
                        "recovered": False,
                    },
                    seams=seams,
                )
                _append_budgeted_event(session.transaction, marker, budget)
                budget.release_attempt_headroom()
                return _outcome_from_pair(
                    context,
                    _pair(session.transaction, session.history_context),
                    exit_code=1,
                    code="operational_stop",
                )
            if decision.terminal:
                if plan_ordinal != len(context.plan) - 1:
                    budget.release_attempt_headroom()
                break
            assert decision.backoff_ms is not None
            try:
                seams.sleeper(decision.backoff_ms / 1000)
            except KeyboardInterrupt:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="signal",
                    budget=budget,
                    seams=seams,
                )
            except Exception:
                return _append_interruption(
                    session=session,
                    context=context,
                    execution_session_id=execution_session_id,
                    next_plan_item_id=row.plan_item_id,
                    reason="internal_error",
                    budget=budget,
                    seams=seams,
                )
            attempt_number += 1
            if attempt_number > maximum_attempts:
                _fail("retry_mismatch")

    if final_finish_id is None:
        _fail("history_mismatch")
    completed = _new_event(
        transaction=session.transaction,
        context=context,
        operation_id=session.operation_id,
        execution_session_id=execution_session_id,
        kind="generation_completed",
        payload={
            "terminal_plan_item_count": len(context.plan),
            "final_plan_ordinal": len(context.plan) - 1,
            "origin_request_finished_event_id": final_finish_id,
            "recovered": False,
        },
        seams=seams,
    )
    _append_budgeted_event(session.transaction, completed, budget)
    budget.release_attempt_headroom()
    return _outcome_from_pair(
        context,
        _pair(session.transaction, session.history_context),
        exit_code=0,
        code="complete",
    )


def _resume_locked(
    *,
    path: Path,
    session: _MutatorSessionV1,
    filesystem_class: str,
    provider_factory: ProviderFactory,
    on_target_known: Callable[[Path], None] | None,
    seams: _ExecutionSeams,
    checkpoint_dispatch: _ExecutionCheckpointDispatch,
) -> _ResumeOutcome:
    context = _verified_context(session)
    recovery_plan = _plan_mutator_session_v1(session)
    try:
        if on_target_known is not None:
            on_target_known(path)
    except Exception:
        raise ResumeError("target_callback_failed") from None

    authored_bytes = _authored_input_byte_count(context)
    try:
        authority = _capture_runtime_authority(
            context,
            authored_input_byte_count=authored_bytes,
            filesystem_class=filesystem_class,
        )
    except ResumeError as error:
        if error.code != "producer_runtime_differs":
            raise
        return _ResumeOutcome(
            _result_for_lifecycle(
                context,
                context.lifecycle,
                producer_runtime_differs=True,
            ),
            2,
            "producer_runtime_differs",
        )

    _require_fresh_execution_guard(seams)
    applied = _apply_recovery_plan_v1(session, recovery_plan)
    pair = _pair(session.transaction, session.history_context)
    if applied.disposition != (
        "sealing_interrupted"
        if pair.lifecycle.state == "SEALING_INTERRUPTED"
        else "ambiguous"
        if pair.lifecycle.state == "AMBIGUOUS_INFLIGHT"
        else "authentication_stopped"
        if pair.lifecycle.state == "AUTHENTICATION_STOPPED"
        else "complete"
        if pair.lifecycle.state == "GENERATION_COMPLETE"
        else "provider_ready"
    ):
        _fail("lifecycle_mismatch")
    if applied.disposition == "complete":
        return _outcome_from_pair(context, pair, exit_code=0, code="complete")
    if applied.disposition in {"ambiguous", "authentication_stopped"}:
        return _outcome_from_pair(
            context,
            pair,
            exit_code=1,
            code="operational_stop",
        )
    if applied.disposition == "sealing_interrupted":
        return _outcome_from_pair(context, pair, exit_code=2, code="sealed")
    return _execute_provider_ready(
        path=path,
        session=session,
        context=context,
        authority=authority,
        authored_input_byte_count=authored_bytes,
        provider_factory=provider_factory,
        seams=seams,
        checkpoint_dispatch=checkpoint_dispatch,
    )


def _invalid_outcome(code: str = "invalid_model") -> _ResumeOutcome:
    return _ResumeOutcome(_invalid_result(code), 2, "invalid")


def _resume_capsule(
    path: Path,
    *,
    provider_factory: ProviderFactory,
    on_target_known: Callable[[Path], None] | None = None,
    seams: _ExecutionSeams | None = None,
    _runtime_integrity_check: Callable[[], bool] = _CAPTURED_PROVIDER_RUNTIME_CHECK,
) -> _ResumeOutcome:
    """Private wrapper exposing clocks/provider seams and the target-known callback."""

    type_of = type
    id_of = id
    len_of = len
    raw_getattribute = object.__getattribute__
    function_type = FunctionType
    function_seal_type = _FunctionSeal
    tuple_type = tuple
    dict_type = dict
    str_type = str
    int_type = int
    ordinary_exception = Exception

    def sequence_identity_matches(actual: object, expected: object) -> bool:
        if expected is None:
            return actual is None
        if type_of(actual) is not tuple_type or type_of(expected) is not tuple_type:
            return False
        actual_items: tuple[object, ...] = actual  # type: ignore[assignment]
        expected_parts: tuple[object, ...] = expected  # type: ignore[assignment]
        if len_of(expected_parts) != 2 or type_of(expected_parts[1]) is not tuple_type:
            return False
        expected_items: tuple[object, ...] = expected_parts[1]  # type: ignore[assignment]
        if (
            type_of(expected_parts[0]) is not int_type
            or id_of(actual_items) != expected_parts[0]
            or len_of(actual_items) != len_of(expected_items)
        ):
            return False
        for index in range(len_of(actual_items)):
            if type_of(expected_items[index]) is not int_type:
                return False
            if id_of(actual_items[index]) != expected_items[index]:
                return False
        return True

    def kwdefault_identity_matches(actual: object, expected: object) -> bool:
        if expected is None:
            return actual is None
        if type_of(actual) is not dict_type or type_of(expected) is not tuple_type:
            return False
        actual_mapping: dict[object, object] = actual  # type: ignore[assignment]
        expected_parts: tuple[object, ...] = expected  # type: ignore[assignment]
        if len_of(expected_parts) != 2 or type_of(expected_parts[1]) is not tuple_type:
            return False
        expected_items: tuple[object, ...] = expected_parts[1]  # type: ignore[assignment]
        if (
            type_of(expected_parts[0]) is not int_type
            or id_of(actual_mapping) != expected_parts[0]
            or len_of(actual_mapping) != len_of(expected_items)
        ):
            return False
        for item in expected_items:
            if type_of(item) is not tuple_type:
                return False
            item_parts: tuple[object, ...] = item  # type: ignore[assignment]
            if (
                len_of(item_parts) != 2
                or type_of(item_parts[0]) is not str_type
                or type_of(item_parts[1]) is not int_type
                or item_parts[0] not in actual_mapping
                or id_of(actual_mapping[item_parts[0]]) != item_parts[1]
            ):
                return False
        return True

    def closure_identity_matches(actual: object, expected: object) -> bool:
        if expected is None:
            return actual is None
        if type_of(actual) is not tuple_type or type_of(expected) is not tuple_type:
            return False
        actual_cells: tuple[object, ...] = actual  # type: ignore[assignment]
        expected_parts: tuple[object, ...] = expected  # type: ignore[assignment]
        if len_of(expected_parts) != 2 or type_of(expected_parts[1]) is not tuple_type:
            return False
        expected_items: tuple[object, ...] = expected_parts[1]  # type: ignore[assignment]
        if (
            type_of(expected_parts[0]) is not int_type
            or id_of(actual_cells) != expected_parts[0]
            or len_of(actual_cells) != len_of(expected_items)
        ):
            return False
        for index in range(len_of(actual_cells)):
            item = expected_items[index]
            if type_of(item) is not tuple_type:
                return False
            item_parts: tuple[object, ...] = item  # type: ignore[assignment]
            if (
                len_of(item_parts) != 2
                or type_of(item_parts[0]) is not int_type
                or type_of(item_parts[1]) is not int_type
                or id_of(actual_cells[index]) != item_parts[0]
                or id_of(raw_getattribute(actual_cells[index], "cell_contents")) != item_parts[1]
            ):
                return False
        return True

    def raw_function_matches(value: object, seal: _FunctionSeal) -> bool:
        try:
            return (
                type_of(value) is function_type
                and type_of(seal) is function_seal_type
                and value is raw_getattribute(seal, "function")
                and raw_getattribute(value, "__code__") is raw_getattribute(seal, "code")
                and sequence_identity_matches(
                    raw_getattribute(value, "__defaults__"),
                    raw_getattribute(seal, "defaults"),
                )
                and kwdefault_identity_matches(
                    raw_getattribute(value, "__kwdefaults__"),
                    raw_getattribute(seal, "kwdefaults"),
                )
                and closure_identity_matches(
                    raw_getattribute(value, "__closure__"),
                    raw_getattribute(seal, "closure"),
                )
                and id_of(raw_getattribute(value, "__globals__"))
                == raw_getattribute(seal, "globals_id")
                and id_of(raw_getattribute(value, "__builtins__"))
                == raw_getattribute(seal, "builtins_id")
            )
        except ordinary_exception:
            return False

    complete_execution_checkpoint = _complete_execution_checkpoint
    runtime_checkpoint = _runtime_checkpoint
    revalidate_mutator_session = _revalidate_mutator_session_v1
    runtime_integrity_check = cast(FunctionType, _runtime_integrity_check)
    checkpoint_dispatch = _ExecutionCheckpointDispatch(
        complete_execution_checkpoint,
        _seal_function(complete_execution_checkpoint),
        runtime_checkpoint,
        _seal_function(runtime_checkpoint),
        revalidate_mutator_session,
        _seal_function(revalidate_mutator_session),
        runtime_integrity_check,
        _seal_function(runtime_integrity_check),
        raw_function_matches,
        _seal_function,
    )
    execution_seams = _ExecutionSeams() if seams is None else seams
    if (
        type(provider_factory) is not ProviderFactory
        or ProviderFactory.create is not _PROVIDER_FACTORY_CREATE
        or not _runtime_integrity_check()
        or type(execution_seams) is not _ExecutionSeams
        or (on_target_known is not None and not callable(on_target_known))
    ):
        return _invalid_outcome()
    try:
        _require_fresh_execution_guard(execution_seams)
    except ResumeError:
        return _invalid_outcome()

    try:
        raw_path = os.fspath(path)
        if type(raw_path) is not str or not raw_path:
            raise TypeError
        visible_path = Path(os.path.abspath(raw_path))
        if not visible_path.name:
            raise TypeError
        operation_id = _uuid4(
            execution_seams.new_uuid(),
            code="invalid_operation_id",
        )
        operation_time = _timestamp(execution_seams.utc_now())
    except Exception:
        return _invalid_outcome()

    root_fd: int | None = None
    parent_fd: int | None = None
    lock: LockHandle | None = None
    session: _MutatorSessionV1 | None = None
    root_before: _Identity | None = None
    parent_before: _Identity | None = None
    outcome: _ResumeOutcome | None = None
    fatal: BaseException | None = None
    try:
        root_fd = open_directory_no_follow(visible_path)
        parent_fd = open_directory_no_follow(visible_path.parent)
        parent_before, root_before = _check_public_root_identity(
            visible_path,
            parent_fd,
            root_fd,
        )
        posix = cast(FilesystemPosixOps, PosixOps())
        filesystem_identity = classify_filesystem(root_fd, posix=posix)
        lock = try_acquire_mutator_lock(root_fd, posix=posix)
        if lock is None:
            outcome = _ResumeOutcome(_busy_result(), 2, "busy")
        else:
            _check_lock_identity(root_fd, lock.descriptor)
            session = _make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=visible_path.name,
                operation_id=operation_id,
                occurred_at=operation_time,
                lock_handle=lock,
            )
            outcome = _resume_locked(
                path=visible_path,
                session=session,
                filesystem_class=filesystem_identity.filesystem_class,
                provider_factory=provider_factory,
                on_target_known=on_target_known,
                seams=execution_seams,
                checkpoint_dispatch=checkpoint_dispatch,
            )
    except UnsupportedFilesystemError:
        outcome = _ResumeOutcome(_unsupported_result(), 2, "unsupported_filesystem")
    except (KeyboardInterrupt, SystemExit) as error:
        fatal = error
    except BoundedIOError:
        outcome = _invalid_outcome("unsafe_path_type")
    except FileNotFoundError:
        outcome = _invalid_outcome("missing_path")
    except OwnedStagingError as error:
        code = "unsafe_path_type" if error.code == "unsafe_lock_file" else "io_error"
        outcome = _invalid_outcome(code)
    except RecoveryError as error:
        outcome = _invalid_outcome(error.code)
    except JournalError as error:
        outcome = _invalid_outcome(error.code)
    except ResumeError as error:
        code = (
            error.code
            if error.code
            in {
                "resource_limit",
                "unstable_snapshot",
                "noncanonical_json",
                "history_mismatch",
                "retry_mismatch",
                "lifecycle_mismatch",
            }
            else "invalid_model"
        )
        outcome = _invalid_outcome(code)
    except OSError as error:
        outcome = _invalid_outcome(
            "unsafe_path_type" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
        )
    except Exception:
        outcome = _invalid_outcome()
    finally:
        cleanup_failed = False
        if lock is not None and root_fd is not None and parent_fd is not None:
            try:
                _check_lock_identity(root_fd, lock.descriptor)
                if root_before is not None and parent_before is not None:
                    _check_public_root_identity(
                        visible_path,
                        parent_fd,
                        root_fd,
                        expected_parent=parent_before,
                        expected_root=root_before,
                        recheck_visible_parent=True,
                    )
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception) and fatal is None:
                    fatal = cleanup_error
                else:
                    cleanup_failed = True
        if session is not None:
            try:
                session.transaction.close()
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception) and fatal is None:
                    fatal = cleanup_error
                else:
                    cleanup_failed = True
        if lock is not None:
            try:
                lock.close()
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception) and fatal is None:
                    fatal = cleanup_error
                else:
                    cleanup_failed = True
        for descriptor in (root_fd, parent_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception) and fatal is None:
                    fatal = cleanup_error
                else:
                    cleanup_failed = True
        if cleanup_failed and fatal is None:
            outcome = _invalid_outcome("io_error")
    if fatal is not None:
        raise fatal
    return _invalid_outcome() if outcome is None else outcome


def resume_capsule(
    path: Path,
    *,
    provider_factory: ProviderFactory,
) -> VerifyResultV1:
    """Resume one prepared capsule using only captured bytes and installed producer identity."""

    return _resume_capsule(path, provider_factory=provider_factory).result


# Runtime call sites and the exact factory method captured this closure during module setup.
# Removing the temporary public binding leaves no replaceable module-global authority handle.
del _CAPTURED_PROVIDER_RUNTIME_CHECK
