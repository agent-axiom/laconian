from __future__ import annotations

import base64
import builtins
import contextvars
import csv
import hashlib
import hmac
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import io
import math
import os
import re
import stat
import threading
import tomllib
import types
import typing
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    ForwardRef,
    Literal,
    Protocol,
    TypeAlias,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, field_validator, model_validator
from pydantic.fields import FieldInfo

from laconian_eval.benchmark import canonical_json_v1 as _canonical_json_v1
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.schema import CapsuleModel, Sha256
from laconian_eval.providers.base import (
    DeliveryCertainty,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    PublicBenchmarkRequestPolicyV1,
    PublicBenchmarkRequestV1,
    TokenUsage,
)

BENCHMARK_OPENAI_REQUEST_FIELDS_V1 = (
    "model",
    "instructions",
    "input",
    "max_output_tokens",
    "store",
    "tools",
    "reasoning",
    "text",
    "prompt_cache_options",
    "service_tier",
)
BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1 = (
    "response.id",
    "response.status",
    "response.error",
    "response.output",
)
BENCHMARK_OPENAI_RESPONSE_PATHS_V1 = (
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
BENCHMARK_OPENAI_RETURNED_MODEL_PATH_V1 = "response.model"
BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1 = (
    b'{"input":"sdk-contract-input-v1","instructions":"sdk-contract-instructions-v1",'
    b'"max_output_tokens":1024,"model":"gpt-5.6-sol","prompt_cache_options":'
    b'{"mode":"explicit","ttl":"30m"},"reasoning":{"effort":"medium"},'
    b'"service_tier":"default","store":false,"text":{"verbosity":"medium"}}'
)
BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1 = (
    "c7f3d0d8d7b056226b10195e76e9974c213881e3678d09aee071ad3cbedb0211"
)
BENCHMARK_OPENAI_LOCK_REGISTRY_V1 = "https://pypi.org/simple"
BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1 = (
    "anyio",
    "httpx2",
    "jiter",
    "pydantic",
    "sniffio",
    "typing-extensions",
)
BENCHMARK_OPENAI_LOCK_SDIST_V1 = (
    "https://files.pythonhosted.org/packages/7d/9c/ba0c292b4032ede74c249ca314ad64eb1bb5a03a843f6e01facb02f80cd8/openai-3.3.1.tar.gz",
    "sha256:6f22807de1a976c932cecda620e8172a8c3fdbaeed29c7f21564e0c2410edf56",
    1_282_113,
    "2026-08-19T16:31:35.006Z",
)
BENCHMARK_OPENAI_LOCK_WHEELS_V1 = (
    (
        "https://files.pythonhosted.org/packages/6a/db/2b7a1b3de659bb82aef979116c74e809982b13e42c057759767552b5155f/openai-3.3.1-py3-none-any.whl",
        "sha256:9652df7fdf8ee6f5bd58e0a12f2b1d414a18e0f06bb7a9a57c8643a5f5469bd3",
        1_690_337,
        "2026-08-19T16:31:32.812Z",
    ),
)
_OPENAI_WHEEL_RECORD_SIZE = 164_291
_OPENAI_WHEEL_RECORD_SHA256 = "4a9a567d1c130100b9fd5bb48d4f6605d39f818d0466329225a853a7ff5ead31"
_OPENAI_RECORD_PROJECTION_ROWS = 1_530
_OPENAI_RECORD_PROJECTION_DECLARED_SIZE = 6_364_613
_OPENAI_RECORD_PROJECTION_PREIMAGE_SIZE = 163_990
_OPENAI_RECORD_PROJECTION_SHA256 = (
    "8b8a7f3f95d8937c1e795223842535a58ad7e1e17991eb66b565429b345393db"
)

_OPENAI_RECORD_RELATIVE_PATH = "openai-3.3.1.dist-info/RECORD"
_MAX_OPENAI_RECORD_BYTES = 262_144
_MAX_OPENAI_RECORD_ROWS = 1_600
_MAX_OPENAI_SOURCE_BYTES = 1_048_576

BenchmarkSDKContractErrorCode: TypeAlias = Literal[
    "installed-version",
    "lock-digest",
    "lock-entry",
    "request-model",
    "response-model",
    "serializer-projection",
]


class BenchmarkSDKContractError(RuntimeError):
    code: BenchmarkSDKContractErrorCode

    def __init__(self, code: BenchmarkSDKContractErrorCode) -> None:
        self.code = code
        super().__init__("public benchmark SDK contract verification failed")


class VerifiedBenchmarkSDKContractV1(CapsuleModel):
    schema_version: Literal["VerifiedBenchmarkSDKContractV1"]
    distribution: Literal["openai"]
    installed_version: Literal["3.3.1"]
    c0_uv_lock_sha256: Sha256
    lock_version: Literal["3.3.1"]
    lock_registry: Literal["https://pypi.org/simple"]
    lock_dependencies: tuple[
        Literal["anyio"],
        Literal["httpx2"],
        Literal["jiter"],
        Literal["pydantic"],
        Literal["sniffio"],
        Literal["typing-extensions"],
    ]
    lock_sdist_url: Literal[
        "https://files.pythonhosted.org/packages/7d/9c/ba0c292b4032ede74c249ca314ad64eb1bb5a03a843f6e01facb02f80cd8/openai-3.3.1.tar.gz"
    ]
    lock_sdist_hash: Literal[
        "sha256:6f22807de1a976c932cecda620e8172a8c3fdbaeed29c7f21564e0c2410edf56"
    ]
    lock_sdist_size: Literal[1282113]
    lock_sdist_upload_time: Literal["2026-08-19T16:31:35.006Z"]
    lock_wheel_url: Literal[
        "https://files.pythonhosted.org/packages/6a/db/2b7a1b3de659bb82aef979116c74e809982b13e42c057759767552b5155f/openai-3.3.1-py3-none-any.whl"
    ]
    lock_wheel_hash: Literal[
        "sha256:9652df7fdf8ee6f5bd58e0a12f2b1d414a18e0f06bb7a9a57c8643a5f5469bd3"
    ]
    lock_wheel_size: Literal[1690337]
    lock_wheel_upload_time: Literal["2026-08-19T16:31:32.812Z"]
    request_model_qualified_name: Literal[
        "openai.types.responses.response_create_params.ResponseCreateParams"
    ]
    response_model_qualified_name: Literal["openai.types.responses.response.Response"]
    request_fields: tuple[
        Literal["model"],
        Literal["instructions"],
        Literal["input"],
        Literal["max_output_tokens"],
        Literal["store"],
        Literal["tools"],
        Literal["reasoning"],
        Literal["text"],
        Literal["prompt_cache_options"],
        Literal["service_tier"],
    ]
    response_paths: tuple[
        Literal["response.service_tier"],
        Literal["response.prompt_cache_options.mode"],
        Literal["response.prompt_cache_options.ttl"],
        Literal["response.usage.input_tokens"],
        Literal["response.usage.input_tokens_details.cached_tokens"],
        Literal["response.usage.input_tokens_details.cache_write_tokens"],
        Literal["response.usage.output_tokens"],
        Literal["response.usage.output_tokens_details.reasoning_tokens"],
        Literal["response.usage.total_tokens"],
    ]
    returned_model_path: Literal["response.model"]
    response_content_paths: tuple[
        Literal["response.id"],
        Literal["response.status"],
        Literal["response.error"],
        Literal["response.output"],
    ]
    serializer_projection_sha256: Literal[
        "c7f3d0d8d7b056226b10195e76e9974c213881e3678d09aee071ad3cbedb0211"
    ]
    contract_sha256: Sha256

    @field_validator("lock_sdist_size", "lock_wheel_size", mode="before")
    @classmethod
    def validate_exact_artifact_size(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("artifact size must be an exact integer")
        return value

    @model_validator(mode="after")
    def validate_contract_digest(self) -> typing.Self:
        payload = self.model_dump(mode="json", exclude={"contract_sha256"})
        if self.contract_sha256 != stable_digest("laconian-benchmark-sdk-contract-v1", payload):
            raise ValueError("SDK contract digest mismatch")
        return self


def _installed_openai_version() -> object:
    return importlib.metadata.version("openai")


class _OpenAIRecordEntry(typing.NamedTuple):
    digest: str
    size: int


class _AuthenticatedOpenAIInstall(typing.NamedTuple):
    root: Path
    record_path: Path
    record_projection_sha256: str
    entries: typing.Mapping[str, _OpenAIRecordEntry]


def _read_bounded_regular_file(path: Path, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ImportError("OpenAI authenticated file is not regular")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read(maximum_bytes + 1)
    finally:
        os.close(descriptor)


def _read_openai_record_bytes(path: Path) -> bytes:
    record = _read_bounded_regular_file(path, _MAX_OPENAI_RECORD_BYTES)
    if len(record) > _MAX_OPENAI_RECORD_BYTES:
        raise ImportError("OpenAI RECORD exceeds the authenticated bound")
    return record


def _decode_record_digest(value: str) -> bytes:
    if not value.startswith("sha256="):
        raise ImportError("OpenAI RECORD hash algorithm is not authenticated")
    encoded = value.removeprefix("sha256=")
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", encoded) is None:
        raise ImportError("OpenAI RECORD digest is malformed")
    try:
        digest = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise ImportError("OpenAI RECORD digest is malformed") from None
    if len(digest) != hashlib.sha256().digest_size:
        raise ImportError("OpenAI RECORD digest is malformed")
    return digest


def _validated_record_path(value: str) -> PurePosixPath:
    if (
        not value
        or "\\" in value
        or "," in value
        or "\x00" in value
        or "\r" in value
        or "\n" in value
    ):
        raise ImportError("OpenAI RECORD path is malformed")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ImportError("OpenAI RECORD path is malformed")
    return path


def _parse_openai_record(
    record: bytes,
) -> tuple[str, typing.Mapping[str, _OpenAIRecordEntry]]:
    try:
        decoded = record.decode("utf-8", errors="strict")
        rows = list(csv.reader(io.StringIO(decoded, newline=""), strict=True))
    except (UnicodeError, csv.Error):
        raise ImportError("OpenAI RECORD is malformed") from None
    if not 1 <= len(rows) <= _MAX_OPENAI_RECORD_ROWS:
        raise ImportError("OpenAI RECORD row count is invalid")
    all_paths: set[str] = set()
    selected: list[tuple[str, str, str]] = []
    entries: dict[str, _OpenAIRecordEntry] = {}
    for row in rows:
        if len(row) != 3:
            raise ImportError("OpenAI RECORD row is malformed")
        path_text, hash_text, size_text = row
        path = _validated_record_path(path_text)
        normalized = path.as_posix()
        if normalized != path_text or normalized in all_paths:
            raise ImportError("OpenAI RECORD path is duplicated or noncanonical")
        all_paths.add(normalized)
        if not hash_text and not size_text:
            if normalized != _OPENAI_RECORD_RELATIVE_PATH:
                raise ImportError("OpenAI RECORD empty integrity fields are invalid")
            continue
        digest = _decode_record_digest(hash_text)
        if re.fullmatch(r"0|[1-9][0-9]*", size_text) is None:
            raise ImportError("OpenAI RECORD size is malformed")
        size = int(size_text)
        if normalized.startswith("openai/"):
            entries[normalized] = _OpenAIRecordEntry(digest.hex(), size)
            selected.append((normalized, hash_text, size_text))
    selected.sort(key=lambda row: row[0].encode("utf-8"))
    preimage = "".join(",".join(row) + "\n" for row in selected).encode("utf-8")
    projection_sha256 = hashlib.sha256(preimage).hexdigest()
    if (
        len(selected) != _OPENAI_RECORD_PROJECTION_ROWS
        or sum(int(row[2]) for row in selected) != _OPENAI_RECORD_PROJECTION_DECLARED_SIZE
        or len(preimage) != _OPENAI_RECORD_PROJECTION_PREIMAGE_SIZE
        or not hmac.compare_digest(projection_sha256, _OPENAI_RECORD_PROJECTION_SHA256)
    ):
        raise ImportError("OpenAI RECORD projection is not authenticated")
    return projection_sha256, types.MappingProxyType(entries)


def _authenticate_openai_install() -> _AuthenticatedOpenAIInstall:
    distribution = importlib.metadata.distribution("openai")
    root = Path(str(distribution.locate_file("openai"))).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ImportError("OpenAI distribution root is not authenticated")
    record_path = root.parent / _OPENAI_RECORD_RELATIVE_PATH
    if record_path.is_symlink() or record_path.resolve(strict=True) != record_path:
        raise ImportError("OpenAI RECORD path is not authenticated")
    record = _read_openai_record_bytes(record_path)
    projection_sha256, entries = _parse_openai_record(record)
    return _AuthenticatedOpenAIInstall(root, record_path, projection_sha256, entries)


def _read_authenticated_openai_file(
    install: _AuthenticatedOpenAIInstall, path: Path, maximum_bytes: int
) -> bytes:
    try:
        if path.resolve(strict=True) != path or not path.is_relative_to(install.root):
            raise ImportError("OpenAI source escaped the authenticated root")
        relative = path.relative_to(install.root.parent).as_posix()
    except (OSError, ValueError):
        raise ImportError("OpenAI source escaped the authenticated root") from None
    entry = install.entries.get(relative)
    if entry is None or entry.size > maximum_bytes:
        raise ImportError("OpenAI source is not present in the authenticated RECORD")
    content = _read_bounded_regular_file(path, entry.size)
    if type(content) is not bytes or len(content) != entry.size:
        raise ImportError("OpenAI source size is not authenticated")
    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), entry.digest):
        raise ImportError("OpenAI source hash is not authenticated")
    return content


def _public_benchmark_responses_kwargs(
    request: PublicBenchmarkRequestV1,
) -> dict[str, object]:
    result: dict[str, object] = {
        "model": request.requested_model_id,
        "instructions": request.instructions,
        "input": request.prompt,
        "max_output_tokens": request.max_output_tokens,
        "store": False,
    }
    if request.reasoning_effort is not None:
        result["reasoning"] = {"effort": request.reasoning_effort}
    if request.text_verbosity is not None:
        result["text"] = {"verbosity": request.text_verbosity}
    result["prompt_cache_options"] = {
        "mode": request.policy.prompt_cache_mode,
        "ttl": request.policy.prompt_cache_ttl,
    }
    result["service_tier"] = request.policy.service_tier
    return result


def _rewrite_private_openai_source(name: str, source: str) -> str:
    replacements: tuple[tuple[str, str], ...] = ()
    if name == "openai._models":
        replacements = (
            (
                'coerce_boolean(os.environ.get("DEFER_PYDANTIC_BUILD", "true"))',
                "True",
            ),
            (
                "        model_config: ClassVar[ConfigDict] = "
                "ConfigDict(arbitrary_types_allowed=True)",
                "        model_config: ClassVar[ConfigDict] = ConfigDict("
                "arbitrary_types_allowed=True, defer_build=True)",
            ),
        )
    elif name == "openai._compat":
        replacements = (
            (
                "        class GenericModel(pydantic.BaseModel): ...",
                "        class GenericModel(pydantic.BaseModel):\n"
                "            model_config = pydantic.ConfigDict(defer_build=True)",
            ),
        )
    for needle, replacement in replacements:
        if source.count(needle) != 1:
            raise ImportError("pinned openai private source anchor changed")
        source = source.replace(needle, replacement)
    return source


class _PrivateOpenAITypeLoader:
    def __init__(self, install: _AuthenticatedOpenAIInstall | None = None) -> None:
        self.install = _authenticate_openai_install() if install is None else install
        self.root = self.install.root
        self.modules: dict[str, types.ModuleType] = {}
        self.loaded_source_paths: dict[str, Path] = {}
        self._failed = False
        self._real_import = builtins.__import__

    def _module_path(self, name: str) -> tuple[Path, bool, bool]:
        relative = name.removeprefix("openai").lstrip(".").split(".")
        base = self.root.joinpath(*relative)
        if name in {"openai", "openai.types", "openai.types.responses"}:
            if not base.is_dir():
                raise ImportError("private SDK package is missing")
            return base, True, True
        package_init = base / "__init__.py"
        if package_init.is_file():
            return package_init, True, False
        module_path = base.with_suffix(".py")
        if module_path.is_file():
            return module_path, False, False
        raise ImportError("private SDK module is missing")

    def _module_exists(self, name: str) -> bool:
        try:
            self._module_path(name)
        except ImportError:
            return False
        return True

    def _private_import(
        self,
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] | list[str] = (),
        level: int = 0,
    ) -> object:
        absolute = name
        if level:
            package = None if globals is None else globals.get("__package__")
            if not isinstance(package, str) or not package:
                raise ImportError("relative private SDK import has no package")
            absolute = importlib.util.resolve_name(f"{'.' * level}{name}", package)
        if absolute == "openai" or absolute.startswith("openai."):
            module = self.import_module(absolute)
            if fromlist:
                for item in fromlist:
                    if item == "*" or hasattr(module, item):
                        continue
                    child_name = f"{absolute}.{item}"
                    if self._module_exists(child_name):
                        self.import_module(child_name)
                    if not hasattr(module, item):
                        raise ImportError("private SDK from-import member is missing")
                return module
            return self.import_module("openai")
        return self._real_import(name, globals, locals, fromlist, level)

    def import_module(self, name: str) -> types.ModuleType:
        if self._failed:
            raise ImportError("private SDK loader is failed")
        existing = self.modules.get(name)
        if existing is not None:
            return existing
        if name != "openai" and not name.startswith("openai."):
            raise ImportError("invalid private SDK module name")
        parent: types.ModuleType | None = None
        child_name = ""
        if "." in name:
            parent_name, _, child_name = name.rpartition(".")
            parent = self.import_module(parent_name)
        path, is_package, is_synthetic = self._module_path(name)
        module = types.ModuleType(name)
        module.__file__ = None if is_synthetic else os.fspath(path)
        module.__package__ = name if is_package else name.rpartition(".")[0]
        module.__loader__ = cast(Any, self)
        module.__spec__ = importlib.machinery.ModuleSpec(
            name,
            loader=None,
            origin=None if is_synthetic else os.fspath(path),
            is_package=is_package,
        )
        if is_package:
            module.__path__ = [os.fspath(path if is_synthetic else path.parent)]
        missing = object()
        previous_parent_member = missing if parent is None else getattr(parent, child_name, missing)
        self.modules[name] = module
        if parent is not None:
            setattr(parent, child_name, module)
        if is_synthetic:
            return module
        private_builtins = dict(vars(builtins))
        private_builtins["__import__"] = _dispatch_private_openai_import
        module.__dict__["__builtins__"] = private_builtins
        try:
            source_bytes = self._read_source(name, path)
            self._authenticate_source_bytes(name, path, source_bytes)
            source = _rewrite_private_openai_source(
                name, source_bytes.decode("utf-8", errors="strict")
            )
            self._before_exec(name, path)
            exec(compile(source, os.fspath(path), "exec"), module.__dict__)
            self._after_exec(name, path, module)
            self.loaded_source_paths[name] = path
        except BaseException:
            self._failed = True
            self.modules.pop(name, None)
            if parent is not None and getattr(parent, child_name, missing) is module:
                if previous_parent_member is missing:
                    delattr(parent, child_name)
                else:
                    setattr(parent, child_name, previous_parent_member)
            raise
        return module

    def _read_source(self, name: str, path: Path) -> bytes:
        del name
        return _read_authenticated_openai_file(self.install, path, _MAX_OPENAI_SOURCE_BYTES)

    def _authenticate_source_bytes(self, name: str, path: Path, source: object) -> None:
        del name
        if type(source) is not bytes:
            raise ImportError("private SDK source bytes are not exact")
        try:
            if path.resolve(strict=True) != path or not path.is_relative_to(self.root):
                raise ImportError("private SDK source escaped the distribution root")
            relative = path.relative_to(self.root.parent).as_posix()
        except (OSError, ValueError):
            raise ImportError("private SDK source escaped the distribution root") from None
        entry = self.install.entries.get(relative)
        if entry is None or len(source) != entry.size:
            raise ImportError("private SDK source size is not authenticated")
        actual = hashlib.sha256(source).hexdigest()
        if not hmac.compare_digest(actual, entry.digest):
            raise ImportError("private SDK source hash is not authenticated")

    def reauthenticate_loaded_sources(self, install: _AuthenticatedOpenAIInstall) -> None:
        if (
            install.root != self.install.root
            or install.record_projection_sha256 != self.install.record_projection_sha256
        ):
            raise ImportError("private SDK source identity changed")
        for name, path in sorted(
            self.loaded_source_paths.items(), key=lambda item: item[0].encode("utf-8")
        ):
            source = self._read_source(name, path)
            self._authenticate_source_bytes(name, path, source)

    def _before_exec(self, name: str, path: Path) -> None:
        del name, path

    def _after_exec(self, name: str, path: Path, module: types.ModuleType) -> None:
        del name, path, module


