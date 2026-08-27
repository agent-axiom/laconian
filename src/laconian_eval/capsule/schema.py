"""Strict scalar and enum primitives for generation capsule schemas."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime
from ipaddress import ip_address
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Self, TypeAlias, TypeVar
from urllib.parse import urlsplit
from uuid import RFC_4122, UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)

from laconian_eval.capsule.canonical import canonical_timestamp
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, bounded_utf8_length

Arm: TypeAlias = Literal["baseline", "concise", "caveman", "if"]
ProviderKind: TypeAlias = Literal["fake", "replay", "openai"]
RunPurpose: TypeAlias = Literal[
    "integration_smoke", "development", "confirmatory_author_run", "replication"
]
ClaimIntent: TypeAlias = Literal["none", "exploratory", "confirmatory_candidate"]
DatasetRole: TypeAlias = Literal[
    "smoke", "development", "calibration", "held_out_test", "challenge"
]
ComparisonRole: TypeAlias = Literal["primary", "secondary", "contextual", "diagnostic"]
ProtocolStage: TypeAlias = Literal["scoring", "judging", "inference", "publication"]
DeclaredRequirement: TypeAlias = Literal["optional", "required_for_declared_claim"]
InputRole: TypeAlias = Literal["case", "arm", "replay", "protocol", "runner_source"]
Locale: TypeAlias = Literal["en", "ru"]
CaseCategory: TypeAlias = Literal[
    "direct",
    "coding",
    "preservation",
    "structured-output",
    "uncertainty",
    "safety",
    "user-message",
    "summarization",
]
FilesystemClass: TypeAlias = Literal["ext-family", "xfs", "btrfs", "zfs", "apfs", "hfsplus"]
LifecycleState: TypeAlias = Literal[
    "PREPARED",
    "INTERRUPTED",
    "AMBIGUOUS_INFLIGHT",
    "AUTHENTICATION_STOPPED",
    "GENERATION_COMPLETE",
    "SEALING_INTERRUPTED",
    "SEALED_COMPLETE",
    "SEALED_BLOCKED",
]
VerifyStatus: TypeAlias = Literal["valid", "invalid", "busy", "unsupported"]
OperationalBlocker: TypeAlias = Literal[
    "never_started", "interrupted", "ambiguous_inflight", "authentication_stopped"
]
VerificationWarning: TypeAlias = Literal[
    "broader_permissions",
    "permission_representation_differs",
    "producer_runtime_differs",
    "lock_file_omitted_for_sealed_transport",
]
VerificationErrorCode: TypeAlias = Literal[
    "unsupported_schema",
    "resource_limit",
    "unexpected_path",
    "missing_path",
    "unsafe_path_type",
    "unstable_snapshot",
    "noncanonical_json",
    "invalid_model",
    "hash_mismatch",
    "identity_mismatch",
    "plan_mismatch",
    "history_mismatch",
    "retry_mismatch",
    "lifecycle_mismatch",
    "seal_mismatch",
    "unsupported_filesystem",
    "io_error",
]

PROTOCOL_STAGE_ORDER: tuple[ProtocolStage, ...] = (
    "scoring",
    "judging",
    "inference",
    "publication",
)
OPERATIONAL_BLOCKER_ORDER: tuple[OperationalBlocker, ...] = (
    "never_started",
    "interrupted",
    "ambiguous_inflight",
    "authentication_stopped",
)
VERIFICATION_WARNING_ORDER: tuple[VerificationWarning, ...] = (
    "broader_permissions",
    "permission_representation_differs",
    "producer_runtime_differs",
    "lock_file_omitted_for_sealed_transport",
)
CONSOLE_LAUNCHER_TEMPLATE_SHA256 = (
    "afdb677819f87d2c8e8af0eb2461ea1856b13dec27768546af0175c376ee493d"
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RUN_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]+$")
_CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]+-(?:en|ru)$")
_SCENARIO_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]+$")
_API_KEY_ENV_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_PEP503_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TOP_LEVEL_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOWS_PREFIX_PATTERN = re.compile(r"^[A-Za-z]:")
_CANONICAL_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_EXACT_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_INVALID_PERCENT_ESCAPE_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")
_REG_NAME_PATTERN = re.compile(r"^(?:[A-Za-z0-9\-._~!$&'()*+,;=]|%[0-9A-Fa-f]{2})+$")
_IPV_FUTURE_PATTERN = re.compile(r"^[Vv][0-9A-Fa-f]+\.[A-Za-z0-9\-._~!$&'()*+,;=:]+$")
_URI_NAMESPACE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://.+$")
_HTTP_PATH_PATTERN = re.compile(r"^[A-Za-z0-9\-._~!$&'()*+,;=:@/%]*$")
_HTTP_QUERY_PATTERN = re.compile(r"^[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]*$")
_MEDIA_TYPE_TOKEN = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
_MEDIA_TYPE_QUOTED = r'"(?:[\t !#-\[\]-~]|\\[\t !-~])*"'
_MEDIA_TYPE_PATTERN = re.compile(
    rf"^{_MEDIA_TYPE_TOKEN}/{_MEDIA_TYPE_TOKEN}"
    rf"(?:[ \t]*;[ \t]*{_MEDIA_TYPE_TOKEN}="
    rf"(?:{_MEDIA_TYPE_TOKEN}|{_MEDIA_TYPE_QUOTED}))*$"
)


class CapsuleModel(BaseModel):
    """Capsule-local immutable strict-object base without changing legacy models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Return a fully revalidated copy, including nested capsule models."""

        payload = self.model_dump(mode="python", round_trip=True)
        if deep:
            payload = deepcopy(payload)
        if update is not None:
            payload.update(update)
        return type(self).model_validate(payload)


def _strict_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("value must be a string")
    return value


def _bounded_string(value: str, *, limit: int = RESOURCE_LIMITS_V1.bounded_string_bytes) -> str:
    bounded_utf8_length(value, limit=limit, code="bounded_string_limit")
    return value


def _bounded_nonblank(value: str) -> str:
    _bounded_string(value)
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


def _bounded_diagnostic(value: str) -> str:
    _bounded_string(value, limit=RESOURCE_LIMITS_V1.diagnostic_bytes)
    if not value.strip():
        raise ValueError("diagnostic must not be blank")
    if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value):
        raise ValueError("diagnostic must be sanitized")
    if "  " in value:
        raise ValueError("diagnostic whitespace must be sanitized")
    return value


def _match(pattern: re.Pattern[str], label: str) -> Any:
    def validate(value: str) -> str:
        if pattern.fullmatch(value) is None:
            raise ValueError(f"invalid {label}")
        return value

    return AfterValidator(validate)


BoundedString: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_bounded_string)
]
BoundedNonBlankString: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_bounded_nonblank)
]
DiagnosticString: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_bounded_diagnostic)
]
Sha256: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_SHA256_PATTERN, "SHA-256"),
]
GitObjectId: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_GIT_OBJECT_ID_PATTERN, "Git object ID"),
]
RunName: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_RUN_NAME_PATTERN, "run name"),
]
CaseId: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_CASE_ID_PATTERN, "case ID"),
]
ScenarioId: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_SCENARIO_ID_PATTERN, "scenario ID"),
]
ApiKeyEnvironmentName: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_API_KEY_ENV_PATTERN, "API-key environment name"),
]
NormalizedDistributionName: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_PEP503_NAME_PATTERN, "normalized distribution name"),
]
TopLevelModuleName: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_string),
    _match(_TOP_LEVEL_MODULE_PATTERN, "top-level module name"),
]


def _namespaced_string(value: str) -> str:
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    ):
        raise ValueError("namespaced string must not contain whitespace or controls")
    if "\\" in value:
        raise ValueError("namespaced string must not contain backslashes")
    if _URI_NAMESPACE_PATTERN.fullmatch(value) is not None:
        return value
    if value[0] in "/:" or value[-1] in "/:":
        raise ValueError("namespaced string separators require values on both sides")
    if "/" in value:
        if "//" in value or any(component in ("", ".", "..") for component in value.split("/")):
            raise ValueError("namespaced string components must be nonempty")
        return value
    if ":" in value:
        if "::" in value or any(component in ("", ".", "..") for component in value.split(":")):
            raise ValueError("namespaced string components must be nonempty")
        return value
    if "." in value:
        if any(component in ("", ".", "..") for component in value.split(".")):
            raise ValueError("namespaced string components must be nonempty")
        return value
    raise ValueError("namespaced string must contain a namespace separator")


def _media_type(value: str) -> str:
    if not value.isascii() or _MEDIA_TYPE_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid media type")
    return value


NamespacedString: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_nonblank),
    AfterValidator(_namespaced_string),
]
MediaType: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_nonblank),
    AfterValidator(_media_type),
]

StrictNonNegativeInt: TypeAlias = Annotated[int, Field(strict=True, ge=0)]
StrictPositiveInt: TypeAlias = Annotated[int, Field(strict=True, ge=1)]
StrictSigned64Int: TypeAlias = Annotated[int, Field(strict=True, ge=-(2**63), le=2**63 - 1)]
StrictRepetitionCount: TypeAlias = Annotated[int, Field(strict=True, ge=1, le=100)]
StrictMaxOutputTokens: TypeAlias = Annotated[
    int,
    Field(strict=True, ge=1, le=RESOURCE_LIMITS_V1.output_tokens_per_request),
]
StrictTransientRetries: TypeAlias = Annotated[int, Field(strict=True, ge=0, le=5)]


def _strict_finite_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be an integer or float")
    try:
        projected = float(value)
    except (OverflowError, ValueError):
        raise ValueError("value must be representable as a finite float") from None
    if not math.isfinite(projected):
        raise ValueError("value must be finite")
    return 0.0 if projected == 0.0 else projected


def _nonnegative_float(value: float) -> float:
    if value < 0.0:
        raise ValueError("value must be nonnegative")
    return value


def _temperature(value: float) -> float:
    if not 0.0 <= value <= 2.0:
        raise ValueError("temperature must be between zero and two")
    return value


def _timeout(value: float) -> float:
    if not 0.0 < value <= 600.0:
        raise ValueError("timeout must be greater than zero and at most 600")
    return value


FiniteFloat: TypeAlias = Annotated[float, BeforeValidator(_strict_finite_float)]
NonNegativeFiniteFloat: TypeAlias = Annotated[FiniteFloat, AfterValidator(_nonnegative_float)]
Temperature: TypeAlias = Annotated[FiniteFloat, AfterValidator(_temperature)]
TimeoutSeconds: TypeAlias = Annotated[FiniteFloat, AfterValidator(_timeout)]


def _exact_date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError("date must not be a datetime")
    if isinstance(value, date):
        return value
    if type(value) is not str or _EXACT_DATE_PATTERN.fullmatch(value) is None:
        raise ValueError("date must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("date is invalid") from None
    if parsed.isoformat() != value:
        raise ValueError("date must use canonical spelling")
    return parsed


ExactDate: TypeAlias = Annotated[
    date,
    BeforeValidator(_exact_date),
    PlainSerializer(lambda value: value.isoformat(), return_type=str, when_used="json"),
]


def _canonical_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
    if type(value) is not str or _CANONICAL_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("timestamp must use canonical UTC spelling")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("timestamp is invalid") from None
    if canonical_timestamp(parsed) != value:
        raise ValueError("timestamp must use canonical UTC spelling")
    return parsed


CanonicalTimestamp: TypeAlias = Annotated[
    datetime,
    BeforeValidator(_canonical_datetime),
    PlainSerializer(canonical_timestamp, return_type=str, when_used="json"),
]


def _uuid4(value: object) -> UUID:
    if isinstance(value, UUID):
        parsed = value
    elif type(value) is str:
        try:
            parsed = UUID(value)
        except ValueError:
            raise ValueError("value must be a UUID") from None
        if str(parsed) != value:
            raise ValueError("UUID must use lowercase hyphenated spelling")
    else:
        raise ValueError("value must be a UUID")
    if parsed.version != 4 or parsed.variant != RFC_4122:
        raise ValueError("UUID must be version 4")
    return parsed


UUID4: TypeAlias = Annotated[
    UUID,
    BeforeValidator(_uuid4),
    PlainSerializer(str, return_type=str, when_used="json"),
]


def _relative_posix_path(value: str) -> str:
    _bounded_string(value)
    if not value or value == ".":
        raise ValueError("path must be nonempty")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError("path must be relative")
    if _WINDOWS_PREFIX_PATTERN.match(value) is not None or "\\" in value:
        raise ValueError("path must not use a platform prefix or separator")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("path must not contain controls")
    components = value.split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ValueError("path must be normalized and non-traversing")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or parsed.as_posix() != value:
        raise ValueError("path must be normalized relative POSIX")
    return value


RelativePosixPath: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_relative_posix_path)
]
validate_relative_posix_path = _relative_posix_path


def _exact_ascii_http_url(value: str) -> str:
    _bounded_string(value)
    if not value.isascii():
        raise ValueError("URL must be ASCII")
    if value != value.strip() or any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    ):
        raise ValueError("URL must not contain whitespace or controls")
    if "\\" in value or "#" in value:
        raise ValueError("URL must not contain a backslash or fragment")
    if _INVALID_PERCENT_ESCAPE_PATTERN.search(value) is not None:
        raise ValueError("URL contains an invalid percent escape")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError("URL is invalid") from None
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError("URL must be absolute HTTP(S)")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValueError("URL must not contain user information")
    if parsed.hostname is None or not parsed.hostname:
        raise ValueError("URL must contain a host")
    if _HTTP_PATH_PATTERN.fullmatch(parsed.path) is None:
        raise ValueError("URL path contains an invalid character")
    if _HTTP_QUERY_PATTERN.fullmatch(parsed.query) is None:
        raise ValueError("URL query contains an invalid character")
    authority = parsed.netloc
    if authority.startswith("["):
        closing_bracket = authority.find("]")
        literal = authority[1:closing_bracket]
        port_suffix = authority[closing_bracket + 1 :]
        if port_suffix and (not port_suffix.startswith(":") or not port_suffix[1:].isdigit()):
            raise ValueError("URL IP-literal suffix is invalid")
        if port_suffix == ":":
            raise ValueError("URL port must not be empty")
        if _IPV_FUTURE_PATTERN.fullmatch(literal) is None:
            try:
                parsed_ip = ip_address(literal)
            except ValueError:
                raise ValueError("URL IP literal is invalid") from None
            if parsed_ip.version != 6 or "%" in literal:
                raise ValueError("bracketed URL host must be IPv6 or IPvFuture")
    else:
        if "[" in authority or "]" in authority or authority.endswith(":"):
            raise ValueError("URL host or port is invalid")
        host = parsed.hostname
        assert host is not None
        if _REG_NAME_PATTERN.fullmatch(host) is None:
            raise ValueError("URL host is invalid")
    return value


ExactAsciiHttpUrl: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_exact_ascii_http_url)
]

_T = TypeVar("_T")


def require_unique(values: tuple[_T, ...], *, label: str) -> tuple[_T, ...]:
    """Return a tuple after equality-based duplicate rejection."""

    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


def require_fixed_order(
    values: tuple[_T, ...], *, order: tuple[_T, ...], label: str
) -> tuple[_T, ...]:
    """Require a duplicate-free subsequence of a fixed enum order."""

    require_unique(values, label=label)
    positions = {value: position for position, value in enumerate(order)}
    if tuple(sorted(values, key=positions.__getitem__)) != values:
        raise ValueError(f"{label} must use fixed enum order")
    return values


def require_utf8_sorted_unique(values: tuple[_T, ...], *, key: Any, label: str) -> tuple[_T, ...]:
    """Require exact UTF-8 byte ordering and uniqueness for a projected key."""

    keys = tuple(key(value) for value in values)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} must be unique")
    if keys != tuple(sorted(keys, key=lambda value: value.encode("utf-8"))):
        raise ValueError(f"{label} must be sorted by UTF-8 bytes")
    return values