_ACTIVE_PRIVATE_OPENAI_LOADER: contextvars.ContextVar[_PrivateOpenAITypeLoader | None] = (
    contextvars.ContextVar("active_private_openai_loader", default=None)
)


def _dispatch_private_openai_import(
    name: str,
    globals: dict[str, object] | None = None,
    locals: dict[str, object] | None = None,
    fromlist: tuple[str, ...] | list[str] = (),
    level: int = 0,
) -> object:
    return _active_private_openai_loader()._private_import(name, globals, locals, fromlist, level)


@contextmanager
def _isolated_openai_type_modules(
    loader: _PrivateOpenAITypeLoader | None = None,
) -> typing.Iterator[None]:
    if loader is None:
        loader = _PrivateOpenAITypeLoader()
    token = _ACTIVE_PRIVATE_OPENAI_LOADER.set(loader)
    try:
        yield
    finally:
        _ACTIVE_PRIVATE_OPENAI_LOADER.reset(token)


def _active_private_openai_loader() -> _PrivateOpenAITypeLoader:
    loader = _ACTIVE_PRIVATE_OPENAI_LOADER.get()
    if loader is None:
        raise RuntimeError("private OpenAI loader is inactive")
    return loader


def _import_sdk_request_contract_types() -> tuple[object, tuple[object, ...]]:
    module = _active_private_openai_loader().import_module(
        "openai.types.responses.response_create_params"
    )
    response_create_params = module.ResponseCreateParams

    return response_create_params, get_args(response_create_params)


def _import_sdk_response_contract_type() -> object:
    module = _active_private_openai_loader().import_module("openai.types.responses.response")

    return module.Response


def _import_sdk_expected_request_anchors() -> tuple[object, object]:
    request_module = _active_private_openai_loader().import_module(
        "openai.types.responses.response_create_params"
    )

    return (
        request_module.ResponseCreateParamsNonStreaming,
        request_module.ResponseCreateParamsStreaming,
    )


def _import_sdk_expected_response_anchor() -> object:
    response_module = _active_private_openai_loader().import_module(
        "openai.types.responses.response"
    )
    return response_module.Response


def _load_sdk_request_contract_types() -> tuple[object, tuple[object, ...]]:
    return _import_sdk_request_contract_types()


def _load_sdk_response_contract_type() -> object:
    return _import_sdk_response_contract_type()


def _load_sdk_expected_request_anchors() -> tuple[object, object]:
    return _import_sdk_expected_request_anchors()


def _load_sdk_expected_response_anchor() -> object:
    return _import_sdk_expected_response_anchor()


def _annotation_branches(annotation: object) -> tuple[object, ...]:
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return tuple(item for item in get_args(annotation) if item is not type(None))
    return (annotation,)


def _sdk_type_hints(value: type[object]) -> dict[str, object]:
    module = _active_private_openai_loader().modules[value.__module__]
    namespace = vars(module)
    return get_type_hints(value, globalns=namespace, localns=namespace)


def _resolved_sdk_model_annotation(owner: type[BaseModel], annotation: object) -> object:
    if annotation is Any or annotation is object:
        return annotation
    if not isinstance(annotation, (str, ForwardRef)):
        return annotation
    module = _active_private_openai_loader().modules[owner.__module__]
    namespace = vars(module)
    holder = type("_SDKAnnotationHolder", (), {"__annotations__": {"value": annotation}})
    return get_type_hints(holder, globalns=namespace, localns=namespace)["value"]


def _sdk_model_field_annotation(owner: type[BaseModel], field_name: str) -> object:
    raw_fields = vars(owner).get("__pydantic_fields__")
    raw_annotations = vars(owner).get("__annotations__")
    if (
        type(raw_fields) is not dict
        or type(raw_annotations) is not dict
        or field_name not in raw_fields
        or field_name not in raw_annotations
    ):
        raise TypeError("private SDK model field is missing")
    field = raw_fields[field_name]
    if type(field) is not FieldInfo:
        raise TypeError("private SDK model field is invalid")
    field_annotation = _resolved_sdk_model_annotation(owner, field.annotation)
    source_annotation = _resolved_sdk_model_annotation(owner, raw_annotations[field_name])
    if field_annotation is Any or field_annotation is object:
        raise TypeError("private SDK model field is untyped")
    return source_annotation


def _typed_path_exists(root: object, path: str) -> bool:
    branches: tuple[object, ...] = (root,)
    for component in path.split(".")[1:]:
        next_branches: list[object] = []
        for branch in branches:
            if branch is Any:
                return False
            if not isinstance(branch, type) or not issubclass(branch, BaseModel):
                return False
            try:
                annotation = _sdk_model_field_annotation(branch, component)
            except (KeyError, NameError, TypeError):
                return False
            next_branches.extend(_annotation_branches(annotation))
        branches = tuple(next_branches)
    return bool(branches) and all(branch is not Any and branch is not object for branch in branches)


class _CachedPrivateOpenAIGraph(typing.NamedTuple):
    key: tuple[Path, str]
    loader: _PrivateOpenAITypeLoader


_PRIVATE_OPENAI_GRAPH_LOCK = threading.RLock()
_PRIVATE_OPENAI_GRAPH: _CachedPrivateOpenAIGraph | None = None


def _verify_sdk_type_seams_in_process() -> tuple[bool, bool, _AuthenticatedOpenAIInstall | None]:
    global _PRIVATE_OPENAI_GRAPH

    request_failed = False
    response_failed = False
    install: _AuthenticatedOpenAIInstall | None = None
    loader: _PrivateOpenAITypeLoader | None = None
    cache_eligible = False
    try:
        install = _authenticate_openai_install()
        key = (install.root, install.record_projection_sha256)
        cache_eligible = _private_openai_verifier_seams_are_exact()
        cached = _PRIVATE_OPENAI_GRAPH
        if cache_eligible and cached is not None:
            if cached.key != key:
                raise ImportError("authenticated OpenAI install identity changed")
            cached.loader.reauthenticate_loaded_sources(install)
            loader = cached.loader
        else:
            loader = _PrivateOpenAITypeLoader(install)
        with _isolated_openai_type_modules(loader):
            try:
                request_union, candidate_members = _load_sdk_request_contract_types()
                expected_members = _load_sdk_expected_request_anchors()
                typed_expected = cast(tuple[type[object], ...], expected_members)
                union_members = get_args(request_union)
                identity_valid = (
                    len(candidate_members) == len(expected_members)
                    and all(
                        candidate is expected
                        for candidate, expected in zip(
                            candidate_members, expected_members, strict=True
                        )
                    )
                    and len(union_members) == len(expected_members)
                    and all(
                        candidate is expected
                        for candidate, expected in zip(union_members, expected_members, strict=True)
                    )
                )
                expected_names = (
                    (
                        "openai.types.responses.response_create_params",
                        "ResponseCreateParamsNonStreaming",
                    ),
                    (
                        "openai.types.responses.response_create_params",
                        "ResponseCreateParamsStreaming",
                    ),
                )
                if (
                    not identity_valid
                    or tuple((member.__module__, member.__qualname__) for member in typed_expected)
                    != expected_names
                ):
                    request_failed = True
                else:
                    hints = tuple(_sdk_type_hints(member) for member in typed_expected)
                    if len(hints) != 2 or any(
                        field not in member_hints
                        for member_hints in hints
                        for field in BENCHMARK_OPENAI_REQUEST_FIELDS_V1
                    ):
                        request_failed = True
            except Exception:
                request_failed = True
            if not request_failed:
                try:
                    response = _load_sdk_response_contract_type()
                    expected_response = _load_sdk_expected_response_anchor()
                    if (
                        not isinstance(response, type)
                        or response is not expected_response
                        or response.__module__ != "openai.types.responses.response"
                        or response.__qualname__ != "Response"
                        or any(
                            not _typed_path_exists(response, path)
                            for path in (
                                *BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1,
                                *BENCHMARK_OPENAI_RESPONSE_PATHS_V1,
                                BENCHMARK_OPENAI_RETURNED_MODEL_PATH_V1,
                            )
                        )
                    ):
                        response_failed = True
                except Exception:
                    response_failed = True
    except Exception:
        request_failed = True
    if (
        not request_failed
        and not response_failed
        and cache_eligible
        and install is not None
        and loader is not None
        and _PRIVATE_OPENAI_GRAPH is None
    ):
        _PRIVATE_OPENAI_GRAPH = _CachedPrivateOpenAIGraph(
            (install.root, install.record_projection_sha256), loader
        )
    return request_failed, response_failed, install


def _private_openai_verifier_seams() -> tuple[object, ...]:
    return (
        _read_bounded_regular_file,
        _read_openai_record_bytes,
        _decode_record_digest,
        _validated_record_path,
        _parse_openai_record,
        _authenticate_openai_install,
        _read_authenticated_openai_file,
        _rewrite_private_openai_source,
        _PrivateOpenAITypeLoader.__init__,
        _PrivateOpenAITypeLoader._module_path,
        _PrivateOpenAITypeLoader._module_exists,
        _PrivateOpenAITypeLoader._private_import,
        _PrivateOpenAITypeLoader.import_module,
        _PrivateOpenAITypeLoader._read_source,
        _PrivateOpenAITypeLoader._authenticate_source_bytes,
        _PrivateOpenAITypeLoader.reauthenticate_loaded_sources,
        _PrivateOpenAITypeLoader._before_exec,
        _PrivateOpenAITypeLoader._after_exec,
        _dispatch_private_openai_import,
        _isolated_openai_type_modules,
        _active_private_openai_loader,
        _import_sdk_request_contract_types,
        _import_sdk_response_contract_type,
        _import_sdk_expected_request_anchors,
        _import_sdk_expected_response_anchor,
        _load_sdk_request_contract_types,
        _load_sdk_response_contract_type,
        _load_sdk_expected_request_anchors,
        _load_sdk_expected_response_anchor,
        _annotation_branches,
        _sdk_type_hints,
        _resolved_sdk_model_annotation,
        _sdk_model_field_annotation,
        _typed_path_exists,
        _verify_sdk_type_seams_in_process,
        _public_benchmark_responses_kwargs,
        _canonical_json_v1,
    )


_EXACT_PRIVATE_OPENAI_VERIFIER_SEAMS = _private_openai_verifier_seams()


def _private_openai_verifier_seams_are_exact() -> bool:
    current = _private_openai_verifier_seams()
    return len(current) == len(_EXACT_PRIVATE_OPENAI_VERIFIER_SEAMS) and all(
        actual is expected
        for actual, expected in zip(current, _EXACT_PRIVATE_OPENAI_VERIFIER_SEAMS, strict=True)
    )


def _fail(code: BenchmarkSDKContractErrorCode) -> typing.NoReturn:
    raise BenchmarkSDKContractError(code)


def _build_verified_benchmark_sdk_contract(
    *, c0_uv_lock_bytes: bytes, expected_c0_uv_lock_sha256: Sha256
) -> VerifiedBenchmarkSDKContractV1:
    if type(c0_uv_lock_bytes) is not bytes or not 1 <= len(c0_uv_lock_bytes) <= 1_048_576:
        _fail("lock-entry")
    if (
        type(expected_c0_uv_lock_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_c0_uv_lock_sha256) is None
    ):
        _fail("lock-digest")
    actual_digest = hashlib.sha256(c0_uv_lock_bytes).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_c0_uv_lock_sha256):
        _fail("lock-digest")
    installed_failed = False
    try:
        installed = _installed_openai_version()
    except Exception:
        installed_failed = True
        installed = None
    if installed_failed or type(installed) is not str or installed != "3.3.1":
        _fail("installed-version")
    lock_failed = False
    try:
        decoded = c0_uv_lock_bytes.decode("utf-8", errors="strict")
        lock = tomllib.loads(decoded)
    except Exception:
        lock_failed = True
        lock = {}
    packages = lock.get("package") if isinstance(lock, dict) else None
    if lock_failed or not isinstance(packages, list) or len(packages) > 4096:
        _fail("lock-entry")
    members = [item for item in packages if isinstance(item, dict) and item.get("name") == "openai"]
    expected_member = {
        "name": "openai",
        "version": "3.3.1",
        "source": {"registry": BENCHMARK_OPENAI_LOCK_REGISTRY_V1},
        "dependencies": [{"name": name} for name in BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1],
        "sdist": dict(
            zip(("url", "hash", "size", "upload-time"), BENCHMARK_OPENAI_LOCK_SDIST_V1, strict=True)
        ),
        "wheels": [
            dict(zip(("url", "hash", "size", "upload-time"), wheel, strict=True))
            for wheel in BENCHMARK_OPENAI_LOCK_WHEELS_V1
        ],
    }
    member_has_exact_sizes = (
        len(members) == 1
        and isinstance(members[0].get("sdist"), dict)
        and type(members[0]["sdist"].get("size")) is int
        and isinstance(members[0].get("wheels"), list)
        and all(
            isinstance(wheel, dict) and type(wheel.get("size")) is int
            for wheel in members[0]["wheels"]
        )
    )
    if not member_has_exact_sizes or members[0] != expected_member:
        _fail("lock-entry")
    request_failed, response_failed, authenticated_install = _verify_sdk_type_seams_in_process()
    if request_failed:
        _fail("request-model")
    if response_failed:
        _fail("response-model")
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
    serializer_failed = False
    try:
        projection = _public_benchmark_responses_kwargs(probe)
        serializer_failed = (
            tuple(projection)
            != (
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
            or _canonical_json_v1(projection)
            != BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1
            or hashlib.sha256(BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1).hexdigest()
            != BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1
        )
    except Exception:
        serializer_failed = True
    if serializer_failed:
        _fail("serializer-projection")
    if authenticated_install is None:
        _fail("request-model")
    payload = {
        "schema_version": "VerifiedBenchmarkSDKContractV1",
        "distribution": "openai",
        "installed_version": "3.3.1",
        "c0_uv_lock_sha256": actual_digest,
        "lock_version": "3.3.1",
        "lock_registry": BENCHMARK_OPENAI_LOCK_REGISTRY_V1,
        "lock_dependencies": BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1,
        "lock_sdist_url": BENCHMARK_OPENAI_LOCK_SDIST_V1[0],
        "lock_sdist_hash": BENCHMARK_OPENAI_LOCK_SDIST_V1[1],
        "lock_sdist_size": BENCHMARK_OPENAI_LOCK_SDIST_V1[2],
        "lock_sdist_upload_time": BENCHMARK_OPENAI_LOCK_SDIST_V1[3],
        "lock_wheel_url": BENCHMARK_OPENAI_LOCK_WHEELS_V1[0][0],
        "lock_wheel_hash": BENCHMARK_OPENAI_LOCK_WHEELS_V1[0][1],
        "lock_wheel_size": BENCHMARK_OPENAI_LOCK_WHEELS_V1[0][2],
        "lock_wheel_upload_time": BENCHMARK_OPENAI_LOCK_WHEELS_V1[0][3],
        "request_model_qualified_name": (
            "openai.types.responses.response_create_params.ResponseCreateParams"
        ),
        "response_model_qualified_name": "openai.types.responses.response.Response",
        "request_fields": BENCHMARK_OPENAI_REQUEST_FIELDS_V1,
        "response_paths": BENCHMARK_OPENAI_RESPONSE_PATHS_V1,
        "returned_model_path": BENCHMARK_OPENAI_RETURNED_MODEL_PATH_V1,
        "response_content_paths": BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1,
        "serializer_projection_sha256": BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1,
    }
    record = VerifiedBenchmarkSDKContractV1.model_validate(
        payload | {"contract_sha256": stable_digest("laconian-benchmark-sdk-contract-v1", payload)}
    )
    return record


def require_benchmark_sdk_contract(
    *, c0_uv_lock_bytes: bytes, expected_c0_uv_lock_sha256: Sha256
) -> None:
    with _PRIVATE_OPENAI_GRAPH_LOCK:
        record = _build_verified_benchmark_sdk_contract(
            c0_uv_lock_bytes=c0_uv_lock_bytes,
            expected_c0_uv_lock_sha256=expected_c0_uv_lock_sha256,
        )
        payload = record.model_dump(mode="json", exclude={"contract_sha256"})
        if record.contract_sha256 != stable_digest("laconian-benchmark-sdk-contract-v1", payload):
            _fail("serializer-projection")
        return None


class _ResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _OpenAIConstructor(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesResource


def _provider_error(
    *,
    kind: str,
    message: str,
    retryable: bool,
    delivery_certainty: DeliveryCertainty,
    request_id: str | None = None,
    response_model: str | None = None,
    finish_reason: str | None = None,
    usage: TokenUsage | None = None,
) -> ProviderError:
    return ProviderError(
        kind=kind,
        message=message,
        retryable=retryable,
        request_id=request_id,
        delivery_certainty=delivery_certainty,
        response_model=response_model,
        finish_reason=finish_reason,
        usage=usage,
    )


def _configuration_error(message: str) -> ProviderError:
    return _provider_error(
        kind="configuration",
        message=message,
        retryable=False,
        delivery_certainty="definitely_not_sent",
    )


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _configuration_error("timeout_seconds must be a finite positive number")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        raise _configuration_error("timeout_seconds must be a finite positive number") from None
    if not math.isfinite(normalized) or normalized <= 0:
        raise _configuration_error("timeout_seconds must be a finite positive number")
    return normalized


def _openai_exception_names(error: Exception) -> frozenset[str]:
    return frozenset(base.__name__ for base in type(error).__mro__ if base.__module__ == "openai")


def _request_id(error: Exception) -> str | None:
    value = getattr(error, "request_id", None)
    return value if isinstance(value, str) else None


def _classify_api_error(error: Exception) -> ProviderError | None:
    names = _openai_exception_names(error)
    if "OpenAIError" not in names:
        return None
    raw_status = getattr(error, "status_code", None)
    status = raw_status if type(raw_status) is int else None
    kind = "provider_error"
    retryable = False
    if "APITimeoutError" in names:
        kind = "timeout"
        retryable = True
    elif "APIConnectionError" in names:
        kind = "connection"
        retryable = True
    elif "AuthenticationError" in names or status == 401:
        kind = "authentication"
    elif "PermissionDeniedError" in names or status == 403:
        kind = "permission"
    elif "BadRequestError" in names or status == 400:
        kind = "bad_request"
    elif "RateLimitError" in names or status == 429:
        kind = "rate_limit"
        retryable = True
    elif status in (408, 409):
        kind = "provider_status"
        retryable = True
    elif "InternalServerError" in names or (status is not None and status >= 500):
        kind = "server_error"
        retryable = True
    elif "APIStatusError" in names:
        kind = "provider_status"

    timeout_or_connection = bool(names & {"APITimeoutError", "APIConnectionError"})
    if timeout_or_connection or status == 408 or (status is not None and status >= 500):
        delivery_certainty: DeliveryCertainty = "unknown"
    elif (status is not None and 400 <= status < 500) or names & {
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
        "RateLimitError",
    }:
        delivery_certainty = "definitely_rejected"
    else:
        delivery_certainty = "unknown"

    return _provider_error(
        kind=kind,
        message=str(error),
        retryable=retryable,
        delivery_certainty=delivery_certainty,
        request_id=_request_id(error),
    )


def _malformed(
    message: str,
    request_id: str | None,
    *,
    response_model: str | None = None,
    finish_reason: str | None = None,
    usage: TokenUsage | None = None,
) -> ProviderError:
    return _provider_error(
        kind="malformed_response",
        message=message,
        retryable=False,
        delivery_certainty="response_received",
        request_id=request_id,
        response_model=response_model,
        finish_reason=finish_reason,
        usage=usage,
    )


def _required_count(usage: object, field: str, request_id: str | None) -> int:
    value = getattr(usage, field, None)
    if type(value) is not int or value < 0:
        raise _malformed(
            f"response usage {field} must be a nonnegative integer",
            request_id,
        )
    return value


def _optional_cached_count(usage: object, request_id: str | None) -> int | None:
    details = getattr(usage, "input_tokens_details", None)
    if details is None:
        return None
    missing = object()
    value = getattr(details, "cached_tokens", missing)
    if value is missing:
        raise _malformed(
            "response usage input_tokens_details must expose cached_tokens",
            request_id,
        )
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _malformed(
            "response usage cached_tokens must be a nonnegative integer or null",
            request_id,
        )
    return value


def _parse_usage(raw_usage: object | None, request_id: str | None) -> TokenUsage | None:
    if raw_usage is None:
        return None
    input_tokens = _required_count(raw_usage, "input_tokens", request_id)
    output_tokens = _required_count(raw_usage, "output_tokens", request_id)
    total_tokens = _required_count(raw_usage, "total_tokens", request_id)
    cached_tokens = _optional_cached_count(raw_usage, request_id)
    if total_tokens != input_tokens + output_tokens:
        raise _malformed(
            "response usage total_tokens must equal input_tokens + output_tokens",
            request_id,
        )
    if cached_tokens is not None and cached_tokens > input_tokens:
        raise _malformed(
            "response usage cached_tokens cannot exceed input_tokens",
            request_id,
        )
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_tokens,
    )


def _response_request_id(response: object) -> str | None:
    value = getattr(response, "_request_id", None)
    if value is not None and not isinstance(value, str):
        raise _malformed("response request ID must be a string or null", None)
    return value


def _public_response_error(error: object, request_id: str | None) -> tuple[str, str]:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    if not isinstance(code, str) or not code.strip():
        raise _malformed("response error code must be a nonblank string", request_id)
    if not isinstance(message, str) or not message.strip():
        raise _malformed("response error message must be a nonblank string", request_id)
    return code, message


def _parse_response(response: object) -> GenerationResult:
    metadata_error: str | None = None
    request_id: str | None = None
    try:
        request_id = _response_request_id(response)
    except ProviderError as error:
        metadata_error = error.message

    raw_response_model = getattr(response, "model", None)
    response_model: str | None = None
    if not isinstance(raw_response_model, str) or not raw_response_model.strip():
        metadata_error = metadata_error or "response model must be a nonblank string"
    else:
        response_model = raw_response_model

    raw_status = getattr(response, "status", None)
    status: str | None = None
    if not isinstance(raw_status, str):
        metadata_error = metadata_error or "response status must be a string"
    else:
        status = raw_status

    usage: TokenUsage | None = None
    try:
        usage = _parse_usage(getattr(response, "usage", None), request_id)
    except ProviderError as error:
        metadata_error = metadata_error or error.message

    if metadata_error is not None:
        raise _malformed(
            metadata_error,
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )

    assert response_model is not None
    assert status is not None
    response_error = getattr(response, "error", None)
    if status == "incomplete":
        raise _provider_error(
            kind="incomplete_response",
            message=f"OpenAI response is incomplete for model {response_model}",
            retryable=False,
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status == "failed":
        if response_error is None:
            raise _provider_error(
                kind="failed_response",
                message=f"OpenAI response failed for model {response_model}",
                retryable=False,
                delivery_certainty="response_received",
                request_id=request_id,
                response_model=response_model,
                finish_reason=status,
                usage=usage,
            )
        try:
            code, message = _public_response_error(response_error, request_id)
        except ProviderError as error:
            raise _malformed(
                error.message,
                request_id,
                response_model=response_model,
                finish_reason=status,
                usage=usage,
            ) from None
        raise _provider_error(
            kind=code,
            message=message,
            retryable=code
            in {
                "rate_limit",
                "rate_limit_exceeded",
                "server_error",
                "vector_store_timeout",
            },
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status == "cancelled":
        message = f"OpenAI response was cancelled for model {response_model}"
        if response_error is not None:
            try:
                _, message = _public_response_error(response_error, request_id)
            except ProviderError as error:
                raise _malformed(
                    error.message,
                    request_id,
                    response_model=response_model,
                    finish_reason=status,
                    usage=usage,
                ) from None
        raise _provider_error(
            kind="cancelled",
            message=message,
            retryable=False,
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status != "completed":
        raise _malformed(
            f"response status {status!r} is not a completed terminal status",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if response_error is not None:
        raise _malformed(
            "completed response must not contain an error",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise _malformed(
            "response output_text must be a nonblank string",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    return GenerationResult(
        output_text=output_text,
        usage=usage,
        request_id=request_id,
        finish_reason=status,
        response_model=response_model,
    )


class OpenAIProvider:
    __slots__ = ("_client", "_timeout_seconds")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: object | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._timeout_seconds = _validate_timeout(timeout_seconds)
        if client is not None:
            self._client = cast(_OpenAIClient, client)
            return
        if not isinstance(api_key, str) or not api_key.strip():
            raise _configuration_error("a nonblank OpenAI API key is required")
        if os.environ.get("OPENAI_CUSTOM_HEADERS", "").strip():
            raise _configuration_error(
                "OPENAI_CUSTOM_HEADERS must be unset or blank for reproducible runs"
            )
        try:
            from openai import DefaultHttpxClient, OpenAI
        except ImportError as exc:
            raise _configuration_error(
                "the openai extra is required; install with `uv sync --extra openai`"
            ) from exc
        self._client = cast(
            _OpenAIClient,
            OpenAI(
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
                base_url="https://api.openai.com/v1",
                organization="",
                project="",
                admin_api_key="",
                webhook_secret="",
                http_client=DefaultHttpxClient(trust_env=False),
            ),
        )

    def _validate_request(self, request: GenerationRequest) -> None:
        if not isinstance(request.model, str) or not request.model.strip():
            raise _configuration_error("model must not be blank")
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise _configuration_error("prompt must not be blank")
        if request.instructions is not None and (
            not isinstance(request.instructions, str) or not request.instructions.strip()
        ):
            raise _configuration_error("instructions must be null or nonblank")
        if type(request.max_output_tokens) is not int or request.max_output_tokens < 1:
            raise _configuration_error("max_output_tokens must be a positive integer")
        if request.temperature is not None:
            temperature = request.temperature
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
                raise _configuration_error("temperature must be null or between 0 and 2")
            try:
                normalized_temperature = float(temperature)
            except (OverflowError, TypeError, ValueError):
                raise _configuration_error("temperature must be null or between 0 and 2") from None
            if not math.isfinite(normalized_temperature) or not 0 <= normalized_temperature <= 2:
                raise _configuration_error("temperature must be null or between 0 and 2")
        request_timeout = _validate_timeout(request.timeout_seconds)
        if request_timeout != self._timeout_seconds:
            raise _configuration_error(
                "request timeout_seconds does not match the provider client timeout"
            )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._validate_request(request)
        kwargs: dict[str, object] = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.prompt,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        try:
            response = self._client.responses.create(**kwargs)
        except Exception as exc:
            classified = _classify_api_error(exc)
            if classified is None:
                raise
            raise classified from exc
        return _parse_response(response)
