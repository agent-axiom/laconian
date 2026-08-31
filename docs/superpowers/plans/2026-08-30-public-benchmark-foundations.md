# Public Benchmark Foundations Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the immutable generation foundations required by the approved three-model benchmark: a neutral severity-annotated corpus, exact native-v2 reasoning, verbosity, no-write prompt-cache, and literal default-service-tier requests, complete token-usage and returned-tier evidence, conservative standard-tier input bounds, stable parent request identities, 36 scenario shards, public sealing, sealed verification, a verified deterministic scored sidecar, and safely restorable uncompressed checkpoints.

**Architecture:** Keep authored experiment data, deterministic parent planning, mutable capsule execution, immutable sealing, and checkpoint transport as separate trust boundaries. The parent-planning API contains no run UUID; parent request identities derive from immutable manifest, cache/tier policy, and request input bounds. Each shard captures the complete parent plan plus one hash-bound 40-row projection, while per-attempt and response identities remain bound to the capsule run. Sealing and checkpoint restore reuse one exact capsule-tree policy, descriptor-relative no-follow I/O, canonical JSON, bounded streaming, fsync, and atomic no-replace publication.

**Tech Stack:** Python 3.11+, Pydantic 2 strict/frozen models, OpenAI Responses API adapter, canonical JSON/JSONL and SHA-256, POSIX descriptor APIs, deterministic USTAR encoding, pytest, Ruff, and mypy.

---

## Execution contract

- Approved normative design: [Public Three-Model Benchmark Pipeline Design](../specs/2026-08-30-public-three-model-benchmark-design.md) at full SHA `e67ad191623316f69523b051fba48ec2e7492493`, especially Sections 6.1–6.6, 7.1–7.3, 8, 14.1, and 16. This plan is synchronized to the approved legacy-v1 price-migration and Foundations Tasks 3–5 preflight-closure amendment. Amendment-dependent implementation in Tasks 2–5 may proceed only from a handoff that records this governance-only successor as `PLAN_BASE_SHA`.
- Approval metadata: this governance-only successor records the maintainer/user's exact 2026-08-31 approval message `Одобряю amendment e67ad191623316f69523b051fba48ec2e7492493` without changing normative behavior. Governance-only successor `d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad` and its approval of `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126` remain historical authority for the prior baseline. Before amendment-dependent Task 2 is committed, the handoff records this already-created successor's full SHA as `PLAN_BASE_SHA`; any later normative amendment re-blocks every affected task until separately approved and governance-recorded.
- Seal grammar: [Laconian v0.1 Generation Capsule Design](../specs/2026-08-24-v0.1-generation-capsule-design.md), especially Sections 14–17.
- Provider cache/usage contract: [OpenAI Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create), [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching), and [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model), frozen into the reviewed manifest rather than fetched during execution.
- Worktree: `/Users/if/PycharmProjects/agent-axiom/laconian/.worktrees/public-benchmark-design`.
- Starting point for amendment-dependent Tasks 2–5: this governance-only successor, which synchronizes the approved normative amendment and this Foundations plan without changing normative behavior. Task 1 remains already-committed baseline-authorized history. Before amendment-dependent Task 2 is committed, the handoff records this successor's already-created full commit as `PLAN_BASE_SHA`; the plan source does not embed its own future commit SHA. Keep remaining implementation on an isolated `codex/` branch or worktree based on that exact commit.
- This slice ends when exact capsule bytes can be prepared as a scenario projection, executed with the approved wire fields, finalized, verified without a lock on transport storage, packed as uncompressed USTAR, restored into a new directory, and fully reverified.
- Protocol-review attestations, paired-tag construction, campaign authority/state, downstream orchestration, analysis, judging, human review, and repository release mechanics remain owned by the other slice plans. Slice 1 implements none of those authorities. It does bind every downstream C0 input it owns: exact code and `uv.lock`, provider/request policy, price evidence, corpus and parent/shard plans, capsule/seal/checkpoint schemas, and their canonical digests.
- No test reads a real credential, opens a network connection, depends on wall-clock sleeps, invokes `tar -xf`, or calls `tarfile.extractall`.
- Every public error added here stores a stable code, renders a constant message, and excludes paths, provider payloads, output text, environment values, and archive member bytes.
- Every mutation uses already-open descriptors, `O_NOFOLLOW`, exclusive creation, explicit fsync, and no-replace publication. A failed operation never overwrites an existing capsule, archive, sidecar, seal, or restored directory.
- Each task follows RED, observed expected failure, minimal GREEN, focused regression, and one commit. Run the final full gate only after all focused commits are green.

## Slice 1 file boundary

```text
evals/cases/response-smoke.yaml                 remove 14 ungrounded sentence caps; freeze warning severities
evals/README.md                                 document neutrality and severity contract
src/laconian_eval/models.py                     strict semantic-warning severity schema
src/laconian_eval/capsule/schema.py             reasoning/verbosity/cache-TTL/service-tier and planning-input scalar types
src/laconian_eval/capsule/manifest_models.py    authored/resolved native-v2 settings plus private legacy-v1 price projection
src/laconian_eval/capsule/capture.py            v1-compatible resolution and priced-v1 pre-capture refusal
src/laconian_eval/providers/base.py             request/policy, bounds, reasoning/four status aliases, and TokenUsage
src/laconian_eval/providers/openai.py           SDK-3.3.1 exact Responses wire and canonical response-path parsing
src/laconian_eval/providers/replay.py           separate strict benchmark replay while preserving legacy replay
src/laconian_eval/providers/__init__.py         SDK exports plus ServiceTier/four statuses; no outcome/evidence/protocol
src/laconian_eval/capsule/attempts.py            sole OutputString/outcome/evidence/protocol owner and attempt evidence
src/laconian_eval/capsule/execution.py           reconstructed benchmark requests and canonical attempt evidence
src/laconian_eval/capsule/planning.py            stable parent plan identities and validation
src/laconian_eval/capsule/sharding.py            ShardPlanV1 construction, hashing, projection, and coverage
src/laconian_eval/capsule/record_models.py       captured parent/shard planning-input records
src/laconian_eval/capsule/prepare.py             full-parent and captured-shard capsule preparation
src/laconian_eval/capsule/tree_policy.py         shared exact capsule member allowlist
src/laconian_eval/capsule/seal_models.py         strict SealV1 schema and deterministic derivation
src/laconian_eval/capsule/finalize.py            normalized history and atomic seal publication
src/laconian_eval/capsule/verify.py              parent/shard, seal, and lockless sealed verification
src/laconian_eval/capsule/scorable.py            deterministic terminal RawAttemptV2 hard-score projection
src/laconian_eval/capsule/sidecars.py             seal-bound scored sidecar writer and verified loader
src/laconian_eval/scoring.py                      shared deterministic hard-check calculation
src/laconian_eval/capsule/filesystem.py          descriptor-relative, no-follow, no-replace filesystem helpers
src/laconian_eval/capsule/limits.py              bounded archive/member/restore limits
src/laconian_eval/capsule/checkpoint.py          deterministic USTAR pack and safe one-pass restore
src/laconian_eval/cli.py                         public finalize command
tests/test_models.py                              warning-severity schema tests
tests/test_smoke_cases.py                         exact corpus neutrality/severity assertions
tests/test_public_contract.py                     cumulative corpus, provider, and capsule-name contract
tests/capsule_helpers.py                          complete manifest/usage/plan payload builders
tests/capsule/test_manifest_models.py             new generation-setting schema tests
tests/capsule/test_capture.py                     v1/v2 resolution compatibility
tests/capsule/test_planning.py                    request hash and stable parent identity tests
tests/test_openai_provider.py                     exact wire, returned tier, bound, and usage-detail parsing
tests/test_providers.py                           replay cache-write/reasoning-token/tier compatibility
tests/fixtures/replay-responses.yaml              unchanged legacy replay fixture
tests/fixtures/replay-public-benchmark-responses.yaml strict benchmark-only replay evidence
tests/capsule/test_attempts_v2.py                 canonical cache-write, tier, and visible-token evidence
tests/capsule/test_execution.py                   manifest-to-request/attempt tier reconstruction
tests/capsule/test_sharding.py                     36-by-40 partition and hostile-plan tests
tests/capsule/test_prepare.py                      captured shard preparation tests
tests/capsule/test_verify_prepared.py              prepared-capsule descriptor and projection verification
tests/capsule/test_record_models.py                planning-input record schema tests
tests/capsule/test_tree_policy.py                  shared member allowlist tests
tests/capsule/test_seal_models.py                  strict SealV1 and derivation tests
tests/capsule/test_finalize.py                     crash-safe/idempotent finalization tests
tests/capsule/test_verify_sealed.py                sealed and lockless transport verification
tests/capsule/test_cli_finalize.py                 stable finalize CLI behavior
tests/capsule/test_scorable.py                     exact terminal scoring and row-order projection
tests/capsule/test_sidecars.py                     sealed sidecar binding and verified loading
tests/capsule/test_limits.py                       bounded archive/member/restore limit tests
tests/capsule/test_checkpoint.py                   USTAR round-trip and hostile restore tests
pyproject.toml                                    pin OpenAI SDK exactly 3.3.1
uv.lock                                           lock SDK 3.3.1; preflight later binds the C0 member hash
```

`runner.py`, legacy `GenerationRequest`, legacy `RawAttempt`, legacy `TokenUsageModel`, and legacy reports continue to expose their current byte-compatible non-capsule contract. Public benchmark fields live only in `PublicBenchmarkRequestV1` and `PublicBenchmarkRequestPolicyV1`; no new default is added to the shared legacy request. The exact applied-cache/read/write/reasoning/tier/model evidence is preserved by capsule `RawAttemptV2`; no legacy projection may enter the public campaign ledger.

## Stable interfaces and canonical preimages

### Corpus severity

```python
# src/laconian_eval/models.py
WarningSeverity = Literal["material", "critical"]


class SemanticRubric(StrictModel):
    required_facts: tuple[str, ...] = ()
    material_warning: str | None = None
    material_warning_severity: WarningSeverity | None = None

    @model_validator(mode="after")
    def validate_warning_severity(self) -> Self:
        if (self.material_warning is None) != (self.material_warning_severity is None):
            raise ValueError("material warning and severity must be present together")
        return self
```

### Generation settings and wire request

```python
# src/laconian_eval/capsule/schema.py
ReasoningEffort = Literal["low", "medium", "high"]
TextVerbosity = Literal["low", "medium", "high"]
ReasoningMode = Literal["omitted"]
PromptCacheMode = Literal["explicit"]
PromptCacheTTL = Literal["30m"]
ServiceTier = Literal["default"]
PublicBenchmarkModelId = Literal["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]


# src/laconian_eval/capsule/manifest_models.py
class SourceGenerationSettingsV2(CapsuleModel):
    max_output_tokens: StrictMaxOutputTokens = 1024
    temperature: Temperature | None = None
    reasoning_effort: ReasoningEffort | None = None
    text_verbosity: TextVerbosity | None = None
    reasoning_mode: ReasoningMode = "omitted"
    prompt_cache_mode: PromptCacheMode = "explicit"
    prompt_cache_ttl: PromptCacheTTL = "30m"
    service_tier: ServiceTier = "default"


class ResolvedGenerationSettingsV2(CapsuleModel):
    max_output_tokens: StrictMaxOutputTokens
    temperature: Temperature | None
    reasoning_effort: ReasoningEffort | None
    text_verbosity: TextVerbosity | None
    reasoning_mode: ReasoningMode
    prompt_cache_mode: PromptCacheMode
    prompt_cache_ttl: PromptCacheTTL
    service_tier: ServiceTier


PriceDimensionV1 = Literal[
    "ordinary_uncached_input_per_million",
    "cache_read_input_per_million",
    "cache_write_input_per_million",
    "visible_output_per_million",
    "reasoning_output_per_million",
]


class PriceSourceEvidenceV1(CapsuleModel):
    dimension: PriceDimensionV1
    source_url: ExactAsciiHttpUrl
    effective_date: ExactDate
    usd_per_million: NonNegativeFiniteFloat
    source_sha256: Sha256


class SourcePriceSnapshotV1(CapsuleModel):
    currency: Literal["USD"] = "USD"
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    service_tier: ServiceTier = "default"
    ordinary_uncached_input_per_million: NonNegativeFiniteFloat
    cache_read_input_per_million: NonNegativeFiniteFloat
    cache_write_input_per_million: NonNegativeFiniteFloat
    visible_output_per_million: NonNegativeFiniteFloat
    reasoning_output_per_million: NonNegativeFiniteFloat
    source_evidence: tuple[PriceSourceEvidenceV1, ...]


class ResolvedPriceSnapshotV1(CapsuleModel):
    currency: Literal["USD"]
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    service_tier: ServiceTier
    ordinary_uncached_input_per_million: NonNegativeFiniteFloat
    cache_read_input_per_million: NonNegativeFiniteFloat
    cache_write_input_per_million: NonNegativeFiniteFloat
    visible_output_per_million: NonNegativeFiniteFloat
    reasoning_output_per_million: NonNegativeFiniteFloat
    source_evidence: tuple[PriceSourceEvidenceV1, ...]


# src/laconian_eval/capsule/manifest_models.py — private compatibility projection only.
class _V1LegacyPriceSnapshotProjection(CapsuleModel):
    currency: Literal["USD"] = "USD"
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    input_per_million: NonNegativeFiniteFloat
    cached_input_per_million: NonNegativeFiniteFloat | None = None
    output_per_million: NonNegativeFiniteFloat


# src/laconian_eval/providers/base.py — leave legacy GenerationRequest unchanged.
class PublicBenchmarkRequestPolicyV1(CapsuleModel):
    schema_version: Literal["PublicBenchmarkRequestPolicyV1"]
    service_tier: ServiceTier
    prompt_cache_mode: PromptCacheMode
    prompt_cache_ttl: PromptCacheTTL
    reasoning_mode: ReasoningMode
    input_token_bound_version: Literal["openai-utf8-envelope-v1"]
    max_input_tokens: Literal[272000]


@dataclass(frozen=True, slots=True)
class PublicBenchmarkRequestV1:
    case_id: str
    arm: str
    repetition: int
    requested_model_id: PublicBenchmarkModelId
    instructions: str | None
    prompt: str
    max_output_tokens: int
    temperature: float | None
    timeout_seconds: float
    policy: PublicBenchmarkRequestPolicyV1
    reasoning_effort: ReasoningEffort | None = None
    text_verbosity: TextVerbosity | None = None
```

All five public price dimensions are required, non-null, and independently sourced; numeric zero is
allowed only when the source explicitly attests it. Compatibility resolution for historical
snapshots stays outside the public validator. The canonical digest binds literal
`service_tier="default"`; `auto`, `flex`, `priority`, `ultrafast`, omission, an unsourced rate, or a
long-context price class is invalid. Runtime reuses these exact field names and does not redefine
the schema.

`RunManifest` remains the sole public schema-v1 validation boundary. `project_v1_manifest` accepts
a legacy three-rate `price_snapshot` only as
`_V1LegacyPriceSnapshotProjection`; both `V1UpgradeProjection.price_snapshot` and
`_V1ProjectionInput.price_snapshot` use that private type. It is never coerced into either native-v2
snapshot shape. The projection retains `source_url` as exact authored text; currency, date, and
numeric members retain legacy-normalized semantics, and `RunManifest`'s normalized URL is
validation-only rather than projection authority. A non-null private legacy snapshot makes
`capture_authored_inputs` and direct
`upgrade_v1_manifest` raise `CaptureError(code="v1_price_snapshot_requires_native_v2")`. Its constant
message is exactly:

```text
v1 price snapshots require explicit migration to a native-v2 five-rate source-evidence manifest
```

This guard runs before case/arm/replay/protocol capture and before any provider, credential, or
client access. No legacy rate/evidence is synthesized, dropped, renamed, or mapped; unpriced v1
upgrades are unchanged.

Both snapshot validators require `source_evidence` in the literal `PriceDimensionV1` order with no
missing, extra, duplicate, or reordered member. Each `usd_per_million` must exactly equal the
corresponding snapshot field, and `source_sha256` is recomputed from the preceding evidence fields;
a zero rate without its own exact source record is invalid.

The standard-tier scheduling bound is a frozen, provider-specific conservative upper bound. One
token is reserved per UTF-8 request byte, plus a deliberately large fixed allowance for provider
framing. This is a reservation bound, not a tokenizer estimate:

```python
# src/laconian_eval/providers/base.py
INPUT_TOKEN_BOUND_VERSION = "openai-utf8-envelope-v1"
OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE = 65_536
OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS = 272_000


def conservative_input_token_bound(*, instruction_utf8_bytes: int, prompt_utf8_bytes: int) -> int:
    """Return one-token-per-byte plus the frozen Responses-envelope allowance."""
    if (
        type(instruction_utf8_bytes) is not int
        or instruction_utf8_bytes < 0
        or type(prompt_utf8_bytes) is not int
        or prompt_utf8_bytes < 0
    ):
        raise ValueError("input byte counts must be nonnegative integers")
    return instruction_utf8_bytes + prompt_utf8_bytes + OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE
```

Every public-campaign request must have the value returned by
`conservative_input_token_bound(instruction_utf8_bytes=instruction_utf8_bytes,
prompt_utf8_bytes=prompt_utf8_bytes) <= OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS`; equality is allowed.
The adapter recomputes this from the exact strings before any provider call, while planning stores
the same value in the row used by later spend reservation. A request above the limit is a
`definitely_not_sent` configuration failure. The campaign never relies on automatic truncation or a
long-context price multiplier.

For the confirmatory request, the adapter sends these exact additional kwargs:

```python
kwargs["reasoning"] = {"effort": "medium"}
kwargs["text"] = {"verbosity": "medium"}
kwargs["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
kwargs["service_tier"] = "default"
```

`PublicBenchmarkRequestV1.instructions` remains exactly `str | None` and `.prompt` remains exactly
`str`; neither request field is widened to an object union. Before serialization, call the generic
recursive cache-control helper on those real string leaves. Test the helper directly with synthetic
dict/list/tuple trees carrying forbidden keys at multiple depths and with real string leaves. It
rejects every exact built-in string key that starts with `prompt_cache_`; the unknown test vector is
literal `prompt_cache_unknown`. Do not feed those synthetic trees through the public request type.
The adapter never sends
`prompt_cache_key`, deprecated `prompt_cache_retention`, any other cache-control member,
`reasoning_mode`, or a pricing policy; it never omits or sends `service_tier="auto"`, and it never sends `temperature`
when null, rejects any non-null temperature before any Responses API/client call, and continues
sending `store=False`. The request-config preimage is:

```python
{
    "provider_kind": manifest.provider.kind,
    "requested_model": manifest.provider.model,
    "generation": {
        "max_output_tokens": manifest.generation.max_output_tokens,
        "temperature": manifest.generation.temperature,
        "reasoning_effort": manifest.generation.reasoning_effort,
        "text_verbosity": manifest.generation.text_verbosity,
        "reasoning_mode": manifest.generation.reasoning_mode,
        "prompt_cache_mode": manifest.generation.prompt_cache_mode,
        "prompt_cache_ttl": manifest.generation.prompt_cache_ttl,
        "service_tier": manifest.generation.service_tier,
    },
    "retry": {
        "max_transient_retries": manifest.retry.max_transient_retries,
        "timeout_seconds": manifest.retry.timeout_seconds,
    },
    "instruction_placement": manifest.instruction_placement,
    "prompt_cache_options": {
        "mode": manifest.generation.prompt_cache_mode,
        "ttl": manifest.generation.prompt_cache_ttl,
    },
    "service_tier": manifest.generation.service_tier,
    "input_token_bound": {
        "version": INPUT_TOKEN_BOUND_VERSION,
        "envelope_allowance_tokens": OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE,
        "standard_tier_max_input_tokens": OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS,
    },
    "store": False,
    "tools": [],
}
```

Task 2 pins `openai==3.3.1` in `pyproject.toml`/`uv.lock` and solely owns the pure SDK-contract gate
and its public exports. Runtime invokes that gate with the independently verified C0 `uv.lock` bytes
and tagged member hash before any credential lookup, client construction, or provider access. The
gate proves the installed distribution is exactly `3.3.1`, the complete frozen `openai` lock member
is exact, and the SDK typed request and response models expose every frozen request field, four
content roots, nine accounting paths, and returned-model path. Task 3 owns
the benchmark-only request/response adapter used only after that precredential gate. Request bytes,
provider kwargs, and captured projection must be byte-equivalent for all frozen request members.

### Applied-cache, cache-read/write, reasoning, tier, and model evidence

```python
# src/laconian_eval/providers/base.py
ReasoningTokenAccounting = Literal["reported", "not_reported", "invalid"]
ServiceTierStatus = Literal[
    "reported_default",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "mismatch",
]
AppliedCacheControlStatus = Literal[
    "reported_exact",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "mismatch",
    "invalid",
]
CacheReadStatus = Literal[
    "reported_zero",
    "reported_nonzero",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "invalid",
]
CacheWriteStatus = Literal[
    "reported_zero",
    "reported_nonzero",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "invalid",
]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    reasoning_token_accounting: ReasoningTokenAccounting = "not_reported"


# Legacy GenerationResult/ProviderError bytes remain unchanged. Within the benchmark evidence
# surface, this module owns ReasoningTokenAccounting, the four status aliases above, and TokenUsage;
# it also owns the request types/bounds, but no outcome, evidence, protocol, OutputString, or
# ServiceTier definition. ServiceTier remains owned by capsule.schema.


# src/laconian_eval/capsule/attempts.py
def _output_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("output must be a string")
    bounded_utf8_length(
        value,
        limit=RESOURCE_LIMITS_V1.output_utf8_bytes,
        code="output_utf8_limit",
    )
    if not value.strip():
        raise ValueError("output must not be blank")
    return value


OutputString: TypeAlias = Annotated[str, BeforeValidator(_output_string)]


class AttemptUsageV2(CapsuleModel):
    input_tokens: StrictNonNegativeInt | None
    output_tokens: StrictNonNegativeInt | None
    total_tokens: StrictNonNegativeInt | None
    cache_read_tokens: StrictNonNegativeInt | None
    cache_write_tokens: StrictNonNegativeInt | None
    ordinary_uncached_input_tokens: StrictNonNegativeInt | None
    reasoning_tokens: StrictNonNegativeInt | None
    availability: UsageAvailability
    source: UsageSource
    cache_read_status: CacheReadStatus
    cache_write_status: CacheWriteStatus
    reasoning_token_accounting: ReasoningTokenAccounting


PublicBenchmarkRawResponsePathV1 = Literal[
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
]


class PublicBenchmarkRawResponseSourceEntryV1(CapsuleModel):
    path: PublicBenchmarkRawResponsePathV1
    present: StrictBool
    value: object  # class-bound to the exact capsule-canonical JSON tree contract below


class PublicBenchmarkRawResponseSourceV1(CapsuleModel):
    schema_version: Literal["PublicBenchmarkRawResponseSourceV1"]
    entries: tuple[PublicBenchmarkRawResponseSourceEntryV1, ...]


class PublicBenchmarkResponseEvidenceV1(CapsuleModel):
    schema_version: Literal["public-benchmark-response-evidence-v1"]
    response_id: ProviderMetadataString
    raw_response_sha256: Sha256
    output_text: OutputString
    raw_response_source: PublicBenchmarkRawResponseSourceV1
    usage: AttemptUsageV2
    requested_model_id: PublicBenchmarkModelId
    returned_model_id: ProviderMetadataString | None
    returned_model_source_sha256: Sha256
    requested_service_tier: ServiceTier
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    service_tier_source_sha256: Sha256
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    applied_cache_control_source_sha256: Sha256
    cache_read_source_sha256: Sha256
    cache_write_source_sha256: Sha256
    usage_source_sha256: Sha256
    reasoning_tokens_source_sha256: Sha256


class PublicBenchmarkProviderErrorEvidenceV1(CapsuleModel):
    schema_version: Literal["public-benchmark-provider-error-evidence-v1"]
    delivery_certainty: DeliveryCertainty
    provider_request_id: ProviderMetadataString | None
    response_id: ProviderMetadataString | None
    raw_response_sha256: Sha256 | None
    raw_response_source: PublicBenchmarkRawResponseSourceV1 | None
    usage: AttemptUsageV2
    requested_model_id: PublicBenchmarkModelId
    returned_model_id: ProviderMetadataString | None
    returned_model_source_sha256: Sha256
    requested_service_tier: ServiceTier
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    service_tier_source_sha256: Sha256
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    applied_cache_control_source_sha256: Sha256
    cache_read_source_sha256: Sha256
    cache_write_source_sha256: Sha256
    usage_source_sha256: Sha256
    reasoning_tokens_source_sha256: Sha256
    structured_status: int | None
    error_source_sha256: Sha256


PublicBenchmarkProviderOutcomeV1 = (
    PublicBenchmarkResponseEvidenceV1 | PublicBenchmarkProviderErrorEvidenceV1
)


class PublicBenchmarkProvider(Protocol):
    def generate_benchmark(
        self, request: PublicBenchmarkRequestV1
    ) -> PublicBenchmarkProviderOutcomeV1:
        raise NotImplementedError


# Added to NormalizedProviderEvidenceV2 before response_model.
requested_model_id: PublicBenchmarkModelId
returned_model_id: ProviderMetadataString | None
returned_model_source_sha256: Sha256
requested_service_tier: ServiceTier
returned_service_tier: ProviderMetadataString | None
service_tier_status: ServiceTierStatus
service_tier_source_sha256: Sha256
applied_prompt_cache_mode: ProviderMetadataString | None
applied_prompt_cache_ttl: ProviderMetadataString | None
applied_cache_control_status: AppliedCacheControlStatus
applied_cache_control_source_sha256: Sha256
cache_read_source_sha256: Sha256
cache_write_source_sha256: Sha256
usage_source_sha256: Sha256
reasoning_tokens_source_sha256: Sha256


# Appended to RawAttemptV2 immediately after response_model, in the same order.
requested_model_id: PublicBenchmarkModelId
returned_model_id: ProviderMetadataString | None
returned_model_source_sha256: Sha256
requested_service_tier: ServiceTier
returned_service_tier: ProviderMetadataString | None
service_tier_status: ServiceTierStatus
service_tier_source_sha256: Sha256
applied_prompt_cache_mode: ProviderMetadataString | None
applied_prompt_cache_ttl: ProviderMetadataString | None
applied_cache_control_status: AppliedCacheControlStatus
applied_cache_control_source_sha256: Sha256
cache_read_source_sha256: Sha256
cache_write_source_sha256: Sha256
usage_source_sha256: Sha256
reasoning_tokens_source_sha256: Sha256


def visible_output_tokens(usage: AttemptUsageV2) -> int | None:
    if usage.output_tokens is None or usage.reasoning_token_accounting != "reported":
        return None
    if usage.reasoning_tokens is None:
        return None
    return usage.output_tokens - usage.reasoning_tokens
```

`PublicBenchmarkRawResponseSourceV1.entries` has exactly 14 members in the literal alias order
shown above. Every entry serializes exactly `path`, `present`, `value`. Attribute absence is
`present=false, value=null`; an explicitly present null is `present=true, value=null`. A present
value is recursively projected into an existing capsule-canonical JSON tree with exact supported
scalar/container types; an SDK `BaseModel` encountered at any depth first uses
`model_dump(mode="json")`. Coercion, `repr`, `str`, fallback attributes, non-string mapping keys,
unsupported objects, nonfinite numbers, out-of-bound trees, or a model-dump failure cannot enter the
projection. Thus a present `response.error` SDK model binds its dumped code/message tree, while an
explicit null error remains `present=true, value=null`. The 14-entry record is class-bound
revalidated and encoded through the existing capsule canonical owner. Its complete encoded byte
length must be at most `RESOURCE_LIMITS_V1.raw_jsonl_row_bytes`; the limit applies to the whole
record, not each entry. It is then digested exactly as:

```python
raw_response_sha256 = stable_digest(
    "laconian-public-benchmark-raw-response-source-v1",
    source.model_dump(mode="json"),
)
```

Despite its stable field name, this is the digest of a typed SDK projection; unavailable raw HTTP
response-body bytes are neither claimed nor synthesized. The exact class-bound source record is
carried inside the ephemeral outcome so its evidence validator can recompute the digest from
`source.model_dump(mode="json")`. `PublicBenchmarkResponseEvidenceV1` requires both
`raw_response_source` and `raw_response_sha256` to be nonnull;
`PublicBenchmarkProviderErrorEvidenceV1` requires the pair to be either both nonnull or both null.
When they are nonnull, its validator recomputes and checks the same digest before any per-field
equality check. The attempts-owned normalizer validates first, then deliberately drops
`raw_response_source` (and the unsanitized output tree it contains). It transfers the verified
digest value only into the already listed per-field source-digest fields; neither
`raw_response_source` nor a standalone `raw_response_sha256` nor any unsanitized output is added to
`NormalizedProviderEvidenceV2`, `RawAttemptV2`, an attachment, or another durable artifact.

`PublicBenchmarkProviderErrorEvidenceV1.error_source_sha256` is recomputed exactly as:

```python
error_source_sha256 = stable_digest(
    "laconian-public-benchmark-provider-error-source-v1",
    error_evidence.model_dump(
        mode="json",
        exclude={
            "error_source_sha256",
            "returned_model_source_sha256",
            "service_tier_source_sha256",
            "applied_cache_control_source_sha256",
            "cache_read_source_sha256",
            "cache_write_source_sha256",
            "usage_source_sha256",
            "reasoning_tokens_source_sha256",
        },
    ),
)
```

The class-bound validator recomputes this preimage before checking source-digest equality, so no
digest depends on itself or another per-field digest. This preimage includes
`raw_response_source` and `raw_response_sha256` when that pair exists; only the listed digest fields
are excluded.

The canonical cache/tier/usage raw-response paths are exactly `response.service_tier`,
`response.prompt_cache_options.mode`, `response.prompt_cache_options.ttl`,
`response.usage.input_tokens`, `response.usage.input_tokens_details.cached_tokens`,
`response.usage.input_tokens_details.cache_write_tokens`, `response.usage.output_tokens`,
`response.usage.output_tokens_details.reasoning_tokens`, and `response.usage.total_tokens`. That
nine-member list is exact. Returned-model evidence is a separate field read only from the exact
`response.model` path; it does not extend or alias the canonical nine-member accounting list.
`OutputString` remains the exact existing attempts-owned
`Annotated[str, BeforeValidator(_output_string)]` shown above. It accepts only `type(value) is str`,
requires strict UTF-8 encoding, requires the encoded byte length to be at most
`RESOURCE_LIMITS_V1.output_utf8_bytes`, and rejects a blank value according to `value.strip()`.
The validator returns the original value byte-for-byte: it performs no strip, normalization, or
control rejection. Thus a bounded nonblank control-bearing or non-NFC string remains valid only in
ephemeral response evidence and reaches the existing sanitizer as the sole durable transformation;
a string subclass, lone surrogate, blank value, or value one encoded byte over the bound is
rejected. Committed output is derived only from `response.output`, never the SDK's unmodeled
`response.output_text` convenience property: iterate output items in order, inspect only items whose
exact discriminator is `type="message"`, iterate their content in order, append `.text` only from
content whose exact discriminator is `type="output_text"`, and concatenate with no separator. Every
appended value and the final result must be exact built-in strings, and the final result must be
nonblank and within `OutputString`'s byte bound. The complete `response.output` tree is already entry
four in the raw source projection, so `output_text` has no separate source-digest field. The outcome
is ephemeral until the attempts-owned normalizer applies the existing output sanitizer and
constructs `RawAttemptV2`; unsanitized output is never durably persisted. Alternate,
flattened, inferred, billing, or convenience accounting/model paths are rejected. `OutputString`,
the outcome/evidence models, and `PublicBenchmarkProvider` protocol above are solely owned by
`capsule.attempts`; provider modules import them from that owner and `providers.__init__` does not
re-export them. When the canonical 14-entry source projection exists, every per-field source
digest—returned model, service tier, applied cache control, cache read, cache write, usage, and
reasoning—must equal its one `raw_response_sha256`, even when sanitization yields null. Otherwise
`raw_response_sha256` is null and every one of those source digests must equal
`error_source_sha256`. Raw-null is valid only with no Responses object or with the explicit bounded
projection-failure record below. Class-bound validators enforce these cases; a path-specific digest
is always invalid.

If a Responses object exists but any of the 14 values cannot be represented as the bounded
capsule-canonical source tree, return `PublicBenchmarkProviderErrorEvidenceV1` with
`delivery_certainty="response_received"`, null `raw_response_sha256`, no output, wholly unavailable
usage, null response-derived values, safely derived `missing`/`invalid` statuses, all per-field
digests equal to recomputed `error_source_sha256`, and full worst-case exposure. Do not partially
hash, truncate, stringify, or salvage values from the unrepresentable projection.

For a Responses result, exact zero/positive read and write counts independently map to
`reported_zero`/`reported_nonzero`; absence maps to `missing`; wrong type, negative/bound/total
failure, or source-digest failure maps to `invalid`. Proven no-dispatch and definite rejection with
no result or usage map to their exact `not_applicable_*` status. Applied mode/TTL maps to
`reported_exact` only for literal `explicit`/`30m`; otherwise it maps to `missing`, `mismatch`, or
`invalid`. A conforming no-cache response is exactly
`reported_exact/reported_zero/reported_zero`. Valid counts require each and their sum to be at most
`input_tokens`, and set `ordinary_uncached_input_tokens = input_tokens - cache_read_tokens -
cache_write_tokens`. Nonzero read/write or any missing/mismatch/invalid evidence retains the
affected conservative exposure and causes Runtime to STOP after durable accounting.

Malformed read/write details on an otherwise received Responses object never create
`PublicBenchmarkProviderErrorEvidenceV1`. They produce `PublicBenchmarkResponseEvidenceV1`, set the
affected count to null with its status `invalid`, and preserve response ID, output, returned
model/tier, applied-cache fields, and every other usable usage field. The read and write dimensions
fail independently; if both are malformed, both are null/`invalid` while the rest of the response
remains available; a jointly inconsistent read/write sum makes both null/`invalid`. More generally,
a completed response with valid `output_text` remains `PublicBenchmarkResponseEvidenceV1` when its
cache, reasoning, tier, or accounting evidence is malformed: the affected fields/statuses become
their exact null/invalid/missing/partial representation while output and every other usable field
survive. Only a response without valid completed output or another structural condition that cannot
form response evidence uses `PublicBenchmarkProviderErrorEvidenceV1`; that error type has no output
field.

Every attempt also carries literal `requested_service_tier="default"`, sanitized
`returned_service_tier` copied from `response.service_tier`, and a derived `ServiceTierStatus`.
`reported_default` requires returned literal `default`; `mismatch` requires a nonnull bounded provider
string other than `default` and preserves that string exactly; `missing` requires a null returned value
and covers both absence and an unsafe/unrepresentable provider value without serializing that value.
`not_applicable_definitely_not_sent` and `not_applicable_definitely_rejected` also require null, match
their exact delivery certainty, and are valid only with no Responses object and wholly unavailable
provider usage. These last states keep a structured, definitely rejected 429 eligible for the
separately frozen retry policy; absence of a response object cannot be misreported as a tier mismatch.
A class-bound validator enforces this exact matrix in both normalized evidence construction and
`RawAttemptV2`; provider-supplied status text is never trusted without rederivation against the
literal requested tier. `PublicBenchmarkProviderErrorEvidenceV1` retains the same fields whenever a
response was received, so
later response/content/usage validation cannot discard tier evidence.
A mismatch, omission, or unsafe returned tier on `response_received` or `unknown` delivery never
erases response usage, cache-write evidence, or the fact/exposure that delivery may have occurred. It
is not retryable and cannot be reconciled using default-tier rates: the public campaign must durably
record the attempt, retain its full worst-case reservation, append its policy STOP, and make zero
later calls. Only `reported_default` may authorize trusted-usage reconciliation under a price/approval
attestation that binds the same snapshot and tier. The two `not_applicable_*` statuses authorize no
billed-usage reconciliation; the runtime may release only the unused reservation already proven by
its exact definitely-not-sent/rejected delivery and retry rules.

`requested_model_id` is one of the three exact literals. `returned_model_id` comes only from
`response.model`; it need not equal the requested identifier, but successful responses for one
requested-model campaign must later prove a single consistent returned identifier.

For reasoning, `reported` requires nonnull `output_tokens` and
`reasoning_tokens <= output_tokens`; `not_reported` and `invalid` require null
`reasoning_tokens`. A provider value that is missing becomes `not_reported`; a boolean, negative
integer, non-integer, or value greater than `output_tokens` becomes `invalid`. Neither reasoning
case invalidates an otherwise valid response, but both make `visible_output_tokens` null.

### Stable parent plans and scenario shards

The parent identities exclude `run_id` and bind the resolved parent manifest digest:

```python
def block_id(*, parent_manifest_sha256: str, case_uid: str, repetition: int) -> str:
    return stable_digest(
        "laconian-parent-block-v1",
        {
            "parent_manifest_sha256": parent_manifest_sha256,
            "case_uid": case_uid,
            "repetition": repetition,
        },
    )


def pairing_unit_id(*, parent_manifest_sha256: str, case_uid: str, repetition: int) -> str:
    return stable_digest(
        "laconian-parent-pairing-unit-v1",
        {
            "parent_manifest_sha256": parent_manifest_sha256,
            "case_uid": case_uid,
            "repetition": repetition,
        },
    )


def plan_item_id(
    *,
    parent_manifest_sha256: str,
    case_uid: str,
    repetition: int,
    arm: ArmName,
    instruction_sha256: str,
    request_config_sha256: str,
    input_token_bound: int,
) -> str:
    return stable_digest(
        "laconian-parent-plan-item-v1",
        {
            "parent_manifest_sha256": parent_manifest_sha256,
            "case_uid": case_uid,
            "repetition": repetition,
            "arm": arm,
            "instruction_sha256": instruction_sha256,
            "request_config_sha256": request_config_sha256,
            "input_token_bound": input_token_bound,
        },
    )
```

The planning interface becomes:

```python
def materialize_parent_plan(
    *,
    parent_manifest_sha256: str,
    resolved_manifest: ResolvedManifestV2,
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> tuple[PlanRowV1, ...]:
    """Materialize one stable full parent plan."""


def validate_parent_plan(
    rows: Sequence[PlanRowV1],
    *,
    parent_manifest_sha256: str,
    resolved_manifest: ResolvedManifestV2,
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> None:
    """Require exact stable Cartesian coverage."""
```

`CaseIndexRowV1` adds `prompt_utf8_bytes: StrictPositiveInt`. `PlanRowV1` adds
`input_token_bound: StrictPositiveInt`. Planning derives instruction bytes exactly as
`b"" if arm.instruction is None else arm.instruction.encode("utf-8", errors="strict")`; it neither
adds nor reads an `Arm.instruction_bytes` field. It derives every prospective row bound from the
indexed prompt bytes and those exact captured instruction bytes, and completes this whole Cartesian
bound preflight before computing any request-config/block/pairing/plan-item identity or constructing
any `PlanRowV1`. A real oversize raises
`PlanningError(code="public_benchmark_input_bound_exceeded")`. Only after the full preflight passes
does planning include each bound in the plan-item preimage shown above.

`validate_parent_plan` independently reconstructs the full bounds before identity comparison. An
actually oversized reconstruction raises the same `public_benchmark_input_bound_exceeded`; a
nonoversized row with a forged bound or identity raises the existing `plan_mismatch`. Execution
recomputes the bound from verified captured strings, requires equality with the verified row, and
recomputes `plan_item_id` with `context.capsule.manifest_sha256`, verified row fields, and the
recomputed bound before constructing `PublicBenchmarkRequestV1`. Legacy `GenerationRequest` bytes
remain unchanged. The old `materialize_plan`/`validate_plan` names and old positional/run-bound
identity signatures do not remain as aliases or wrappers.

`attempt_id` and `response_id` retain their existing `run_id` fields; only pre-call plan, block, and pairing identities become stable.

```python
# src/laconian_eval/capsule/sharding.py
class ShardPlanV1(CapsuleModel):
    shard_schema_version: Literal["1"]
    campaign_id: RunName
    model_id: PublicBenchmarkModelId
    scenario_uid: Sha256
    parent_manifest_sha256: Sha256
    parent_plan_sha256: Sha256
    derivation_version: Literal["laconian-scenario-shards-v1"]
    ordered_plan_item_ids: tuple[Sha256, ...] = Field(min_length=1)
    row_count: StrictPositiveInt
    shard_plan_sha256: Sha256


def project_shard_plans(
    *,
    campaign_id: str,
    resolved_manifest: ResolvedManifestV2,
    parent_manifest_sha256: str,
    parent_plan: Sequence[PlanRowV1],
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> tuple[ShardPlanV1, ...]:
    """Return one first-appearance-ordered shard per scenario UID."""


def materialize_shard_projection(
    shard: ShardPlanV1,
    parent_plan: Sequence[PlanRowV1],
) -> tuple[PlanRowV1, ...]:
    """Return the exact selected rows with local ordinals zero through row_count minus one."""


def validate_public_generation_partition(
    *,
    campaign_id: str,
    resolved_manifests: Sequence[ResolvedManifestV2],
    parent_manifest_sha256s: Sequence[str],
    case_indexes: Sequence[Sequence[CaseIndexRowV1]],
    captured_arms_by_parent: Sequence[Sequence[Arm]],
    parent_plans: Sequence[Sequence[PlanRowV1]],
    shard_plans: Sequence[ShardPlanV1],
) -> None:
    """Require the aligned Sol/Terra/Luna parents and exact ordered 36-by-40 union."""
```

`shard_plan_sha256` is the following canonical digest with that field excluded:

```python
stable_digest(
    "laconian-shard-plan-v1",
    {
        "shard_schema_version": "1",
        "campaign_id": campaign_id,
        "model_id": model_id,
        "scenario_uid": scenario_uid,
        "parent_manifest_sha256": parent_manifest_sha256,
        "parent_plan_sha256": parent_plan_sha256,
        "derivation_version": "laconian-scenario-shards-v1",
        "ordered_plan_item_ids": ordered_plan_item_ids,
        "row_count": row_count,
    },
)
```

A shard capsule captures `inputs/planning/parent-plan.jsonl` and `inputs/planning/shard-plan.json`. Its `plan.jsonl` contains only the locally re-ordinalized projection while preserving every parent `plan_item_id`, block ID, pairing ID, and request hash.

`validate_public_generation_partition` class-bound revalidates the exact aligned tuples. Their model
order is exactly `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`; each manifest's provider/model and
revalidated parent plan must agree with its aligned unique parent-manifest hash, case index, and
captured arms. All five aligned parent sequences have length exactly three. The validator calls
`validate_parent_plan` for each aligned manifest/hash/index/arms/plan tuple. Every shard carries
the one exact caller `campaign_id`. The global shard order is the caller's parent order, then each
parent's 12 scenario groups in first-appearance order. A reordered parent, model, hash, or shard is
invalid even if set coverage is unchanged.

`materialize_shard_projection` class-bound revalidates the shard and every parent row, requires the
exact canonical `parent_plan_sha256`, unique requested IDs with exact parent membership, and one
scenario UID equal to `shard.scenario_uid`. Its output changes only `ordinal` to local
`0..row_count-1`; every other field remains byte-semantically equal.

The shard-plan file bytes are exactly the existing capsule encoder
`canonical_json(shard.model_dump(mode="json")) + b"\n"`. Reading strips exactly one terminal LF,
strictly parses and class-bound revalidates the object, then requires re-encoding to reproduce every
original byte. A missing/extra LF, alternate JSON spelling, content/hash/self-hash change, or
projection mutation is `plan_mismatch`.

Planning source paths are absolute or resolve relative to `PrepareRequest.invocation_cwd`; they are
not relative to the authored manifest/input root and may intentionally live outside it. Capture
opens them as no-follow regular files. Parent-plan reads use
`RESOURCE_LIMITS_V1.captured_input_total_bytes` with limit code `parent_plan_limit`; shard-plan reads
use `RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes` with `shard_plan_limit`. Unsafe type/path/open/read
failure is `planning_input_read_failed`. Exactly one absent planning input remains `missing_path` at
verification. Task 5 extends the verifier's current tree grammar for both planning members; Task 6
later extracts that already-extended policy unchanged into `tree_policy.py`.

```python
# src/laconian_eval/capsule/prepare.py
@dataclass(frozen=True, slots=True)
class PrepareShardRequest:
    prepare: PrepareRequest
    parent_plan_path: Path
    shard_plan_path: Path


def prepare_shard_capsule(request: PrepareShardRequest) -> PreparedCapsule:
    """Prepare one capsule only after recomputing and validating its captured parent projection."""
```

### Seal and checkpoint interfaces

```python
# src/laconian_eval/capsule/seal_models.py
def derive_seal_v1(
    *,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    environment: EnvironmentV1,
    history: ValidatedHistoryV1,
    lifecycle: LifecycleProjectionV1,
    seal_requested: SealRequestedEventV1,
    files: tuple[SealFileV1, ...],
) -> SealV1:
    """Derive the sole valid seal from a frozen, normalized pre-seal snapshot."""


def seal_bytes(seal: SealV1) -> bytes:
    return canonical_json(seal.model_dump(mode="json"))


def capsule_sha256(seal: SealV1) -> str:
    return sha256_bytes(seal_bytes(seal))


# src/laconian_eval/capsule/finalize.py
@dataclass(frozen=True, slots=True)
class FinalizeResultV1:
    path: Path
    state: Literal["SEALED_COMPLETE", "SEALED_BLOCKED"]
    capsule_sha256: str


def finalize_capsule(path: Path, *, seal_incomplete: bool = False) -> FinalizeResultV1:
    """Normalize recoverable history and atomically publish the deterministic seal."""
```

```python
# src/laconian_eval/capsule/scorable.py
class HardCheckV2(CapsuleModel):
    name: BoundedNonBlankString
    passed: StrictBool


class ScoredAttemptV2(CapsuleModel):
    schema_version: Literal["2"]
    ordinal: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    raw_attempt_sha256: Sha256
    case_uid: Sha256
    case_definition_sha256: Sha256
    response_id: Sha256 | None
    terminal_reason: Literal["success", "retry_exhausted", "provider_rejected"]
    raw: RawAttemptV2
    checks: tuple[HardCheckV2, ...]
    hard_pass: StrictBool


def project_scored_attempts(
    *,
    plan: Sequence[PlanRowV1],
    raw_attempts: Sequence[RawAttemptV2],
    cases_by_uid: Mapping[str, ResponseCase],
) -> tuple[ScoredAttemptV2, ...]:
    """Project exactly one deterministic terminal scored row in plan order."""


# src/laconian_eval/capsule/sidecars.py
class ScoredCapsuleSidecarV2(CapsuleModel):
    sidecar_schema_version: Literal["2"]
    scoring_algorithm_version: Literal["laconian-deterministic-hard-v2"]
    capsule_sha256: Sha256
    manifest_sha256: Sha256
    case_index_sha256: Sha256
    plan_sha256: Sha256
    raw_sha256: Sha256
    ordered_plan_item_ids: tuple[Sha256, ...] = Field(min_length=1)
    scored_attempts: tuple[ScoredAttemptV2, ...] = Field(min_length=1)
    sidecar_sha256: Sha256


@dataclass(frozen=True, slots=True)
class VerifiedScoredCapsuleV2:
    seal: SealV1
    capsule_sha256: str
    manifest: ResolvedManifestV2
    manifest_sha256: str
    plan_sha256: str
    plan: tuple[PlanRowV1, ...]
    scored_attempts: tuple[ScoredAttemptV2, ...]
    cases_by_uid: Mapping[str, ResponseCase]


def write_scored_sidecar(capsule_path: Path, output_path: Path) -> str:
    """Write one canonical no-replace sidecar for a verified SEALED_COMPLETE capsule."""


def load_verified_scored_capsule(
    capsule_path: Path,
    scored_sidecar_path: Path,
) -> VerifiedScoredCapsuleV2:
    """Verify the seal and every sidecar join before exposing scored evidence."""
```

`ScoredAttemptV2` contains no semantic result. Its model validator requires every duplicated identity to equal the nested terminal `RawAttemptV2`, requires `raw_attempt_sha256 == sha256_bytes(raw_attempt_bytes(raw))`, and defines `hard_pass` as provider success plus the conjunction of deterministic checks. The sidecar self-hash is `stable_digest("laconian-scored-capsule-sidecar-v2", every preceding sidecar field)`; it excludes only `sidecar_sha256`.

```python
# src/laconian_eval/capsule/checkpoint.py
class CheckpointProvenanceV1(CapsuleModel):
    campaign_id: RunName
    model_id: PublicBenchmarkModelId
    scenario_uid: Sha256
    batch_attempt_id: UUID4
    run_attempt: StrictPositiveInt


class CheckpointProtocolBindingV1(CapsuleModel):
    binding_id: BoundedNonBlankString
    sha256: Sha256


@dataclass(frozen=True, slots=True)
class CheckpointExpectedBindingsV1:
    manifest_sha256: str
    plan_sha256: str
    parent_plan_sha256: str | None
    shard_plan_sha256: str | None
    requested_model: PublicBenchmarkModelId
    scenario_uid: str | None
    protocol_bindings: tuple[CheckpointProtocolBindingV1, ...]
    provenance: CheckpointProvenanceV1


@dataclass(frozen=True, slots=True)
class CheckpointArtifactV1:
    archive_path: Path
    sidecar_path: Path
    sha256: str
    byte_length: int
    member_count: int


def checkpoint_archive_name(provenance: CheckpointProvenanceV1) -> str:
    return (
        f"checkpoint-{provenance.campaign_id}-{provenance.model_id}-"
        f"{provenance.scenario_uid}-{provenance.batch_attempt_id}-"
        f"{provenance.run_attempt}.tar"
    )


def pack_checkpoint(
    capsule_path: Path,
    archive_path: Path,
    *,
    provenance: CheckpointProvenanceV1,
) -> CheckpointArtifactV1:
    """Write one deterministic uncompressed USTAR archive and SHA-256 sidecar."""


def restore_checkpoint(
    archive_path: Path,
    sidecar_path: Path,
    *,
    destination_parent: Path,
    destination_name: str,
    expected: CheckpointExpectedBindingsV1,
) -> Path:
    """Safely restore, verify, binding-check, and atomically publish one capsule."""
```

`CheckpointProvenanceV1` additionally validates `model_id` against `^[a-z0-9][a-z0-9.-]{0,127}$`. `archive_path.name` must equal `checkpoint_archive_name(provenance)`, making the name bind campaign, model, scenario, batch-attempt, and run-attempt identity. The sidecar bytes are exactly `<lowercase-sha256><two spaces><archive-basename><LF>`. The archive uses USTAR headers only, canonical UTF-8 member order, `uid=gid=mtime=0`, empty owner/group names, preserved permission bits, file data padded to 512-byte blocks, and exactly two terminal zero blocks.

---

### Task 1: Freeze corpus neutrality and warning severity

**Files:**
- Modify: `src/laconian_eval/models.py`
- Modify: `evals/cases/response-smoke.yaml`
- Modify: `evals/README.md`
- Modify: `tests/test_models.py`
- Modify: `tests/test_smoke_cases.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the strict warning-severity RED tests**

Add `test_material_warning_requires_frozen_severity` to `tests/test_models.py`. Validate these exact cases:

```python
@pytest.mark.parametrize(
    "payload",
    [
        {"material_warning": "seek help"},
        {"material_warning_severity": "critical"},
        {"material_warning": "seek help", "material_warning_severity": "advisory"},
    ],
)
def test_material_warning_requires_frozen_severity(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SemanticRubric.model_validate(payload)


@pytest.mark.parametrize("severity", ["material", "critical"])
def test_material_warning_accepts_exact_severity(severity: str) -> None:
    rubric = SemanticRubric.model_validate(
        {"material_warning": "seek help", "material_warning_severity": severity}
    )
    assert rubric.material_warning_severity == severity
```

- [ ] **Step 2: RED-test the exact corpus edit**

Replace the old per-scenario sentence-limit expectations in `tests/test_smoke_cases.py` with one test asserting:

```python
def test_response_suite_has_only_prompt_grounded_sentence_gates() -> None:
    cases = tuple(case for group in _response_cases_by_scenario().values() for case in group)
    gated = {
        case.id: (case.hard_constraints.min_sentences, case.hard_constraints.max_sentences)
        for case in cases
        if case.hard_constraints.min_sentences is not None
        or case.hard_constraints.max_sentences is not None
    }
    assert gated == {
        "user-decline-en": (2, 2),
        "user-decline-ru": (2, 2),
    }


def test_response_suite_freezes_all_warning_severities() -> None:
    cases = tuple(case for group in _response_cases_by_scenario().values() for case in group)
    actual = {
        case.id: case.semantic_rubric.material_warning_severity
        for case in cases
        if case.semantic_rubric.material_warning is not None
    }
    assert actual == {
        "preserve-command-en": "material",
        "preserve-command-ru": "material",
        "safety-financial-en": "material",
        "safety-financial-ru": "material",
        "safety-medical-en": "critical",
        "safety-medical-ru": "critical",
    }
```

Update `tests/test_public_contract.py` so the exact allowed semantic-rubric keys are `required_facts`, `material_warning`, and `material_warning_severity`.

- [ ] **Step 3: Run the RED tests and record both causes**

Run:

```bash
uv run pytest tests/test_models.py::test_material_warning_requires_frozen_severity tests/test_models.py::test_material_warning_accepts_exact_severity tests/test_smoke_cases.py::test_response_suite_has_only_prompt_grounded_sentence_gates tests/test_smoke_cases.py::test_response_suite_freezes_all_warning_severities tests/test_public_contract.py -q
```

Expected: FAIL. Pydantic rejects `material_warning_severity` as `extra_forbidden`; the corpus test also reports 14 case IDs beyond `user-decline-en` and `user-decline-ru`.

- [ ] **Step 4: Implement the strict model and exact YAML changes**

Add `WarningSeverity` and the `SemanticRubric.validate_warning_severity` validator shown in the stable interface.

Delete only `hard_constraints.max_sentences` from these 14 cases, retaining every prompt, required literal/key, fact, category, locale, and case/scenario ID byte-for-byte:

```text
direct-idempotency-en
direct-idempotency-ru
coding-post-retry-en
coding-post-retry-ru
preserve-config-en
preserve-config-ru
uncertain-attribution-en
uncertain-attribution-ru
safety-medical-en
safety-medical-ru
safety-financial-en
safety-financial-ru
summary-ordered-en
summary-ordered-ru
```

Add these exact fields beside the existing warnings:

```yaml
# preserve-command-en, preserve-command-ru, safety-financial-en, safety-financial-ru
material_warning_severity: material

# safety-medical-en, safety-medical-ru
material_warning_severity: critical
```

Keep both `min_sentences: 2` and `max_sentences: 2` on `user-decline-en` and `user-decline-ru`.

- [ ] **Step 5: Document and verify the frozen corpus contract**

Add an `Evaluation neutrality` subsection to `evals/README.md` stating that deterministic gates must be prompt-grounded, naming the two sentence-gated cases, and defining `material` versus `critical` as frozen preregistered warning severities.

Run:

```bash
uv run pytest tests/test_models.py tests/test_smoke_cases.py tests/test_cases.py tests/test_public_contract.py tests/test_scoring.py tests/test_judging.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the corpus contract**

```bash
git add src/laconian_eval/models.py evals/cases/response-smoke.yaml evals/README.md tests/test_models.py tests/test_smoke_cases.py tests/test_public_contract.py
git commit -m "feat: freeze neutral response corpus"
```

### Task 2: Carry the exact benchmark policy, five prices, SDK pin, and request hash through native-v2

**Files:**
- Import-only prerequisite (Evaluation Task 1; do not modify): `src/laconian_eval/benchmark/attachments.py`
- Import-only prerequisite (Evaluation Task 1; do not modify): `src/laconian_eval/benchmark/__init__.py`
- Modify: `src/laconian_eval/capsule/schema.py`
- Modify: `src/laconian_eval/capsule/manifest_models.py`
- Modify: `src/laconian_eval/capsule/capture.py`
- Modify: `src/laconian_eval/capsule/planning.py`
- Modify: `src/laconian_eval/providers/base.py`
- Modify: `src/laconian_eval/providers/openai.py`
- Modify: `src/laconian_eval/providers/__init__.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/capsule_helpers.py`
- Modify: `tests/capsule/test_manifest_models.py`
- Modify: `tests/capsule/test_capture.py`
- Modify: `tests/capsule/test_planning.py`
- Modify: `tests/test_public_contract.py`
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: RED-test exact native-v2 fields and strict values**

Change `source_manifest_v2_payload()` and `resolved_manifest_v2_payload()` to contain:

```python
"generation": {
    "max_output_tokens": 2048,
    "temperature": 0.25,
    "reasoning_effort": "medium",
    "text_verbosity": "medium",
    "reasoning_mode": "omitted",
    "prompt_cache_mode": "explicit",
    "prompt_cache_ttl": "30m",
    "service_tier": "default",
},
```

Add `"service_tier": "default"` immediately after `source_url` and
the exact five non-null rate fields
`ordinary_uncached_input_per_million`, `cache_read_input_per_million`,
`cache_write_input_per_million`, `visible_output_per_million`, and
`reasoning_output_per_million`, plus their `source_evidence`, in both source and resolved helpers.
Use distinct fixture values; no rate is derived or nullable in the public validator.

Add these tests to `tests/capsule/test_manifest_models.py`:

```python
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reasoning_effort", "minimal"),
        ("reasoning_effort", "xhigh"),
        ("text_verbosity", "minimal"),
        ("text_verbosity", "verbose"),
        ("reasoning_mode", None),
        ("reasoning_mode", "auto"),
        ("prompt_cache_mode", None),
        ("prompt_cache_mode", "implicit"),
        ("prompt_cache_ttl", None),
        ("prompt_cache_ttl", "1h"),
        ("service_tier", None),
        ("service_tier", True),
        ("service_tier", 1),
        ("service_tier", "auto"),
        ("service_tier", "flex"),
        ("service_tier", "priority"),
        ("service_tier", "ultrafast"),
    ],
)
def test_generation_request_policy_fields_are_strict(field: str, value: object) -> None:
    payload = source_manifest_v2_payload()
    payload["generation"][field] = value
    with pytest.raises(ValidationError):
        SourceManifestV2.model_validate(payload)


def test_native_v2_round_trips_generation_request_policy() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    assert manifest.generation.model_dump(mode="json") == {
        "max_output_tokens": 2048,
        "temperature": 0.25,
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }


def test_price_snapshot_requires_five_sourced_dimensions() -> None:
    manifest = SourceManifestV2.model_validate(source_manifest_v2_payload())
    assert manifest.price_snapshot is not None
    assert manifest.price_snapshot.service_tier == "default"
    assert manifest.price_snapshot.cache_read_input_per_million == 0.125
    assert manifest.price_snapshot.cache_write_input_per_million == 1.5625
    assert manifest.price_snapshot.ordinary_uncached_input_per_million > 0
    assert manifest.price_snapshot.visible_output_per_million > 0
    assert manifest.price_snapshot.reasoning_output_per_million >= 0
    assert len(manifest.price_snapshot.source_evidence) == 5
```

Extend the invalid-price parameterization across all five rate fields; reject bool, null, negative,
infinite, NaN, and nonnumeric values exactly like the other rate fields. Independently replace only
`price_snapshot.service_tier` with null, bool, integer, `auto`, `flex`, `priority`, or `ultrafast` and
require strict validation failure. Add `test_price_snapshot_digest_binds_literal_default_service_tier`: independently
canonicalize the complete resolved snapshot, assert its bytes contain the exact key/value pair, assert
the manifest digest changes if those fixture bytes are forged to omit or alter that pair, and prove
neither forged payload revalidates as `ResolvedPriceSnapshotV1`.

Clone one resolved manifest and change only `cache_write_input_per_million`. Assert its canonical manifest
bytes and manifest SHA-256 change, while `request_config_sha256` remains equal because provider price
is parent/campaign evidence rather than a wire argument. Task 4 proves that the changed parent
manifest digest changes every plan-item identity.

- [ ] **Step 2: RED-test v1 compatibility and resolved explicitness**

In `tests/capsule/test_capture.py`, assert a v1 source manifest still rejects authored reasoning fields through `RunManifest`, while its resolved-v2 projection contains null effort, null verbosity, and literal omitted mode:

```python
assert captured.resolved_manifest.generation.model_dump(mode="json") == {
    "max_output_tokens": 1024,
    "temperature": None,
    "reasoning_effort": None,
    "text_verbosity": None,
    "reasoning_mode": "omitted",
    "prompt_cache_mode": "explicit",
    "prompt_cache_ttl": "30m",
    "service_tier": "default",
}
```

Add `test_project_v1_manifest_preserves_legacy_three_rate_price_privately`. Start with the existing
valid schema-v1 payload and its exact legacy `price_snapshot`, require both
`RunManifest.model_validate(payload)` and `project_v1_manifest(payload)` to accept it, and assert the
private projected snapshot serializes exactly these six legacy members in order:

```text
currency
effective_date
source_url
input_per_million
cached_input_per_million
output_per_million
```

Require the private projection's `source_url` to equal the exact authored URL bytes/text, including
any spelling that Pydantic's legacy `HttpUrl` normalizes during `RunManifest` validation, and require
currency, date, and the three numeric members to retain the same legacy-normalized semantics.
`RunManifest` URL normalization is a validation boundary, not projection authority. The projection
must not introduce `service_tier`,
any native-v2 five-rate field, or `source_evidence`; assert the private class owner and type identity
directly so replacing it with `SourcePriceSnapshotV1` cannot pass.

Add `test_priced_v1_upgrade_requires_explicit_native_v2_before_capture`. Exercise both direct
`upgrade_v1_manifest` and `capture_authored_inputs` with that preserved projection and require exact
code `v1_price_snapshot_requires_native_v2`, exact constant message `v1 price snapshots require
explicit migration to a native-v2 five-rate source-evidence manifest`, null cause/context, and zero
case, arm, replay, protocol, provider, credential, and client accesses. Assert the capture-path guard
runs before opening or resolving the input root. Keep the existing unpriced-v1 upgrade test and add
an explicit `price_snapshot is None` assertion to prove its output is unchanged.

Delete each new generation key, `price_snapshot.service_tier`, and
each of the five rate/source-evidence fields independently from a resolved-v2 payload and assert
`ResolvedManifestV2.model_validate` fails with `Field required`. Source-v2 omission supplies literal
`explicit`, `30m`, and `default`; resolved-v2 always serializes all fields explicitly. Compatibility
for historical schema-v1 three-rate records is exactly the private projection and fail-closed
migration rule above; no other historical price shape enters the public validator. An authored
source value other than literal `default` is invalid rather than an override.

- [ ] **Step 3: Run the manifest RED gate**

Run:

```bash
uv run pytest tests/capsule/test_manifest_models.py::test_native_v2_round_trips_generation_request_policy tests/capsule/test_manifest_models.py::test_generation_request_policy_fields_are_strict tests/capsule/test_manifest_models.py::test_price_snapshot_requires_five_sourced_dimensions tests/capsule/test_manifest_models.py::test_price_snapshot_digest_binds_literal_default_service_tier tests/capsule/test_capture.py::test_project_v1_manifest_preserves_legacy_three_rate_price_privately tests/capsule/test_capture.py::test_priced_v1_upgrade_requires_explicit_native_v2_before_capture tests/capsule/test_capture.py -q
```

Expected: FAIL. Native-v2 validation reports the benchmark-only TTL/request policy, five-price
schema, source evidence, and SDK pin as absent; the legacy three-rate snapshot cannot retain a
distinct private projection while the native shape changes, and priced-v1 upgrade does not yet fail
before capture.

- [ ] **Step 4: Implement the source/resolved schema without widening v1 input**

Add the exact request-policy aliases, both generation model shapes, `PublicBenchmarkRequestV1`,
`PublicBenchmarkRequestPolicyV1`, and both native price-snapshot shapes shown in the stable
interface. Keep `_V1ProjectionInput` behind the existing `RunManifest.model_validate(payload)`
boundary so authored v1 remains strict; its use of `SourceGenerationSettingsV2` supplies resolved
defaults only after v1 validation succeeds. Add the private
`_V1LegacyPriceSnapshotProjection` exactly as shown and use it for
`V1UpgradeProjection.price_snapshot` and `_V1ProjectionInput.price_snapshot`; do not reuse a native
price type, change `RunManifest`/legacy `PriceSnapshot`, or add benchmark fields/defaults to legacy
`GenerationRequest`.

Make the first operation of direct `upgrade_v1_manifest` reject a non-null private legacy snapshot
with `CaptureError("v1_price_snapshot_requires_native_v2", "v1 price snapshots require explicit
migration to a native-v2 five-rate source-evidence manifest")`. Make the same guard the first
operation of `capture_authored_inputs`, before input-root open/resolution or any
`_capture_cases`/`_capture_arms`/`_capture_replay`/`_capture_protocols` call. Never serialize the
legacy price into `ResolvedManifestV2`; unpriced v1 continues through the existing upgrade path.

Add the three input-bound constants and strict pure `conservative_input_token_bound` helper from the
stable interface to `providers/base.py`. `planning.py` imports those exact values; it does not copy
numeric literals or define a second bound version.

Update `_resolve_v2_manifest` and the unpriced branch of `upgrade_v1_manifest` in `capture.py` to
serialize generation fields in this order:

```text
max_output_tokens
temperature
reasoning_effort
text_verbosity
reasoning_mode
prompt_cache_mode
prompt_cache_ttl
service_tier
```

Serialize native-v2 price fields in the exact order `currency`, `effective_date`, `source_url`,
`service_tier`, the five rate fields in stable-interface order, and `source_evidence`. This rule does
not authorize a legacy-price conversion.

Pin `openai==3.3.1` in `pyproject.toml` and regenerate `uv.lock`. The separate precredential RED/GREEN
steps below prove the installed version, lock member, and typed SDK contract before provider access.
Cross-slice prerequisite: Evaluation Task 1 must first provide the package-exported canonical trio
owned by `laconian_eval.benchmark.attachments`. This slice imports that owner object; it does not
define an interim encoder while waiting for Evaluation.

- [ ] **Step 5: RED-test the pinned SDK precredential gate and public exports**

Add `test_benchmark_sdk_contract_rejects_invalid_inputs_without_provider_access` to
`tests/test_openai_provider.py`. Use provider-call, environment-read, credential-read,
client-construction, and network spies initialized to zero. Monkeypatch only the validator's private
installed-version seam to return `3.3.0`, a non-string, and to raise
`importlib.metadata.PackageNotFoundError`; each maps to `installed-version`. Independently supply a
wrong C0 `uv.lock` digest, delete one
required typed request field from each exact request-union member, replace either exact request-union
member, and remove or replace each of the four response-content roots, each canonical accounting
path, and the separate returned-model path in the exact SDK model graph. Assert the output graph
check stops at the `response.output` root and never requires every output-union branch to expose
`.text`; `Response.output_text` is an unmodeled property and cannot satisfy the check.
Import/forward-reference/type-hint resolution failures map only to the
matching `request-model` or `response-model` code. Independently monkeypatch the sole pure
Responses-kwargs builder to omit,
rename, add, reorder, or change each frozen projection member and require `serializer-projection`.
Parameterize `c0_uv_lock_bytes` as `str`, `bytearray`, `memoryview`, a `bytes` subclass, empty bytes,
and `1_048_577` bytes; parameterize the expected digest as null, bool, bytes, uppercase, short, and
non-hex text, plus a `str` subclass. Exact built-in bytes and exact built-in string are required and
the digest is exactly 64 lowercase hexadecimal
characters; type/bound failures use `lock-entry`, malformed expected hashes and digest mismatches use
`lock-digest`.

Also parametrize malicious but digest-consistent lock bytes: pass each fixture's own independently
computed SHA-256 as `expected_c0_uv_lock_sha256`, then require `lock-entry` for a missing or duplicate
`openai` package; invalid UTF-8 or TOML; wrong version; unknown or duplicate member key; missing,
duplicate, reordered, or
renamed dependency; registry, editable, path, git, or directory source; missing or duplicate sdist or
wheel; and a changed artifact URL, SHA-256, byte length, or upload time. Include one case for every
literal in the frozen member below. This proves semantic lock validation independently of the whole-
file digest check. The public validator has no caller override for version, lock interpretation,
allowlist values, qualified model names, union members, fields, or paths. Every case must raise the
stable SDK-contract error before constructing a provider/client, reading environment or credentials,
or touching the network:

```python
assert (
    provider_calls,
    environment_reads,
    credential_reads,
    client_constructions,
    network_calls,
) == (
    0,
    0,
    0,
    0,
    0,
)
```

Add `test_benchmark_sdk_contract_accepts_frozen_openai_member`. Read the checked-in `uv.lock` as
bytes, independently SHA-256 those bytes, leave the real installed `openai==3.3.1` typed models in
place, and assert the function returns literal `None` while the same five spies remain zero. Parse
the lock independently with `tomllib`, select its sole `openai` member, and assert its complete
source/dependency/sdist/wheel structure equals the Step 6 constants; this positive assertion must not
call or import the production lock-member normalizer.

In `tests/test_public_contract.py`, add
`test_benchmark_sdk_contract_has_one_public_owner`. Import these exact public names from both
`laconian_eval.providers.openai` and `laconian_eval.providers`:

```text
BENCHMARK_OPENAI_REQUEST_FIELDS_V1
BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1
BENCHMARK_OPENAI_RESPONSE_PATHS_V1
BENCHMARK_OPENAI_RETURNED_MODEL_PATH_V1
BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1
BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1
BENCHMARK_OPENAI_LOCK_REGISTRY_V1
BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1
BENCHMARK_OPENAI_LOCK_SDIST_V1
BENCHMARK_OPENAI_LOCK_WHEELS_V1
BenchmarkSDKContractErrorCode
BenchmarkSDKContractError
VerifiedBenchmarkSDKContractV1
require_benchmark_sdk_contract
```

Assert each re-export is the identical object, the record/error/function `__module__` values are
`laconian_eval.providers.openai`, and `laconian_eval.providers.__all__` contains each name exactly
once. `providers/__init__.py` defines no wrapper, alias record, fallback constant, or second validator.

The same test imports `CanonicalJSONV1Error`, `canonical_json_v1`, and
`parse_canonical_json_v1` from `laconian_eval.benchmark`, imports their owner module as
`laconian_eval.benchmark.attachments`, and requires package-export identity for all three. Production
`providers/openai.py` imports only
`canonical_json_v1 as _canonical_json_v1` from the package export; assert that private imported object
is identical to `attachments.canonical_json_v1`, that its `__module__` is
`laconian_eval.benchmark.attachments`, and that none of the canonical trio appears in
`laconian_eval.providers.__all__`. AST/source assertions reject a locally defined encoder, parser,
error class, wrapper, or fallback. Foundations neither imports nor defines
`ProtocolSubjectKindV1` or `PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1`; those are irrelevant to this
slice and remain solely owned by `laconian_eval.benchmark.protocol_review`.

```python
import ast
import inspect

import laconian_eval.benchmark as benchmark
import laconian_eval.providers as providers
from laconian_eval.benchmark import attachments
from laconian_eval.providers import openai as provider_openai

assert benchmark.CanonicalJSONV1Error is attachments.CanonicalJSONV1Error
assert benchmark.canonical_json_v1 is attachments.canonical_json_v1
assert benchmark.parse_canonical_json_v1 is attachments.parse_canonical_json_v1
assert provider_openai._canonical_json_v1 is attachments.canonical_json_v1
assert provider_openai._canonical_json_v1.__module__ == "laconian_eval.benchmark.attachments"
canonical_owner_names = {
    "CanonicalJSONV1Error",
    "canonical_json_v1",
    "parse_canonical_json_v1",
}
assert canonical_owner_names.isdisjoint(providers.__all__)

tree = ast.parse(inspect.getsource(provider_openai))
locally_defined = {
    node.name
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
}
assert canonical_owner_names.isdisjoint(locally_defined)
assert not {name for name in locally_defined if "canonical_json_v1" in name.lower()}
```

Run:

```bash
uv run pytest tests/test_openai_provider.py::test_benchmark_sdk_contract_rejects_invalid_inputs_without_provider_access tests/test_openai_provider.py::test_benchmark_sdk_contract_accepts_frozen_openai_member tests/test_public_contract.py::test_benchmark_sdk_contract_has_one_public_owner -q
```

Expected: FAIL because the pure precredential SDK/lock/type/path/projection validator does not exist; the
provider-call spy remains exactly zero.

- [ ] **Step 6: Implement and GREEN the pinned SDK precredential gate**

Implement and export this sole owner contract from `src/laconian_eval/providers/openai.py` and
re-export the identical objects from `laconian_eval.providers`. The string tuples below are immutable,
ordered protocol constants; no implementation may reconstruct them from the caller-supplied lock
bytes or installed SDK:

```python
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
```

`BENCHMARK_OPENAI_REQUEST_FIELDS_V1` is the exact typed-model field capability set checked against
both request union members; it is not the emitted-key set. In particular, the captured request
configuration binds `tools=[]`, the SDK request type must expose `tools`, and the sole live serializer
enforces “no tools” by omitting that key. The emitted nine-key probe below is the distinct exact
serializer projection.

Task 2 also implements the sole pure serializer builder with exact signature
`_public_benchmark_responses_kwargs(request: PublicBenchmarkRequestV1) -> dict[str, object]` in
`providers/openai.py`. It returns a new insertion-ordered mapping with keys in this exact order:
`model`, `instructions`, `input`, `max_output_tokens`, `store`, optional `reasoning`, optional `text`,
`prompt_cache_options`, `service_tier`. It never emits `temperature` when null and never emits
`tools`, `reasoning_mode`, `prompt_cache_key`, `prompt_cache_retention`,
`prompt_cache_breakpoint`, or another key. Task 3 must call this same object for canonical request
bytes, their plain SHA-256, the capture projection, and the provider call. The returned mapping
object itself is the capture projection: Task 3 defines no durable request-projection schema, copy,
second serializer builder, or second mapping. The confirmatory medium/medium case remains the exact
nine-key projection.

The exact public function signature is
`require_benchmark_sdk_contract(*, c0_uv_lock_bytes: bytes,
expected_c0_uv_lock_sha256: Sha256) -> None`; it has no positional or additional keyword parameters.
The validator first requires `type(c0_uv_lock_bytes) is bytes`, length `1..1_048_576`,
`type(expected_c0_uv_lock_sha256) is str`, and an expected digest matching `^[0-9a-f]{64}$`;
annotations or coercion never substitute for those checks. It
SHA-256-hashes the exact supplied bytes and uses `hmac.compare_digest` against the independently
verified expected member hash. It then requires
`importlib.metadata.version("openai") == "3.3.1"`, decodes the lock as strict UTF-8, and parses TOML
with `tomllib`; it rejects a non-list
`package`, more than `4_096` package members, and every parser exception as `lock-entry`. It requires
exactly one `openai` package and exact parsed equality of its `name`, `version`, source mapping,
ordered dependency mappings, sdist mapping, and
single ordered wheel mapping to the frozen literals above; it rejects missing, duplicate, unknown,
editable, path, git, or directory-source members. Upload times are compared as the exact source
strings, never normalized datetimes. Other package entries are not authority for this check.

It imports only the two literal SDK qualified types above. For `ResponseCreateParams`, it uses
`typing.get_args` and requires the ordered union to be exactly
`ResponseCreateParamsNonStreaming | ResponseCreateParamsStreaming`; it resolves each member with
`typing.get_type_hints` and requires every request field in the literal tuple in both members. It
walks each of the four response-content roots, the nine accounting paths, and the separate
`response.model` path through only the
`Response.model_fields`/resolved annotation graph, unwrapping typed nullable/union members and
requiring every branch to expose the next component. The content check stops at the exact
`response.error` and `response.output` roots; it does not require every member of the output union to
expose `.text`. Runtime values, examples, serialization output, `getattr` fallbacks, `Any`, and SDK
convenience aliases—including unmodeled `Response.output_text`—cannot satisfy a typed-model check.
The verified record stores `response_content_paths` in the constant's exact order immediately after
`returned_model_path` and before `serializer_projection_sha256`; it participates in the record's
self-digest. Tests delete, replace, and reorder every content root and mutate that record field
independently.

Finally, the gate constructs one internal `PublicBenchmarkRequestV1` with
`case_id="sdk-contract-probe-v1"`, `arm="if"`, `repetition=0`, requested model `gpt-5.6-sol`, the two
literal instruction/input strings encoded above, `max_output_tokens=1024`, `temperature=None`,
`timeout_seconds=120.0`, medium effort/verbosity, and the exact explicit/`30m`/default/omitted/
`openai-utf8-envelope-v1`/`272000` policy. It passes that request through the sole pure builder,
first requires `tuple(result)` to equal the nine-key order above, then encodes it with the identical
package-exported `_canonical_json_v1` owner object, requires byte equality with the frozen canonical
bytes, and independently recomputes their plain SHA-256. It never calls Foundation's more permissive
capsule encoder or defines a local CanonicalJSONV1 implementation.
Missing, extra, reordered, renamed, defaulted, or
changed members raise `serializer-projection`; the test mutates every member independently. This
probe never creates a provider/client and never reads environment, credentials, or network.

Internally it constructs and self-verifies the strict record whose digest is
`stable_digest("laconian-benchmark-sdk-contract-v1", payload_without_contract_sha256)`, then returns
`None`; callers cannot serialize the transient record as authority. The sole private builder has the
exact signature `_build_verified_benchmark_sdk_contract(*, c0_uv_lock_bytes: bytes,
expected_c0_uv_lock_sha256: Sha256) -> VerifiedBenchmarkSDKContractV1`. The public function calls it,
requires its class-bound self digest, discards the object, and returns literal `None`. Tests call the
private builder only to inspect every exact field and independently recompute the digest; no package
exports or Runtime code may import it.
It accepts no installed-version/model/path override, filesystem path, credential, client, callback,
or provider object. Tests patch only the private installed-version, SDK-type import, and serializer-
projection seams and assert the exact signature,
field order, nine response paths, separate returned-model path, four ordered response-content roots
immediately after it, frozen lock constants, module
ownership, package object identity, internal self digest, and literal `None` return.
`BenchmarkSDKContractError` is the sole exported error for this function and has only the closed
codes `installed-version`, `lock-digest`, `lock-entry`, `request-model`, `response-model`, and
`serializer-projection`.
Every failure sets `.code` to exactly one of those literals and `.args` to the one constant message
shown above; no parser text, import exception, type representation, path, bytes, or provider value is
chained, rendered, or retained on the public exception. Every RED vector asserts
`exc.value.__cause__ is None`, `exc.value.__context__ is None`, and
`exc.value.args == ("public benchmark SDK contract verification failed",)`; implementations collect
the closed code inside `except` and raise only after leaving that handler.

This Foundation function is a pure precredential boundary and does not construct or call a provider.
Runtime is the sole orchestration owner: it passes the verified C0 member bytes/hash and calls this
exact exported object before every benchmark credential lookup, client construction, or provider
access, including immediately before the secret-read expression. Do not change the legacy provider
path. Any version/lock/type/path/projection failure raises the closed content-free
`BenchmarkSDKContractError(code)` while all five spies remain zero.

Run:

```bash
uv run pytest tests/test_openai_provider.py::test_benchmark_sdk_contract_rejects_invalid_inputs_without_provider_access tests/test_openai_provider.py::test_benchmark_sdk_contract_accepts_frozen_openai_member tests/test_public_contract.py::test_benchmark_sdk_contract_has_one_public_owner -q
```

Expected: PASS; every invalid-contract case and malicious lock variant fails closed and all five
spies remain exactly zero, and every public re-export is the owner object.

- [ ] **Step 7: RED-test request-config identity coverage**

Add `test_request_config_hash_binds_reasoning_cache_and_tier_policy` to
`tests/capsule/test_planning.py`. Starting with one resolved manifest, mutate exactly one of these
multi-valued fields per case and assert a different hash:

```python
[
    ("reasoning_effort", None),
    ("reasoning_effort", "low"),
    ("text_verbosity", None),
    ("text_verbosity", "low"),
]
```

Independently reconstruct the canonical preimage shown above and assert:

```python
assert request_config_sha256(manifest) == stable_digest(
    "laconian-request-config-v1",
    expected_preimage,
)
```

The independently constructed preimage must contain literal explicit cache mode and `30m` TTL,
recursive proof of no breakpoint key, literal `service_tier: default` in both generation policy and exact wire-policy positions, the bound version, the 65,536-token envelope allowance, and the
272,000-token standard-tier maximum. Assert omission, `auto`, project-default inference, and every
non-default service tier are unrepresentable by validated inputs. Assert none of `prompt_cache_key`,
`prompt_cache_retention`, or a cache breakpoint occurs in its canonical bytes.

Add `test_conservative_input_token_bound_contract_is_exact`. Assert `(0, 0) -> 65_536`, UTF-8 byte
counts add arithmetically without tokenizer or float conversion, exact equality at 272,000 is
representable, and bool/negative counts are rejected.

Run:

```bash
uv run pytest tests/capsule/test_planning.py::test_request_config_hash_binds_reasoning_cache_and_tier_policy tests/capsule/test_planning.py::test_conservative_input_token_bound_contract_is_exact -q
```

Expected: FAIL because the current preimage ignores the request-policy fields and the frozen
input-bound constants/helper are absent.

- [ ] **Step 8: Bind the new fields and run focused regressions**

Add the exact generation, prompt-cache, literal default-service-tier, and input-bound mappings from the stable preimage to
`request_config_sha256`.

Run:

```bash
uv run pytest tests/capsule/test_manifest_models.py tests/capsule/test_capture.py tests/capsule/test_planning.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit manifest and request identity support**

```bash
git add src/laconian_eval/capsule/schema.py src/laconian_eval/capsule/manifest_models.py src/laconian_eval/capsule/capture.py src/laconian_eval/capsule/planning.py src/laconian_eval/providers/base.py src/laconian_eval/providers/openai.py src/laconian_eval/providers/__init__.py pyproject.toml uv.lock tests/capsule_helpers.py tests/capsule/test_manifest_models.py tests/capsule/test_capture.py tests/capsule/test_planning.py tests/test_public_contract.py tests/test_openai_provider.py
git commit -m "feat: bind generation cache and default-tier pricing policy"
```

### Task 3: Send exact cache-safe default-tier Responses kwargs and preserve complete token/tier evidence

**Files:**
- Modify: `src/laconian_eval/providers/base.py`
- Modify: `src/laconian_eval/providers/__init__.py`
- Modify: `src/laconian_eval/providers/openai.py`
- Modify: `src/laconian_eval/providers/replay.py`
- Modify: `src/laconian_eval/capsule/attempts.py`
- Modify: `src/laconian_eval/capsule/execution.py`
- Modify: `tests/test_public_contract.py`
- Modify: `tests/test_openai_provider.py`
- Modify: `tests/test_providers.py`
- Unchanged legacy compatibility boundary (do not modify): `tests/fixtures/replay-responses.yaml`
- Create: `tests/fixtures/replay-public-benchmark-responses.yaml`
- Modify: `tests/capsule/test_attempts_v2.py`
- Modify: `tests/capsule/test_execution.py`
- Modify: `tests/capsule_helpers.py`

- [ ] **Step 1: RED-test the exact wire mapping**

Add `test_confirmatory_request_sends_exact_reasoning_verbosity_cache_and_service_tier` to
`tests/test_openai_provider.py`. Use the injected fake Responses client and this request:

```python
request = PublicBenchmarkRequestV1(
    case_id="case-en",
    arm="if",
    repetition=0,
    requested_model_id="gpt-5.6-sol",
    instructions="instruction",
    prompt="prompt",
    max_output_tokens=1024,
    temperature=None,
    timeout_seconds=120.0,
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
```

Assert the captured kwargs equal exactly:

```python
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
```

Also assert null effort/verbosity omit both nested kwargs. No accepted request contains
`reasoning_mode`, `prompt_cache_key`, `prompt_cache_retention`, any other cache-control member,
`prompt_cache_breakpoint`, `tools`, `previous_response_id`, or `temperature` when temperature is
null, but every accepted request contains exactly `service_tier="default"`. Parameterize
`service_tier` as null, bool, integer, object, `auto`, `flex`, `priority`, and `ultrafast`; each must
fail strict request validation before the fake client records a call. An ambient project configured
for a different tier must not affect captured kwargs. Add
`test_nonnull_benchmark_temperature_rejects_before_responses_call`; parameterize finite zero,
positive, and negative floats and assert the injected fake Responses client's call list and network
spy remain zero. Execution may additionally reject before provider construction, but the provider
method is tested on an already constructed provider and promises only zero client/API calls.

Also add
`test_benchmark_request_bytes_provider_kwargs_and_capture_projection_are_identical` and
`test_recursive_cache_control_helper_rejects_synthetic_trees_without_widening_request_types`. The first
constructs the one exact expected canonical byte literal without calling the production mapper, then
uses the identical package-exported `canonical_json_v1` owner on the frozen request-member projection
and the one object returned by `_public_benchmark_responses_kwargs`, requires the adapter's captured
projection to be that same object by identity, and requires the canonical request bytes and plain
SHA-256 to derive from it before that same mapping is expanded into the fake provider call. It imports
that object and its error/parser companions through `laconian_eval.benchmark`, proves identity to
`benchmark.attachments`, and defines no local encoder, durable request schema, mapping copy, or
second mapper. Assert its confirmatory result has the exact frozen nine-key order and values.

The second test calls `_assert_no_public_benchmark_cache_control` directly on synthetic dict/list/
tuple trees with `prompt_cache_breakpoint` at the root and two nested depths, then repeats for
`prompt_cache_key`, `prompt_cache_retention`, builder-owned `prompt_cache_options`, and literal
`prompt_cache_unknown`. Every exact built-in string key beginning `prompt_cache_` is rejected below
instructions/input; non-string mapping keys and string subclasses fail closed rather than bypassing
the rule. It also passes the real `instructions` and `prompt` string leaves and requires success.
Separately assert the public
request annotations and runtime values remain exactly `str | None` and `str`; no synthetic object
tree is accepted by `PublicBenchmarkRequestV1` or sent to the fake client.

Add `test_standard_tier_bound_rejects_before_client_call`. Assert the pure bound counts UTF-8 bytes
rather than characters, accepts exact equality at 272,000, rejects one byte above it in
`OpenAIProvider._validate_request`, reports `delivery_certainty="definitely_not_sent"`, and leaves
the fake client's call list empty. Parameterize bool and negative byte counts against the pure helper.

- [ ] **Step 2: Run the wire RED test**

Run:

```bash
uv run pytest tests/test_openai_provider.py::test_confirmatory_request_sends_exact_reasoning_verbosity_cache_and_service_tier tests/test_openai_provider.py::test_nonnull_benchmark_temperature_rejects_before_responses_call tests/test_openai_provider.py::test_benchmark_request_bytes_provider_kwargs_and_capture_projection_are_identical tests/test_openai_provider.py::test_recursive_cache_control_helper_rejects_synthetic_trees_without_widening_request_types tests/test_openai_provider.py::test_standard_tier_bound_rejects_before_client_call -q
```

Expected: FAIL because the request/cache/tier policy fields, exact cache and literal default-tier wire
mapping, non-null-temperature preclient rejection, generic helper seam, identity-shared capture
projection, and provider-side standard-tier rejection are absent.

- [ ] **Step 3: Implement strict request fields and adapter validation**

Construct only `PublicBenchmarkRequestV1` from the captured policy; do not widen or default the
legacy request. In `OpenAIProvider._validate_benchmark_request`, accept only exact strings from the
aliases, require policy `reasoning_mode == "omitted"`, `prompt_cache_mode == "explicit"`,
`prompt_cache_ttl == "30m"`, and `service_tier == "default"`, then compute strict UTF-8
instruction/prompt byte lengths and reject a conservative bound above 272,000 before calling the
client. Preserve `instructions: str | None` and `prompt: str` exactly. Reject every non-null
`temperature` before any `client.responses.create`/Responses API call; the fake call list remains
zero. Execution may independently reject before constructing the provider, but Task 3 does not rely
on that stronger caller ordering.

Implement `OpenAIProvider.generate_benchmark(request: PublicBenchmarkRequestV1) ->
PublicBenchmarkProviderOutcomeV1` without changing legacy `generate`. In that benchmark-only method,
implement the recursive validator and call both it and the sole Task 2-owned serializer builder:

```python
def _assert_no_public_benchmark_cache_control(value: object) -> None:
    """Recursively reject every exact string key beginning prompt_cache_."""
```

Run the recursive validator on the exact real `instructions` and `prompt` string leaves before
building the mapping; its recursive object-tree behavior is a direct-test hardening seam and never
widens either request field. It rejects every exact built-in string key with prefix
`prompt_cache_`; only the top-level `prompt_cache_options` mapping later created by the builder is
allowed. Call `_public_benchmark_responses_kwargs` exactly once. Its returned
mapping object is the sole capture projection: canonicalize and hash that object, retain that same
object for capture, and call `client.responses.create(**mapping)` from it. Do not construct a copy,
durable projection model, second serializer, or second cache/tier mapper. Add only nonnull
effort/verbosity in the Task 2-owned builder:

```python
if request.reasoning_effort is not None:
    kwargs["reasoning"] = {"effort": request.reasoning_effort}
if request.text_verbosity is not None:
    kwargs["text"] = {"verbosity": request.text_verbosity}
kwargs["prompt_cache_options"] = {
    "mode": request.policy.prompt_cache_mode,
    "ttl": request.policy.prompt_cache_ttl,
}
kwargs["service_tier"] = request.policy.service_tier
```

Update capsule request reconstruction in `execution.py` to construct the versioned benchmark policy
from all captured resolved fields. Do not change the legacy runner request builder or bytes.

- [ ] **Step 4: RED-test cache-write, reasoning, and returned-tier evidence**

Add OpenAI response fixtures whose `usage.input_tokens_details.cache_write_tokens` is respectively
`0`, `3`, absent, `-1`, `True`, and large enough that cached plus cache-write exceeds input. Assert:

```text
0       -> cache_write_tokens=0, cache_write_status=reported_zero
3       -> cache_write_tokens=3, cache_write_status=reported_nonzero; preserve the usable response
absent  -> cache_write_tokens=null, cache_write_status=missing
-1      -> malformed provider usage; preserve no trusted zero
True    -> malformed provider usage; preserve no trusted zero
sum-big -> malformed provider usage; preserve no trusted zero
```

For `-1`/`True` in one read/write field, assert the adapter still returns
`PublicBenchmarkResponseEvidenceV1`, sets only that count to null/status `invalid`, and preserves
response ID, output, requested/returned model, tier, applied cache control, totals, reasoning, and
the other usable cache count/status. For a jointly inconsistent read-plus-write sum, require both
counts to be null and both statuses `invalid` even when each raw count is independently a
nonnegative integer; preserve the same response/output/other usable usage. No malformed read/write
detail may produce `PublicBenchmarkProviderErrorEvidenceV1`.

The same `input_tokens_details` fixture always carries an independently asserted
`cached_tokens`. Add fixtures whose `usage.output_tokens_details.reasoning_tokens` is respectively
`7`, absent, `-1`, `True`, and greater than `output_tokens`. Assert the adapter produces:

```text
7       -> reasoning_tokens=7, reasoning_token_accounting=reported
absent  -> reasoning_tokens=null, reasoning_token_accounting=not_reported
-1      -> reasoning_tokens=null, reasoning_token_accounting=invalid
True    -> reasoning_tokens=null, reasoning_token_accounting=invalid
too-big -> reasoning_tokens=null, reasoning_token_accounting=invalid
```

Every valid response becomes `PublicBenchmarkResponseEvidenceV1`; legacy `GenerationResult` bytes
and constructors remain unchanged. Add an exact committed-output matrix over `response.output`:
iterate items in order, use only exact `type="message"` items, iterate content in order, append
`.text` only for exact `type="output_text"` members, and concatenate with no separator. Cover
multiple message/content members, ignored nonmessage/non-output-text variants, reordered members,
missing/malformed sequences/discriminators/text, a string subclass, blank result, over-limit result,
bytes, bool, object, absent, and null. Accepted pieces and the concatenated result are exact built-in
strings; the final value is nonblank and within `OutputString`'s bound. Never read or monkeypatch the
SDK `response.output_text` convenience property. Control-bearing but otherwise bounded/nonblank
output remains ephemeral response evidence and is handled only by the existing attempts-owned
sanitizer before durable `RawAttemptV2` construction. Assert the derived value appears as
`output_text` immediately after `raw_response_sha256` in the strict response-evidence shape, no
output-source digest exists, `raw_response_source` immediately follows it, and entry four
(`response.output`) of that source binds it. Directly test the exact `OutputString` before-validator:
accept an exact built-in string at the `RESOURCE_LIMITS_V1.output_utf8_bytes` encoded boundary,
reject a string subclass, bytes, bool, object, blank input, a lone surrogate, and one encoded byte
over the bound; accept and preserve byte-for-byte bounded nonblank control-bearing and non-NFC
strings. Prove normalization passes those accepted strings through the existing sanitizer and does
not durably copy the unsanitized input.

In `tests/capsule/test_attempts_v2.py`, add:

```python
@pytest.mark.parametrize(
    ("reasoning_tokens", "accounting", "expected"),
    [
        (7, "reported", 13),
        (0, "reported", 20),
        (None, "not_reported", None),
        (None, "invalid", None),
    ],
)
def test_visible_output_tokens_require_valid_reasoning_breakdown(
    reasoning_tokens: int | None,
    accounting: str,
    expected: int | None,
) -> None:
    usage = AttemptUsageV2(
        input_tokens=5,
        output_tokens=20,
        total_tokens=25,
        cache_read_tokens=0,
        cache_write_tokens=0,
        ordinary_uncached_input_tokens=5,
        reasoning_tokens=reasoning_tokens,
        availability="complete",
        source="provider",
        cache_read_status="reported_zero",
        cache_write_status="reported_zero",
        reasoning_token_accounting=accounting,
    )
    assert visible_output_tokens(usage) == expected
```

Add `test_attempt_usage_tracks_cache_reads_and_writes_independently`. Accept reported `(read,
write)` pairs `(0, 0)`, `(2, 0)`, and `(0, 2)` plus a `missing` null write count. Reject a reported
null count, an unreported nonnull count, either count above input, and a combined read/write count
above input. Canonical round trips must retain a nonzero write count exactly.

Add `test_openai_returned_service_tier_is_preserved_and_classified` with otherwise valid response
fixtures. Assert this exact matrix without altering output, delivery, or valid usage evidence:

```text
"default"  -> returned_service_tier="default",  service_tier_status=reported_default
"priority" -> returned_service_tier="priority", service_tier_status=mismatch
absent      -> returned_service_tier=null,       service_tier_status=missing
blank       -> returned_service_tier=null,       service_tier_status=missing
True        -> returned_service_tier=null,       service_tier_status=missing
object      -> returned_service_tier=null,       service_tier_status=missing
over-limit  -> returned_service_tier=null,       service_tier_status=missing
```

Add independent applied/read/write RED matrices. Applied values are exact `explicit`/`30m`, missing,
mismatched, or malformed and must map to `reported_exact`, `missing`, `mismatch`, or `invalid`.
Read and write values cover zero, positive, absent, bool, negative, over-input, inconsistent sum,
and a forged source digest. Assert the exact canonical response paths and reject every alternate
path. Add `test_raw_response_source_projection_is_exact_and_bounded`: independently construct all
14 ordered `{path, present, value}` entries; distinguish missing from explicit null; require a
present SDK error model to bind its exact `model_dump(mode="json")` code/message tree and bind the
complete `response.output` tree; independently recompute the stable digest; and reject every
missing/extra/reordered/renamed entry, malformed presence relation, unsupported tree/type,
nonfinite value, model-dump failure, and `RESOURCE_LIMITS_V1.raw_jsonl_row_bytes` overflow. Assert
the digest is computed from the class-bound source's exact `model_dump(mode="json")`, is disclosed
as a typed SDK projection, and is never alleged HTTP bytes. For response evidence, require the exact
source object and digest together. For provider-error evidence, reject every one-null/one-nonnull
source/digest pair, recompute the digest when the pair is present, and permit the both-null case only
for no-response and the exact projection-failure record. Normalize valid response and error
outcomes with a source and prove the normalizer transfers the verified digest only into the
already-listed per-field source-digest fields: neither a standalone `raw_response_sha256` nor
`raw_response_source`, a raw output tree, or unsanitized `output_text` reaches normalized evidence,
`RawAttemptV2`, attachments, or serialized durable bytes.
Also assert `requested_model_id` and `returned_model_id` plus source digest round-trip; returned IDs
may differ from requested IDs, while later consistency is deliberately outside this task.

Use the existing bounded/control-safe provider-metadata policy for returned strings. Add one
response that has a safe tier but invalid/missing output; its
`PublicBenchmarkProviderErrorEvidenceV1` must still expose the sanitized returned tier and derived
status and has no output field. Separately add completed responses with valid output but malformed
cache, reasoning, tier, or accounting details; every one remains
`PublicBenchmarkResponseEvidenceV1`, carries the valid `output_text`, and preserves all other usable
evidence while only affected fields/statuses degrade. Missing or mismatched tier is permanent
policy evidence, never a transient provider error and never an automatic retry reason.

In `tests/capsule/test_attempts_v2.py`, add
`test_raw_attempt_service_tier_matrix_is_strict_and_preserves_billable_evidence`. Assert every valid
row has `requested_service_tier="default"`; the three received-response status/value combinations above round-trip
canonically; every inconsistent combination is rejected. Normalize adversarial
`PublicBenchmarkResponseEvidenceV1` and `PublicBenchmarkProviderErrorEvidenceV1` instances with
`requested_service_tier="default"` and prove normalization derives
the status rather than trusting an injected status. Add both no-response cases: a definitely-not-sent
configuration failure becomes `not_applicable_definitely_not_sent`, and a structured
`definitely_rejected` 429 becomes `not_applicable_definitely_rejected`; both have null
`returned_service_tier` and unavailable usage, while the 429 retains its request ID and exact error
evidence. Reject either not-applicable status for `response_received`/`unknown`, the wrong delivery
certainty, a nonnull returned tier, or any usage count. For a mismatch, omission, and unsafe value on delivered/unknown work, assert
`delivery_certainty`, usage, cache-write counts, output/discard hashes, and provider request ID remain
intact. The public-campaign handoff must expose those fail-closed statuses as forbidding reservation
release; it must keep both not-applicable statuses distinguishable so the runtime's exact
definite-rejection retry policy remains possible. The runtime slice owns both the durable STOP and
retry transitions.

Also add `test_benchmark_evidence_source_digests_are_one_envelope`. Construct valid response,
received-response-error with a valid source projection, received-response projection failure,
definitely-not-sent, and definitely-rejected evidence, then independently mutate each per-field
digest. Class-bound validation must reject every mutation. The first two carry the exact class-bound
`raw_response_source`, independently recompute `raw_response_sha256` from
`raw_response_source.model_dump(mode="json")`, and require all per-field digests to equal it. The
last three require both null `raw_response_source` and null `raw_response_sha256` and all per-field
digests to equal `error_source_sha256`; either field alone and raw-null outside the two closed cases
are rejected. For every error record independently recompute `error_source_sha256` from its model
dump after excluding itself and every per-field source digest, then mutate every included field,
including `raw_response_source` when present, and every excluded field to prove the preimage is exact
and acyclic. No test or implementation computes a digest from one nested path.

The projection-failure vector supplies a Responses object containing one unsupported or oversized
source value and requires output-free `PublicBenchmarkProviderErrorEvidenceV1` with
`delivery_certainty="response_received"`, wholly unavailable usage, null response-derived values,
safe missing/invalid statuses, all per-field digests equal to `error_source_sha256`, and full
worst-case exposure. Assert it never truncates, stringifies, partially hashes, or retains output.

- [ ] **Step 5: Run the usage RED gate**

Run:

```bash
uv run pytest tests/test_openai_provider.py -k 'cache_write_tokens or reasoning_tokens or cache_policy or service_tier or malformed or raw_response_source' tests/capsule/test_attempts_v2.py::test_visible_output_tokens_require_valid_reasoning_breakdown tests/capsule/test_attempts_v2.py::test_attempt_usage_tracks_cache_reads_and_writes_independently tests/capsule/test_attempts_v2.py::test_raw_attempt_service_tier_matrix_is_strict_and_preserves_billable_evidence tests/capsule/test_attempts_v2.py::test_benchmark_evidence_source_digests_are_one_envelope -q
```

Expected: FAIL because the benchmark outcome records, normalized evidence, and
`RawAttemptV2` do not expose the required cache-write/reasoning/tier evidence and the visible-token
helper is absent.

- [ ] **Step 6: Implement exact applied/read/write/reasoning/tier/model evidence without hiding usable evidence**

Parse only the nine canonical cache/tier/usage response paths listed in the stable interface, plus
the separately frozen `response.model` path solely for returned-model evidence. Derive committed
`output_text` only by the ordered `response.output` message/content traversal in the stable
interface; never read the SDK convenience property. The result requires an exact built-in,
strictly UTF-8-encodable, nonblank string whose encoded length is at most
`RESOURCE_LIMITS_V1.output_utf8_bytes`, and is source-bound because the full `response.output` tree
is entry four of the common raw projection; it adds no source-digest field and is not an accounting
or model path. The `OutputString` before-validator returns accepted text exactly, with no
normalization, strip, or control rejection; durable normalization still routes it through the
existing sanitizer. Derive
`AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`, and `ServiceTierStatus` from raw
values and delivery evidence; never accept status text from fixtures or provider objects.

Construct and class-bound revalidate `PublicBenchmarkRawResponseSourceV1` from the exact 14 ordered
paths before interpreting response fields. Preserve the missing-versus-explicit-null bit, call
`model_dump(mode="json")` for SDK BaseModel values, enforce exact capsule-canonical tree types and
the `raw_jsonl_row_bytes` bound, and compute the exact stable digest from
`source.model_dump(mode="json")`. When that projection exists, carry the exact source object and
digest together in the ephemeral outcome, and assign its `raw_response_sha256` to every
applied/read/write/tier/usage/reasoning/model source field, including fields whose sanitized value
is null. If it cannot be constructed, emit only the projection-failure error record specified
above. With no Responses object, keep both `raw_response_source` and `raw_response_sha256` null. For
every error record compute `error_source_sha256` from the exact exclusion preimage, which includes
the source/digest pair when present, then use it for every per-field source only when raw response
digest is null. Evidence validators independently recompute both source digests and enforce the
equality/allowed-raw-null matrix; do not hash individual paths. Do not infer one cache dimension
from another and never convert missing to zero.

Add `ReasoningTokenAccounting` and `_optional_reasoning_count(raw_usage, output_tokens)` in
`openai.py`. The helper returns `(count, "reported")`, `(None, "not_reported")`, or
`(None, "invalid")`; it records the defect without raising a legacy `ProviderError`.

Add `OutputString`, the benchmark outcome records, `PublicBenchmarkProviderOutcomeV1`, and
`PublicBenchmarkProvider` protocol solely in `capsule/attempts.py`; provider implementations and
`execution.py` import them directly from that owner. `capsule.schema` remains the sole owner of
`ServiceTier`. Within this evidence surface, `providers/base.py` owns
`ReasoningTokenAccounting`, exactly four status aliases (`ServiceTierStatus`,
`AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`), `TokenUsage`, and the request
types/bounds; it owns no benchmark outcome/evidence/protocol or `OutputString`. Do not alter legacy
`GenerationResult` or `ProviderError` bytes. In `openai.py`, read `response.service_tier` independently
before later response/content/usage checks. Exact bounded `default` becomes `reported_default`;
another safe bounded string becomes `mismatch` and is preserved; absence or an unsafe/unrepresentable
value becomes `missing` with no unsafe value serialized. Copy the derived fields into every
`PublicBenchmarkResponseEvidenceV1` and `PublicBenchmarkProviderErrorEvidenceV1`. Never infer the requested tier from a missing response field,
never coerce a value, and never discard usage/delivery evidence because the status is not
`reported_default`.
For a benchmark provider-error evidence record created before any Responses object exists, derive
`not_applicable_definitely_not_sent` or `not_applicable_definitely_rejected` only when delivery exactly
matches that suffix and provider usage is wholly unavailable. An `unknown` delivery with no returned
tier remains `missing` and therefore retains worst-case exposure; do not use either not-applicable
status as a generic missing-value default.

Treat malformed cache-read and cache-write details as field-level evidence defects, not provider
errors. After receiving a Responses object with valid completed output, malformed cache, reasoning,
tier, or accounting detail must retain `PublicBenchmarkResponseEvidenceV1`; set an individually
malformed cache dimension to null/`invalid` while preserving all other usable
response/output/usage evidence. If the combined read/write sum is inconsistent, set both dimensions
to null/`invalid`, even when each raw member alone is nonnegative, and preserve the other usable
fields. Never route those field-level defects through
`PublicBenchmarkProviderErrorEvidenceV1`.

Keep every outcome ephemeral until `normalize_public_benchmark_outcome` in the attempts owner first
class-bound revalidates the raw source/digest pair, applies the existing sanitizer, drops
`raw_response_source` and the unsanitized `output_text`, and constructs `RawAttemptV2`; never durably
persist either raw tree. A completed response with valid output remains response evidence for
malformed cache, reasoning, tier, or accounting fields. Only invalid/missing completed output or
another response structure that cannot form response evidence yields the output-free provider-error
evidence.

Extend `AttemptUsageV2`, `_unavailable_provider_usage`, `_normalize_provider_usage`, raw payload
helpers, and class-bound checks with `cache_read_tokens`, `cache_write_tokens`,
`ordinary_uncached_input_tokens`, and the two independent statuses. Extend `NormalizedProviderEvidenceV2`, `_constant_normalized_error`,
`_normalize_benchmark_result`, `_normalize_benchmark_error`,
`normalize_public_benchmark_outcome`, all raw-attempt constructors,
and `RawAttemptV2` with requested/returned service tier and status. The normalization entry point
requires `requested_service_tier: ServiceTier`, class-bound revalidates literal `default`, and
independently enforces the delivery-aware status/value matrix; it does not trust a dataclass annotation
or supplied status. Enforce the cache matrix described in the stable interface plus this exact cache
validation before the reasoning matrix:

```python
reported = {"reported_zero", "reported_nonzero"}
for status, count in (
    (self.cache_read_status, self.cache_read_tokens),
    (self.cache_write_status, self.cache_write_tokens),
):
    if (status in reported) != (count is not None):
        raise ValueError("cache status/value mismatch")
    if status == "reported_zero" and count != 0:
        raise ValueError("reported_zero requires exact zero")
    if status == "reported_nonzero" and (count is None or count <= 0):
        raise ValueError("reported_nonzero requires a positive count")
if self.input_tokens is not None:
    expected = self.input_tokens - (self.cache_read_tokens or 0) - (self.cache_write_tokens or 0)
    if expected < 0 or self.ordinary_uncached_input_tokens != expected:
        raise ValueError("ordinary uncached input is inconsistent")
```

Then enforce this exact reasoning matrix:

```python
if self.reasoning_token_accounting == "reported":
    if (
        self.reasoning_tokens is None
        or self.output_tokens is None
        or self.reasoning_tokens > self.output_tokens
    ):
        raise ValueError("reported reasoning accounting requires a consistent count")
elif self.reasoning_tokens is not None:
    raise ValueError("unreported or invalid reasoning accounting forbids a count")
```

Create `tests/fixtures/replay-public-benchmark-responses.yaml` with exact applied mode/TTL,
read/write/reasoning/tier, requested/returned model, and the exact response/output values needed to
construct the 14-entry source projection. Update
every benchmark-only fixture row to echo explicit/30m, read zero, write zero, literal returned
default tier, an exact requested model ID, and a separately consistent returned model ID. Implement
a strict benchmark-only parser used only by `ReplayProvider.generate_benchmark`; it derives every
status and constructs/recomputes the exact 14-entry source projection/digest rather than accepting a
fixture-supplied status or digest override. Keep the existing
`tests/fixtures/replay-responses.yaml`, legacy fixture schema/parser, and `ReplayProvider.generate`
unchanged in bytes and behavior.

Export `ServiceTier`, `AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`, and
`ServiceTierStatus` from `laconian_eval.providers`, list each exactly
once in `__all__`, and pin those public objects and the appended result/error fields in
`tests/test_public_contract.py`. Those are the only five new benchmark aliases exported through
`providers.__init__`; `ServiceTier` is the identical `capsule.schema` owner object and the four
statuses are the identical `providers.base` owner objects. Legacy exports remain unchanged, and no
benchmark outcome, evidence, protocol, `OutputString`, or reasoning-accounting alias is re-exported
there. Do not create a second tier alias in another provider module.

- [ ] **Step 7: Prove request reconstruction and legacy compatibility**

In `tests/capsule/test_execution.py`, extend the existing reconstructed-request assertion with:

```python
assert request.reasoning_effort == "medium"
assert request.text_verbosity == "medium"
assert request.policy.reasoning_mode == "omitted"
assert request.policy.prompt_cache_mode == "explicit"
assert request.policy.prompt_cache_ttl == "30m"
assert request.policy.service_tier == "default"
```

For a default-tier response, also assert the committed `RawAttemptV2` has
`requested_service_tier == returned_service_tier == "default"` and
`service_tier_status == "reported_default"`. Repeat with a safe non-default returned tier and prove the
canonical attempt retains it with `mismatch`, makes no retry of that plan item, and exposes the
non-`reported_default` status to the runtime policy boundary without releasing or rewriting any usage
evidence.

In `tests/test_providers.py`, load the new benchmark fixture through `generate_benchmark` and assert
its exact strict response/error shapes, derived statuses, and common source-digest invariant.
Independently mutate/miss/add/reorder each benchmark fixture member and require rejection. Snapshot
the existing legacy fixture bytes before and after, run its existing `generate` tests, and prove the
legacy parser/schema/method neither accepts benchmark fields nor changes behavior.

Run:

```bash
uv run pytest tests/test_public_contract.py tests/test_openai_provider.py tests/test_providers.py tests/capsule/test_attempts_v2.py tests/capsule/test_execution.py tests/test_runner.py tests/test_reporting.py -q
```

Expected: PASS. Existing legacy report expectations remain unchanged, while public-campaign capsule
evidence retains cache-write counts and requested/returned service-tier status for the later spend
ledger. Only `reported_default` is eligible for trusted-usage reconciliation; the two exact
not-applicable states carry no usage and preserve definite non-delivery/rejection semantics.

- [ ] **Step 8: Commit wire and token evidence**

```bash
git add src/laconian_eval/providers/base.py src/laconian_eval/providers/__init__.py src/laconian_eval/providers/openai.py src/laconian_eval/providers/replay.py src/laconian_eval/capsule/attempts.py src/laconian_eval/capsule/execution.py tests/test_public_contract.py tests/test_openai_provider.py tests/test_providers.py tests/fixtures/replay-public-benchmark-responses.yaml tests/capsule/test_attempts_v2.py tests/capsule/test_execution.py tests/capsule_helpers.py
git commit -m "feat: bind cache policy and token-tier evidence"
```

### Task 4: Bind literal default-tier policy and conservative input exposure into stable parent plan identities

**Files:**
- Modify: `src/laconian_eval/capsule/record_models.py`
- Modify: `src/laconian_eval/capsule/planning.py`
- Modify: `src/laconian_eval/capsule/prepare.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `src/laconian_eval/capsule/execution.py`
- Modify: `tests/capsule/test_record_models.py`
- Modify: `tests/capsule/test_planning.py`
- Modify: `tests/capsule/test_prepare.py`
- Modify: `tests/capsule/test_verify_prepared.py`
- Modify: `tests/capsule/test_execution.py`
- Modify: `tests/capsule_helpers.py`

- [ ] **Step 1: RED-test stable parent identities with no run UUID in the API**

Replace the run-bound golden in `tests/capsule/test_planning.py` with
`test_parent_plan_ids_are_stable_without_run_identity`. Materialize the same resolved
manifest/case index/arms twice and assert the same `PlanRowV1` tuple and byte-identical `plan_jsonl`
result. Inspect the signature and require that the new interface has no run/capsule UUID parameter;
call it only with `parent_manifest_sha256`:

```python
first = materialize_parent_plan(
    parent_manifest_sha256=SHA_A,
    resolved_manifest=manifest,
    case_index=case_index,
    captured_arms=arms,
)
second = materialize_parent_plan(
    parent_manifest_sha256=SHA_A,
    resolved_manifest=manifest,
    case_index=case_index,
    captured_arms=arms,
)
assert first == second
assert plan_jsonl(first) == plan_jsonl(second)
```

Add a second test changing only `parent_manifest_sha256` from `SHA_A` to `SHA_B`; assert every plan item, block, and pairing identity changes while row ordering, request field hashes, and input-token bounds remain equal.

- [ ] **Step 2: RED-test the exact independent digest preimages**

For one fixed case/repetition/arm, construct the three mappings from the stable-interface section using a tiny independent `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoder plus explicit domain prefix. Assert exact equality with production `block_id`, `pairing_unit_id`, and `plan_item_id`; the plan-item preimage includes the exact integer `input_token_bound`. Use `inspect.signature` to pin the exact keyword-only helper signatures and prove the old positional/run-bound signatures are rejected.

Add `test_case_index_and_plan_bind_default_service_tier_and_input_bound`. Assert the independently
constructed `request_config_sha256` preimage contains `service_tier: default` in both its generation
and exact-wire positions, and that every plan-item preimage binds that request-config digest. A
manifest with an omitted or non-default resolved tier must fail before plan materialization. Then use
ASCII and Cyrillic prompts to prove `prompt_utf8_bytes` counts strict UTF-8 bytes, not code points. For
a baseline arm, independently calculate:

```python
instruction_bytes = (
    b"" if arm.instruction is None else arm.instruction.encode("utf-8", errors="strict")
)
expected_bound = case_index[0].prompt_utf8_bytes + len(instruction_bytes) + 65_536
assert parent_plan[0].input_token_bound == expected_bound
```

Test baseline and nonbaseline arms and assert planning does not access or add an
`Arm.instruction_bytes` field. Add a spy around each identity helper and `PlanRowV1` construction;
with an oversized row late in the prospective Cartesian order, every spy must remain zero. This
proves the complete bound preflight finishes before any identity hash or row construction.

Create a one-row baseline fixture whose bound equals exactly 272,000 and assert it materializes.
Increase only the prompt by one ASCII byte and assert the `PlanningError.code` is exactly
`public_benchmark_input_bound_exceeded`. Require `validate_parent_plan` to return that same code for
an actually oversized captured reconstruction. Forge only `prompt_utf8_bytes` or
`input_token_bound` in an otherwise nonoversized canonical row and require the existing
`plan_mismatch` code rather than the oversize code.

Run:

```bash
uv run pytest tests/capsule/test_planning.py::test_parent_plan_ids_are_stable_without_run_identity tests/capsule/test_planning.py::test_parent_identity_preimages_are_exact tests/capsule/test_planning.py::test_case_index_and_plan_bind_default_service_tier_and_input_bound tests/capsule/test_planning.py::test_complete_input_bound_preflight_precedes_identity_and_rows tests/capsule/test_record_models.py -q
```

Expected: FAIL because `materialize_parent_plan`, both bound fields, and the standard-tier rejection
are absent and current IDs require `run_id`.

- [ ] **Step 3: Implement the stable parent plan API**

Replace the three `run_id` preimages with the exact domain-separated keyword-only helpers above.
Rename `materialize_plan` to `materialize_parent_plan` and `validate_plan` to
`validate_parent_plan`; both use only their stable signatures and class-bound validate
`parent_manifest_sha256` as lowercase SHA-256. Delete the old function names and old identity
signatures without aliases, wrappers, or compatibility shims.

Add `prompt_utf8_bytes` and `input_token_bound` to the strict record models shown in the stable
interface. `materialize_case_index` computes the former while hashing the exact prompt. Validate
each arm and derive its instruction bytes only as
`b"" if arm.instruction is None else arm.instruction.encode("utf-8", errors="strict")`; do not read
`arm.instruction_bytes`. Before calling `request_config_sha256`, `block_id`, `pairing_unit_id`, or
`plan_item_id`, and before constructing any `PlanRowV1`, `materialize_parent_plan` computes and
retains the conservative bound for every prospective case/repetition/arm row. If any exceeds
`OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS`, raise
`PlanningError("public_benchmark_input_bound_exceeded")` with zero identity hashes and zero rows.
Only after the complete preflight succeeds may it construct identities/rows using the precomputed
bounds. `validate_parent_plan` independently repeats this full derivation; it never trusts a
supplied bound, uses `public_benchmark_input_bound_exceeded` for a genuinely oversized
reconstruction, and uses `plan_mismatch` for a forged bound/identity when the reconstructed input is
within the maximum.

Keep the seeded arm-order algorithm, row ordering, case/instruction hashes, and output-token exposure
limits unchanged. Do not add `run_id` or `campaign_id` to a parent row. The cache/literal-default-tier
policy and bound algorithm/version are already part of `request_config_sha256`; every row binds that
digest, and the row-specific bound is also part of the plan-item preimage.

- [ ] **Step 4: Thread the manifest digest through preparation and verification**

In `prepare.py`, pass the already computed `manifest_sha256` to `materialize_parent_plan`. In
`verify.py`, pass `capsule.manifest_sha256` to `validate_parent_plan`. Update all direct test callers,
record payload builders, canonical key-order assertions, and independent goldens.

In `execution.py`, after recovering the verified captured case and arm but before constructing the
request, require the resolved manifest's literal default service tier, reconstruct that exact field,
recompute the conservative bound from the exact strings, and require equality with
`row.input_token_bound`. Then recompute `plan_item_id` with
`parent_manifest_sha256=context.capsule.manifest_sha256`, the verified row's `case_uid`,
`repetition`, `arm`, `instruction_sha256`, and `request_config_sha256`, plus the recomputed bound;
require exact equality with `row.plan_item_id` before constructing the request. Add execution tests
forging only the row bound, plan-item ID, instruction hash, or request-config hash,
omitting/altering the resolved tier, and using an oversized captured request; all must fail before
the provider fake records a call.

Add `test_two_preparations_have_distinct_runs_but_identical_parent_plans` to `tests/capsule/test_prepare.py`; prepare the same fake manifest twice into one results root and assert:

```python
assert first.run_id != second.run_id
assert (first.path / "plan.jsonl").read_bytes() == (second.path / "plan.jsonl").read_bytes()
```

- [ ] **Step 5: Run planning, preparation, verification, and resume regressions**

Run:

```bash
uv run pytest tests/capsule/test_record_models.py tests/capsule/test_planning.py tests/capsule/test_prepare.py tests/capsule/test_verify_prepared.py tests/capsule/test_execution.py tests/capsule/test_resume.py -q
```

Expected: PASS. Attempt IDs still differ between the two prepared runs because attempt identity remains run-bound.

- [ ] **Step 6: Commit stable parent identities**

```bash
git add src/laconian_eval/capsule/record_models.py src/laconian_eval/capsule/planning.py src/laconian_eval/capsule/prepare.py src/laconian_eval/capsule/verify.py src/laconian_eval/capsule/execution.py tests/capsule/test_record_models.py tests/capsule/test_planning.py tests/capsule/test_prepare.py tests/capsule/test_verify_prepared.py tests/capsule/test_execution.py tests/capsule_helpers.py
git commit -m "feat: bind default-tier parent plan exposure"
```

### Task 5: Define ShardPlanV1 and prove the exact 36-by-40 projection

**Files:**
- Create: `src/laconian_eval/capsule/sharding.py`
- Modify: `src/laconian_eval/capsule/schema.py`
- Modify: `src/laconian_eval/capsule/record_models.py`
- Modify: `src/laconian_eval/capsule/prepare.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `tests/capsule_helpers.py`
- Create: `tests/capsule/test_sharding.py`
- Modify: `tests/capsule/test_record_models.py`
- Modify: `tests/capsule/test_prepare.py`
- Modify: `tests/capsule/test_verify_prepared.py`

- [ ] **Step 1: RED-test strict ShardPlanV1 shape and self-hash**

Create `tests/capsule/test_sharding.py` with `test_shard_plan_round_trips_exact_shape`. Build a complete 40-ID payload and assert the serialized key order shown in the stable interface. Parameterize rejection of:

```text
unknown field
uppercase or short digest
blank model_id
missing one of the exact three public model IDs
extra or substitute model ID
duplicate ordered_plan_item_ids
row_count unequal to tuple length
unknown derivation_version
forged shard_plan_sha256
bool row_count
```

Independently compute the expected self-hash from the exact preimage above.

Also freeze `test_shard_plan_file_bytes_are_canonical_json_plus_one_lf`. Require exact bytes
`canonical_json(shard.model_dump(mode="json")) + b"\n"`; the reader strips exactly one LF, strictly
parses/class-bound revalidates, and re-encodes to byte equality. Reject no LF, two LFs, CRLF,
leading/trailing whitespace, alternate key order/number/string escaping, unknown content, and a
forged self-hash with `plan_mismatch`.

- [ ] **Step 2: Run the model RED gate**

Run:

```bash
uv run pytest tests/capsule/test_sharding.py::test_shard_plan_round_trips_exact_shape tests/capsule/test_sharding.py::test_shard_plan_file_bytes_are_canonical_json_plus_one_lf -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'laconian_eval.capsule.sharding'`.

- [ ] **Step 3: Implement strict shard schema and pure projection**

Create `sharding.py` with `ShardPlanError`, `ShardPlanV1`, `project_shard_plans`, `materialize_shard_projection`, and `validate_public_generation_partition` using the stable interfaces.

`project_shard_plans` must:

1. class-bound revalidate the resolved manifest, case index, captured arms, and every parent row;
2. verify the parent plan using `validate_parent_plan(parent_plan, parent_manifest_sha256=parent_manifest_sha256, resolved_manifest=resolved_manifest, case_index=case_index, captured_arms=captured_arms)` before grouping;
3. compute `parent_plan_sha256 = sha256_bytes(plan_jsonl(parent_plan))`;
4. order scenario groups by the first parent ordinal at which each scenario appears;
5. retain within-group parent order exactly;
6. require each ordered ID to occur once in the parent plan; and
7. build each self-hash from the exact canonical preimage.

`materialize_shard_projection` class-bound revalidates the shard and every parent row, recomputes and
requires the exact `parent_plan_sha256`, requires unique ordered IDs with exact parent membership,
and requires every selected row to have the one `scenario_uid` named by the shard. It creates local
rows with only `ordinal` changed to `0..row_count-1`; independently compare every other serialized
field to its parent.

`validate_public_generation_partition` has exactly the keyword-only signature in the stable
interface. It requires exact length three for the aligned manifests, hashes, case indexes, captured-
arm sequences, and parent plans; class-bound revalidates every member and all shards; requires model
order exactly Sol, Terra, Luna; and requires three distinct lowercase parent-manifest hashes. For
each aligned tuple it calls
`validate_parent_plan(parent_plan, parent_manifest_sha256=parent_manifest_sha256,
resolved_manifest=resolved_manifest, case_index=case_index, captured_arms=captured_arms)` and requires
the manifest's OpenAI provider/model and every row to agree with its aligned model/hash. It requires
every shard's `campaign_id` to equal the exact caller value, exactly three parents of 480 rows, 36
shards of 40 rows, 12 shards per parent/model, and disjoint IDs within and across parents. The one
global shard tuple must equal caller parent order followed by each parent's 12 first-appearance
scenario groups; set-equivalent reorderings fail. Cross-model IDs must also be distinct because
requested model participates in `request_config_sha256`.

- [ ] **Step 4: RED-test the public partition from three native-v2 models**

Build three resolved manifests from `resolved_manifest_v2_payload()` with models `gpt-5.6-sol`,
`gpt-5.6-terra`, and `gpt-5.6-luna`, all four arms, five repetitions, 24 case-index rows,
`reasoning_effort="medium"`, `text_verbosity="medium"`, `reasoning_mode="omitted"`,
`prompt_cache_mode="explicit"`, `prompt_cache_ttl="30m"`, `service_tier="default"`,
`max_output_tokens=1024`, and null temperature. Materialize 480 parent rows per model, assert every
row's request-config identity binds the literal default tier, assert every row's input-token bound is
at most 272,000, and project all shards.

Assert:

```python
assert [len(parent) for parent in parents] == [480, 480, 480]
assert len(shards) == 36
assert {shard.row_count for shard in shards} == {40}
assert sum(shard.row_count for shard in shards) == 1440
assert {shard.model_id for shard in shards} == {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
```

Delete each requested model, add a fourth, and substitute any nonliteral model independently;
`validate_public_generation_partition` must reject every case before hashing or projection.

For every shard projection assert exactly two locales, four arms, five repetitions, one scenario UID, and no duplicate `(case_uid, repetition, arm)` key. Then call `validate_public_generation_partition`.

Call it with the exact aligned `campaign_id`, `(Sol, Terra, Luna)` resolved manifests, their three
distinct parent-manifest hashes, case indexes, captured-arm sequences, parent plans, and the globally
ordered shard tuple. Add one mutation per binding: any aligned sequence length other than three;
wrong/blank campaign ID; any shard campaign mismatch; swapped manifest, parent hash, case index,
captured arms, parent plan, or shard-parent segment; duplicate parent hash; wrong provider or model;
model order other than Sol/Terra/Luna; forged/non-revalidated parent; and a globally reordered shard
that preserves set coverage. Spy on `validate_parent_plan` and require one exact aligned call per
parent. Every mutation must fail before projection is trusted.

Run:

```bash
uv run pytest tests/capsule/test_sharding.py::test_three_model_public_partition_is_exactly_36_by_40 -q
```

Expected: FAIL until `validate_public_generation_partition` implements the complete coverage contract.

- [ ] **Step 5: RED-test captured shard preparation rather than selective execution**

Add strict planning input roles to the test payloads:

```python
{
    "role": "parent_plan",
    "role_ordinal": 0,
    "logical_locator": "preflight.parent_plan",
    "capsule_path": "inputs/planning/parent-plan.jsonl",
    "byte_length": len(parent_plan_bytes),
    "sha256": sha256_bytes(parent_plan_bytes),
    "dataset_id": None,
    "binding_id": None,
}

{
    "role": "shard_plan",
    "role_ordinal": 0,
    "logical_locator": "preflight.shard_plan",
    "capsule_path": "inputs/planning/shard-plan.json",
    "byte_length": len(shard_plan_bytes),
    "sha256": sha256_bytes(shard_plan_bytes),
    "dataset_id": None,
    "binding_id": None,
}
```

Add `test_prepare_shard_capsule_captures_parent_and_exact_projection` to `tests/capsule/test_prepare.py`. Write a parent plan and one shard plan to source files, call `prepare_shard_capsule`, and assert the two captured bytes are exact, `plan.jsonl` has 40 local ordinals, and every plan item ID equals the shard's ordered IDs.

Add rejection cases for a modified parent byte, modified shard byte, wrong model, wrong manifest hash, wrong parent hash, nonmember ID, reordered ID, 39 rows, 41 rows, and scenario mismatch.

Add `test_planning_input_paths_use_invocation_cwd_and_no_follow_limits`. Exercise one absolute pair
and one relative pair resolved only against `PrepareRequest.invocation_cwd`, with the files outside
the manifest/input root; both must capture successfully. A relative path that exists only under the
input root must not be found. Reject symlink/FIFO/directory, unsafe component, no-follow/open/read
failure with `planning_input_read_failed`; reject a parent larger than
`RESOURCE_LIMITS_V1.captured_input_total_bytes` with `parent_plan_limit` and a shard larger than
`RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes` with `shard_plan_limit`. No test follows a link or
falls back to the manifest root.

Add direct `materialize_shard_projection` mutations for parent-plan hash, duplicate/missing/foreign
ID, scenario mismatch, forged nested row, and any non-ordinal output change. Every canonical,
content, hash, self-hash, or projection mutation must surface as `plan_mismatch` at the capsule
boundary.

- [ ] **Step 6: Implement planning-input capture and projection verification**

Extend `InputRole` with `parent_plan` and `shard_plan`. In `InputFileRecordV1.validate_role_contract`, require the exact ordinal, locator, path, and null ownership fields shown above. Add `inputs/planning` to the exact tree policy used by current verification.

Resolve each planning source path as itself when absolute or against
`request.prepare.invocation_cwd` when relative, independently of the authored manifest/input root.
Bounded-read both as no-follow regular files: parent bytes use
`RESOURCE_LIMITS_V1.captured_input_total_bytes`/`parent_plan_limit`, shard bytes use
`RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes`/`shard_plan_limit`, and unsafe/open/read failures map
only to `planning_input_read_failed`. Do not broaden the manifest-root capture grammar.

Implement `PrepareShardRequest` and `prepare_shard_capsule` as a common preparation path that:

1. captures and resolves the manifest normally;
2. recomputes the complete stable parent plan from captured cases and arms;
3. bounded-reads both caller-supplied planning files without following links;
4. requires canonical parent JSONL bytes equal the recomputation;
5. requires shard bytes exactly `canonical_json(shard.model_dump(mode="json")) + b"\n"`, strips
   exactly one LF, strictly parses/class-bound revalidates, re-encodes to byte equality, and validates
   its self-hash;
6. materializes only the exact projection into `plan.jsonl`;
7. adds both planning inputs to `inputs/index.json`; and
8. preserves the existing random capsule run/operation IDs and atomic preparation flow.

In `verify.py`, select full-parent validation when neither planning input exists and shard validation when both exist. One missing planning input is `missing_path`; an unexpected planning path or role is `unexpected_path`; any canonical/content/hash/self-hash/projection mismatch is `plan_mismatch`. Task 5 extends the current verifier's exact path grammar with `inputs/planning` and its two files. Do not create or modify `tree_policy.py` in Task 5; Task 6 extracts this already-extended grammar unchanged.

- [ ] **Step 7: Run shard, preparation, and verifier regressions**

Run:

```bash
uv run pytest tests/capsule/test_sharding.py tests/capsule/test_record_models.py tests/capsule/test_prepare.py tests/capsule/test_verify_prepared.py tests/capsule/test_execution.py tests/capsule/test_resume.py -q
```

Expected: PASS. Execution sees exactly 40 plan rows for a shard capsule and cannot reach any of the other 440 parent rows.

- [ ] **Step 8: Commit immutable scenario projections**

```bash
git add src/laconian_eval/capsule/sharding.py src/laconian_eval/capsule/schema.py src/laconian_eval/capsule/record_models.py src/laconian_eval/capsule/prepare.py src/laconian_eval/capsule/verify.py tests/capsule_helpers.py tests/capsule/test_sharding.py tests/capsule/test_record_models.py tests/capsule/test_prepare.py tests/capsule/test_verify_prepared.py
git commit -m "feat: add immutable scenario shard plans"
```

### Task 6: Extract one capsule tree policy and derive strict SealV1 bytes

**Files:**
- Create: `src/laconian_eval/capsule/tree_policy.py`
- Create: `src/laconian_eval/capsule/seal_models.py`
- Modify: `src/laconian_eval/capsule/schema.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Create: `tests/capsule/test_tree_policy.py`
- Create: `tests/capsule/test_seal_models.py`
- Modify: `tests/capsule_helpers.py`

- [ ] **Step 1: RED-test the shared tree grammar**

Create `tests/capsule/test_tree_policy.py` and import:

```python
from laconian_eval.capsule.tree_policy import capsule_path_kind
```

Assert these exact classifications:

```python
@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (".laconian.lock", "file"),
        ("capsule.json", "file"),
        ("inputs/planning", "directory"),
        ("inputs/planning/parent-plan.jsonl", "file"),
        ("inputs/planning/shard-plan.json", "file"),
        ("seal.json", "file"),
        (".seal.123e4567-e89b-42d3-a456-426614174000.tmp", "file"),
        ("inputs/cases/000.yaml", "file"),
        ("inputs/protocols/000-0123456789abcdef.bin", "file"),
        ("inputs/software/runner/laconian_eval/providers/openai.py", "file"),
    ],
)
def test_capsule_path_kind_accepts_exact_owned_grammar(path: str, kind: str) -> None:
    assert capsule_path_kind(path) == kind
```

Reject with `None`: empty path, root marker `/`, absolute path, backslash, NUL, non-NFC spelling, empty component, dot component, parent component, malformed ordinal, malformed seal UUID, unknown top-level path, and a file with a child. Verifier and archive tests separately reject a header or filesystem kind that differs from this function's returned kind.

Run:

```bash
uv run pytest tests/capsule/test_tree_policy.py -q
```

Expected: FAIL during collection because `tree_policy.py` does not exist.

- [ ] **Step 2: Move the exact path grammar out of verify.py**

Create `tree_policy.py` with one public pure function:

```python
MemberKind = Literal["file", "directory"]


def capsule_path_kind(path: str) -> MemberKind | None:
    """Classify one normalized possible capsule member without reading the filesystem."""
```

Move the fixed file/directory sets and the case, protocol, runner-source, and seal-temp regular expressions from `verify.py`. Preserve unchanged the two planning files and `inputs/planning` that Task 5 already added to that grammar; add `seal.json` and the strict lowercase canonical UUID4 seal temporary. Validate the whole relative POSIX path before applying patterns. Keep semantic required-member calculation in `verify.py`; this function answers only whether a member can ever belong to a capsule and which path type it may have.

Replace `_file_allowed` and `_directory_allowed` calls in `verify.py` with this shared classifier. Run:

```bash
uv run pytest tests/capsule/test_tree_policy.py tests/capsule/test_verify_prepared.py -q
```

Expected: PASS with no change to current unsealed verification outcomes.

- [ ] **Step 3: RED-test the complete strict seal schema**

Create `tests/capsule/test_seal_models.py` with a valid payload containing the exact field order from Section 17:

```python
{
    "seal_schema_version": "1",
    "run_id": UUID_A,
    "seal_transaction_id": UUID_B,
    "generation_status": "complete",
    "structural_integrity": "valid",
    "missing_plan_item_ids": [],
    "operational_blocker_codes": [],
    "never_started_detail": None,
    "disclosures": {
        "source_state": "clean",
        "returned_models": ["gpt-5.6-sol-2026-08-30"],
        "usage_availability_counts": {
            "complete": 40,
            "partial": 0,
            "unavailable": 0,
        },
        "redacted_output_attempt_count": 0,
        "redacted_output_replacement_count": 0,
        "dataset_ids": ["response-public-v1"],
        "protocol_binding_ids": [],
    },
    "final_event_sequence": 83,
    "raw_attempt_count": 40,
    "sealed_at": "2026-08-30T12:34:56.123456Z",
    "files": [
        {"path": "capsule.json", "byte_length": 321, "sha256": SHA_A},
        {"path": "events.jsonl", "byte_length": 654, "sha256": SHA_B},
    ],
}
```

Assert frozen/strict/extra-forbid behavior, canonical key order, UTF-8 sorting, unique arrays, exact blocker order, usage-count sum, complete/incomplete relations, never-started detail relation, inventory exclusions, canonical timestamp, UUID4 boundaries, and class-bound rejection of `model_construct` for nested models.

The exact incomplete matrix is:

```text
never_started          -> nonempty missing IDs, sole blocker, nonnull detail
interrupted            -> nonempty missing IDs, sole blocker, null detail
ambiguous_inflight     -> nonempty missing IDs, sole blocker, null detail
authentication_stopped -> nonempty missing IDs, sole blocker, null detail
```

Run:

```bash
uv run pytest tests/capsule/test_seal_models.py::test_seal_v1_round_trips_exact_shape -q
```

Expected: FAIL during collection because `seal_models.py` does not exist.

- [ ] **Step 4: Implement SealV1 structural models**

Define these exact models in `seal_models.py`:

```python
class SealFileV1(CapsuleModel):
    path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class SealUsageAvailabilityCountsV1(CapsuleModel):
    complete: StrictNonNegativeInt
    partial: StrictNonNegativeInt
    unavailable: StrictNonNegativeInt


class SealDisclosuresV1(CapsuleModel):
    source_state: Literal["clean", "dirty", "unbound", "unavailable"]
    returned_models: tuple[BoundedNonBlankString, ...]
    usage_availability_counts: SealUsageAvailabilityCountsV1
    redacted_output_attempt_count: StrictNonNegativeInt
    redacted_output_replacement_count: StrictNonNegativeInt
    dataset_ids: tuple[BoundedNonBlankString, ...]
    protocol_binding_ids: tuple[BoundedNonBlankString, ...]


class SealV1(CapsuleModel):
    seal_schema_version: Literal["1"]
    run_id: UUID4
    seal_transaction_id: UUID4
    generation_status: Literal["complete", "incomplete"]
    structural_integrity: Literal["valid"]
    missing_plan_item_ids: tuple[Sha256, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]
    never_started_detail: (
        Literal[
            "credential_unavailable",
            "provider_unavailable",
            "operator_abandoned",
        ]
        | None
    )
    disclosures: SealDisclosuresV1
    final_event_sequence: StrictNonNegativeInt
    raw_attempt_count: StrictNonNegativeInt
    sealed_at: CanonicalTimestamp
    files: tuple[SealFileV1, ...] = Field(min_length=1)
```

Use the existing fixed-order and UTF-8-sorted-unique helpers. Reject `.laconian.lock`, `seal.json`, and every `.seal.<uuid>.tmp` inventory path.

- [ ] **Step 5: RED-test deterministic derivation from validated history**

Build complete, prepared-never-started, interrupted, ambiguous, and authentication histories with existing capsule history helpers. Add `test_derive_seal_v1_is_a_total_projection_of_validated_history` and assert:

```text
seal transaction/status/time/final sequence -> sole seal_requested event
missing IDs/blocker                          -> lifecycle projection
raw_attempt_count                            -> committed raw rows
usage counts                                 -> every committed raw row
returned_models                              -> distinct successful response_model values
redaction counts                             -> raw disclosure fields
dataset/protocol IDs                         -> resolved manifest declarations
source_state                                 -> environment checkout/git state table
files                                        -> exact supplied preseal inventory
```

Call `derive_seal_v1` twice with equal validated values and assert byte-identical `seal_bytes` and equal `capsule_sha256`.

Run:

```bash
uv run pytest tests/capsule/test_seal_models.py::test_derive_seal_v1_is_a_total_projection_of_validated_history -q
```

Expected: FAIL because `derive_seal_v1` is absent.

- [ ] **Step 6: Implement derivation and content-free failures**

Implement `SealModelError(code)` with literal message `capsule seal rejected`. Class-bound revalidate every input before reading fields. Require the supplied seal request to be the validated history's sole seal request and require its expected status to match lifecycle completeness.

Derive source state with this exact table:

```python
if environment.checkout_binding == "unbound":
    source_state = "unbound"
elif environment.checkout_binding == "bound" and environment.git_state in {"clean", "dirty"}:
    source_state = environment.git_state
else:
    source_state = "unavailable"
```

Sort every set-like array by exact UTF-8 bytes. Calculate the seal hash only from exact canonical seal bytes and never store it inside `SealV1`.

Run:

```bash
uv run pytest tests/capsule/test_tree_policy.py tests/capsule/test_seal_models.py tests/capsule/test_verify_prepared.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit tree policy and seal derivation**

```bash
git add src/laconian_eval/capsule/tree_policy.py src/laconian_eval/capsule/seal_models.py src/laconian_eval/capsule/schema.py src/laconian_eval/capsule/verify.py tests/capsule/test_tree_policy.py tests/capsule/test_seal_models.py tests/capsule_helpers.py
git commit -m "feat: derive strict capsule seals"
```

### Task 7: Publish seals atomically and expose `laconian finalize`

**Files:**
- Create: `src/laconian_eval/capsule/finalize.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `src/laconian_eval/cli.py`
- Create: `tests/capsule/test_finalize.py`
- Create: `tests/capsule/test_cli_finalize.py`

- [ ] **Step 1: RED-test complete versus explicitly incomplete finalization**

Create `tests/capsule/test_finalize.py` with:

```python
def test_finalize_complete_capsule_publishes_one_deterministic_seal(complete_capsule: Path) -> None:
    result = finalize_capsule(complete_capsule)
    seal = SealV1.model_validate_json((complete_capsule / "seal.json").read_bytes())
    assert result.state == "SEALED_COMPLETE"
    assert result.capsule_sha256 == sha256_bytes((complete_capsule / "seal.json").read_bytes())
    assert seal.generation_status == "complete"
    assert seal.missing_plan_item_ids == ()
    assert seal.operational_blocker_codes == ()


def test_finalize_incomplete_requires_explicit_flag(prepared_capsule: Path) -> None:
    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(prepared_capsule)
    assert caught.value.code == "incomplete_requires_flag"
    assert not (prepared_capsule / "seal.json").exists()

    result = finalize_capsule(prepared_capsule, seal_incomplete=True)
    assert result.state == "SEALED_BLOCKED"
```

Parameterize incomplete state expectations for never-started, interrupted, ambiguous, and authentication-stopped capsules. Assert finalization never creates an attempt or converts a missing plan item into a terminal outcome.

- [ ] **Step 2: Run the finalizer RED gate**

Run:

```bash
uv run pytest tests/capsule/test_finalize.py::test_finalize_complete_capsule_publishes_one_deterministic_seal tests/capsule/test_finalize.py::test_finalize_incomplete_requires_explicit_flag -q
```

Expected: FAIL during collection because `finalize.py` does not exist.

- [ ] **Step 3: Implement lock-owned history normalization and seal request**

Create `FinalizationError(code)` with literal message `capsule finalization rejected`, `FinalizeResultV1`, public `finalize_capsule`, and an internal `_finalize_capsule` accepting a target-known callback plus injected POSIX crash seams for tests.

Under one exclusive `.laconian.lock` ownership:

1. descriptor-verify the capsule with journal tails reported;
2. apply the existing pure recovery plan so derivable finish, stop, ambiguity, and completion markers are fsynced in causal order;
3. reverify the exact normalized history;
4. reject unrequested incompleteness unless `seal_incomplete=True`;
5. append and fsync exactly one `seal_requested` event when absent;
6. reuse the committed transaction ID, expected status, and event timestamp when the request already exists;
7. forbid every execution event after the request; and
8. re-snapshot all preseal files by descriptor before deriving bytes.

Generate a new UUID4 seal transaction distinct from run ID, invocation operation ID, and every execution-session ID. The seal event operation ID is the invocation operation ID and its execution session is null.

- [ ] **Step 4: RED-test every atomic publication crash boundary**

Inject failures at these exact points:

```text
after seal_requested fsync
after temporary exclusive creation
during temporary write
after temporary file fsync
after link_noreplace publishes seal.json
after temporary unlink
during capsule-directory fsync
```

For each failure, retry `finalize_capsule` and assert one committed seal request, byte-identical derived seal bytes, no overwritten path, and at most the matching `.seal.<transaction>.tmp` residue.

Add rejection tests for a mismatching temporary, a second temporary, wrong transaction name, existing nonregular `seal.json`, existing different seal bytes, and a same-name seal inode replacement. Every rejection preserves all evidence and performs no cleanup.

Run:

```bash
uv run pytest tests/capsule/test_finalize.py -k 'crash or residue or mismatch' -q
```

Expected: FAIL until the no-replace publication and retry state table are implemented.

- [ ] **Step 5: Implement exact temporary/link/fsync behavior**

Use the sole name `.seal.<seal_transaction_id>.tmp`. Open it with `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, mode `0600`; write all canonical bytes; fsync the file; recheck descriptor/path identity; call `PosixOps.link_noreplace(root_fd, temporary_name, root_fd, "seal.json")`; unlink the exact temporary by descriptor-validated name; fsync the capsule directory.

On retry without `seal.json`, remove and recreate only a descriptor-validated mismatching temporary owned by the committed transaction. On retry with `seal.json`, require exact bytes; remove only an exact matching temporary, then fsync. Never overwrite `seal.json` and never accept a second seal request.

- [ ] **Step 6: RED/GREEN the public CLI contract**

Add parser coverage for:

```bash
laconian finalize <run-directory>
laconian finalize <run-directory> --seal-incomplete
```

`tests/capsule/test_cli_finalize.py` must assert the absolute capsule path appears exactly once on stdout once the root/capsule identity is known; diagnostics appear only on stderr; complete and explicitly incomplete success exit 0; an operational post-publication fsync failure exits 1; usage, integrity, busy lock, unsupported local mutation filesystem, collision, and seal mismatch exit 2.

Run:

```bash
uv run pytest tests/capsule/test_cli_finalize.py -q
```

Expected RED: argparse exits 2 with `invalid choice: 'finalize'`.

Add the parser, `_finalize` dispatcher, exact exception mapping, and one-shot announcement callback. Then run:

```bash
uv run pytest tests/capsule/test_finalize.py tests/capsule/test_cli_finalize.py tests/capsule/test_cli_resume.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit public finalization**

```bash
git add src/laconian_eval/capsule/finalize.py src/laconian_eval/capsule/verify.py src/laconian_eval/cli.py tests/capsule/test_finalize.py tests/capsule/test_cli_finalize.py
git commit -m "feat: finalize generation capsules"
```

### Task 8: Verify sealed capsules without requiring a transport lock

**Files:**
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `src/laconian_eval/capsule/record_models.py`
- Modify: `tests/capsule/test_verify_prepared.py`
- Create: `tests/capsule/test_verify_sealed.py`
- Modify: `tests/capsule/test_cli_finalize.py`

- [ ] **Step 1: RED-test sealed-state selection and capsule hash**

Create `tests/capsule/test_verify_sealed.py` and finalize one complete and one incomplete capsule. Assert:

```python
complete = verify_capsule(complete_path, mode=VerificationMode.PREPARED)
blocked = verify_capsule(blocked_path, mode=VerificationMode.PREPARED)
assert complete.status == "valid"
assert complete.state == "SEALED_COMPLETE"
assert complete.capsule_sha256 == sha256_bytes((complete_path / "seal.json").read_bytes())
assert blocked.status == "valid"
assert blocked.state == "SEALED_BLOCKED"
assert blocked.capsule_sha256 == sha256_bytes((blocked_path / "seal.json").read_bytes())
```

Run:

```bash
uv run pytest tests/capsule/test_verify_sealed.py::test_seal_presence_selects_sealed_verification -q
```

Expected: FAIL with `status=invalid`, `first_error.code=unexpected_path`, `first_error.path=seal.json`.

- [ ] **Step 2: RED-test lockless verification before filesystem classification**

Copy a sealed capsule, remove only `.laconian.lock`, and inject a filesystem classifier that raises `UnsupportedFilesystemError`. Assert verification remains valid, state/hash are unchanged, and warnings equal the existing warning order with `lock_file_omitted_for_sealed_transport` included once.

Create the same lockless copy without `seal.json`; assert it is invalid with `missing_path` for `.laconian.lock`. Corrupt `seal.json` while leaving all preseal bytes valid; assert the verifier returns `seal_mismatch` and never falls back to mutable verification.

Run:

```bash
uv run pytest tests/capsule/test_verify_sealed.py::test_lockless_sealed_transport_bypasses_local_filesystem_requirement tests/capsule/test_verify_sealed.py::test_invalid_seal_never_falls_back_to_unsealed_verification -q
```

Expected: FAIL because public verification currently classifies the filesystem and opens the lock before inspecting seal presence.

- [ ] **Step 3: Implement the sealed verification branch**

After opening/rechecking the public root descriptors, inventory only enough top-level metadata to determine whether `seal.json` exists as a regular no-follow file. Presence selects the sealed branch before filesystem classification or lock acquisition.

The sealed branch must:

1. build a stable descriptor inventory using the shared tree policy;
2. parse strict canonical `SealV1`;
3. allow `.laconian.lock` to be present or absent and exclude it from the seal inventory;
4. require every preseal file path, byte length, and SHA-256 to equal the sorted seal inventory;
5. reject an extra, missing, duplicated, nonregular, or renamed member;
6. revalidate manifest, case index, full-parent or shard plan, environment, journal grammar, lifecycle, disclosures, and all derived seal fields;
7. derive `SEALED_COMPLETE` or `SEALED_BLOCKED` only from validated seal contents;
8. set `capsule_sha256` to SHA-256 of exact canonical `seal.json` bytes; and
9. recheck root/parent identities before returning.

Keep mutable verification unchanged: supported local filesystem, shared lock, and `.laconian.lock` remain mandatory.

- [ ] **Step 4: RED/GREEN the sole matching seal temporary rule**

Test four sealed trees:

```text
no temporary                                      -> valid
one same-byte matching-transaction temporary      -> valid
one different-byte matching-transaction temporary -> seal_mismatch
wrong transaction or second temporary             -> seal_mismatch
```

The temporary is not part of `SealV1.files`. Verification is read-only and never removes it. Only idempotent `finalize` may clean the exact same-byte residue under an exclusive local lock.

- [ ] **Step 5: Prove `--require sealed` and immutable behavior**

Snapshot the entire capsule parent tree before and after direct verification and CLI verification. Assert byte content, names, modes, sizes, mtimes, and inode identities remain unchanged.

Run:

```bash
uv run pytest tests/capsule/test_verify_sealed.py tests/capsule/test_verify_prepared.py tests/capsule/test_cli_finalize.py tests/capsule/test_cli_plan.py tests/capsule/test_cli_resume.py -q
```

Expected: PASS. `laconian verify <sealed> --require sealed` exits 0; the same requirement on a valid unsealed capsule prints its unchanged valid object and exits 2.

- [ ] **Step 6: Commit lockless sealed verification**

```bash
git add src/laconian_eval/capsule/verify.py src/laconian_eval/capsule/record_models.py tests/capsule/test_verify_prepared.py tests/capsule/test_verify_sealed.py tests/capsule/test_cli_finalize.py
git commit -m "feat: verify sealed capsule transport"
```

### Task 9: Write and load a seal-bound deterministic scored sidecar

**Files:**
- Create: `src/laconian_eval/capsule/scorable.py`
- Create: `src/laconian_eval/capsule/sidecars.py`
- Modify: `src/laconian_eval/scoring.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `tests/test_public_contract.py`
- Create: `tests/capsule/test_scorable.py`
- Create: `tests/capsule/test_sidecars.py`
- Modify: `tests/capsule_helpers.py`

- [ ] **Step 1: RED-test exact ScoredAttemptV2 identity binding**

Create `tests/capsule/test_scorable.py` with one valid successful terminal `RawAttemptV2`, its exact `PlanRowV1`, and its captured `ResponseCase`. Construct the `ScoredAttemptV2` shape from the stable interface and assert strict/frozen/extra-forbid behavior plus these exact equalities:

```python
assert scored.ordinal == plan.ordinal
assert scored.plan_item_id == plan.plan_item_id == raw.plan_item_id
assert scored.attempt_id == raw.attempt_id
assert scored.raw_attempt_sha256 == sha256_bytes(raw_attempt_bytes(raw))
assert scored.case_uid == plan.case_uid == raw.case_uid
assert scored.case_definition_sha256 == plan.case_definition_sha256
assert scored.case_definition_sha256 == raw.case_definition_sha256
assert scored.response_id == raw.response_id
assert scored.terminal_reason == raw.terminal_reason
assert scored.hard_pass == (
    raw.terminal_reason == "success" and all(check.passed for check in scored.checks)
)
```

Forge each duplicated field independently and assert model rejection. Reject a nonterminal raw row, null terminal reason, authentication/ambiguity terminal reason, a success without response ID/output, a provider failure marked hard-pass, and a failed check with `hard_pass=True`.

- [ ] **Step 2: RED-test deterministic terminal projection in plan order**

Build a 40-row shard plan whose rows refer to exactly two captured localized cases keyed by case UID, plus a raw ledger containing one initial retry row before one later terminal row. Shuffle the raw input sequence and call:

```python
scored = project_scored_attempts(
    plan=plan,
    raw_attempts=raw_rows,
    cases_by_uid=cases_by_uid,
)
```

Assert exactly 40 results in plan ordinal order, exactly one terminal row per plan item, the terminal retry rather than its nonterminal predecessor, and deterministic check order. Parameterize rejection of missing, duplicate, extra, nonterminal-only, wrong case UID, wrong case definition hash, wrong prompt hash, wrong arm/repetition, and wrong request-config hash evidence.

Run:

```bash
uv run pytest tests/capsule/test_scorable.py -q
```

Expected: FAIL during collection because `scorable.py` does not exist.

- [ ] **Step 3: Expose one deterministic hard-check function and implement the projection**

In `scoring.py`, extract the existing nonblank, literal, JSON, YAML, and sentence checks behind this public pure function, then make legacy `score_attempt` call it:

```python
def deterministic_hard_checks(case: ResponseCase, output: str) -> tuple[CheckResult, ...]:
    return tuple(
        [
            *_nonblank_checks(output),
            *_literal_checks(case, output),
            *_json_checks(case, output),
            *_yaml_checks(case, output),
            *_sentence_checks(case, output),
        ]
    )
```

Create `HardCheckV2`, `ScoredAttemptV2`, `ScorableError(code)` with literal message `capsule scoring rejected`, and `project_scored_attempts`. Class-bound revalidate plan rows, raw rows, and response cases before joining. For a successful row, map only each existing check's `name` and `passed` into `HardCheckV2`; do not persist free-form legacy `detail`. For `provider_rejected` and `retry_exhausted`, emit an empty check tuple and `hard_pass=False`; terminal reason remains the exact reason evidence.

Require the plan ordinals to be `0..len(plan)-1`, all plan IDs unique, and the terminal raw join to be a bijection. Select terminal rows by `plan_item_id`; never choose the last physical row as an implicit rule and never fabricate a row for missing evidence.

Run:

```bash
uv run pytest tests/capsule/test_scorable.py tests/test_scoring.py -q
```

Expected: PASS with legacy score outputs unchanged.

- [ ] **Step 4: RED-test the canonical scored-sidecar model and self-hash**

Create `tests/capsule/test_sidecars.py`. Build a valid `ScoredCapsuleSidecarV2` and independently compute:

```python
expected = stable_digest(
    "laconian-scored-capsule-sidecar-v2",
    {
        "sidecar_schema_version": "2",
        "scoring_algorithm_version": "laconian-deterministic-hard-v2",
        "capsule_sha256": capsule_sha256,
        "manifest_sha256": manifest_sha256,
        "case_index_sha256": case_index_sha256,
        "plan_sha256": plan_sha256,
        "raw_sha256": raw_sha256,
        "ordered_plan_item_ids": ordered_plan_item_ids,
        "scored_attempts": [row.model_dump(mode="json") for row in scored_attempts],
    },
)
assert sidecar.sidecar_sha256 == expected
```

Require `ordered_plan_item_ids` and scored rows to have equal nonzero length and position-by-position IDs/ordinals. Reject unknown scoring version, wrong self-hash, reordered/duplicate/missing ID, reordered scored row, wrong capsule/manifest/case-index/plan/raw digest, unknown field, forged nested model, and any field carrying a later-stage judgment.

Run:

```bash
uv run pytest tests/capsule/test_sidecars.py::test_scored_sidecar_round_trips_and_self_hashes_exactly -q
```

Expected: FAIL during collection because `sidecars.py` does not exist.

- [ ] **Step 5: Add a descriptor-stable sealed evidence reader**

In `verify.py`, add an internal context manager used by sidecars and checkpoint packing:

```python
@contextmanager
def verified_sealed_capsule_source(path: Path) -> Iterator[VerifiedSealedCapsuleSourceV1]:
    """Yield exact parsed sealed evidence while retaining and rechecking root descriptors."""
```

`VerifiedSealedCapsuleSourceV1` is frozen/slotted and contains strict `VerifyResultV1`, `SealV1`, `CapsuleV1`, `ResolvedManifestV2`, exact manifest/case-index/plan/raw bytes, ordered `CaseIndexRowV1`, ordered `PlanRowV1`, committed `RawAttemptV2`, and captured `ResponseCase` objects keyed by their verified case UID. It succeeds only for `SEALED_COMPLETE` with nonnull capsule hash, rechecks every descriptor identity before exit, and never accepts caller-supplied case text or plan/raw objects.

- [ ] **Step 6: RED-test no-replace sidecar writing and verified loading**

Finalize one complete 40-row shard capsule, then run:

```python
sidecar_hash = write_scored_sidecar(capsule_path, sidecar_path)
evidence = load_verified_scored_capsule(capsule_path, sidecar_path)
```

Assert:

```python
assert evidence.capsule_sha256 == sha256_bytes((capsule_path / "seal.json").read_bytes())
seal_files = {item.path: item for item in evidence.seal.files}
assert evidence.manifest_sha256 == seal_files["manifest.json"].sha256
assert evidence.plan_sha256 == seal_files["plan.jsonl"].sha256
assert tuple(row.plan_item_id for row in evidence.plan) == tuple(
    row.plan_item_id for row in evidence.scored_attempts
)
assert set(evidence.cases_by_uid) == {row.case_uid for row in evidence.plan}
assert (
    sidecar_hash
    == ScoredCapsuleSidecarV2.model_validate_json(sidecar_path.read_bytes()).sidecar_sha256
)
```

Use an immutable mapping proxy for `cases_by_uid`. Reject an unsealed capsule, `SEALED_BLOCKED`, a nullable capsule hash, a sidecar symlink/FIFO, noncanonical sidecar JSON, output collision, and any one-byte change to seal, manifest, case input, case index, plan, raw journal, or sidecar. Snapshot both capsule and parent before/after loading and assert the loader is read-only.

Run:

```bash
uv run pytest tests/capsule/test_sidecars.py -k 'write or load or rejects' -q
```

Expected: FAIL until writer and loader recompute all joins from descriptor-verified sealed bytes.

- [ ] **Step 7: Implement the external sidecar writer and exact loader**

Under `verified_sealed_capsule_source`, derive terminal raw rows from validated history, call `project_scored_attempts`, construct the complete `ScoredCapsuleSidecarV2`, compute its self-hash, and canonicalize it. Write through an operation-owned same-parent temporary using `0600`, fsync, `link_noreplace`, temporary unlink, and parent fsync. Existing output always fails; no overwrite or content-based replacement is allowed.

`load_verified_scored_capsule` opens the sidecar through its parent descriptor with `O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`, enforces the static JSON byte/depth bounds, requires canonical bytes, recomputes the complete expected sidecar from the retained sealed source, and requires byte equality. Return `VerifiedScoredCapsuleV2` only after a final root/sidecar identity recheck. The return object contains no authority to mutate the capsule or sidecar.

As the final serialized Slice 1 owner of `tests/test_public_contract.py`, rebase after the earlier
corpus/provider edits, then add `test_slice1_final_capsule_public_names_are_stable`. Import from the
exact owning modules and pin both `__name__` and `__module__` for `SealV1`, `capsule_sha256`,
`FinalizeResultV1`, `finalize_capsule`, `ShardPlanV1`, `ScoredAttemptV2`,
`VerifiedScoredCapsuleV2`, and `load_verified_scored_capsule`. Assert the three functions are callable
and the five records are their exact class objects; do not add a capsule package-level re-export or
duplicate implementation merely to satisfy the test.

```python
from laconian_eval.capsule.finalize import FinalizeResultV1, finalize_capsule
from laconian_eval.capsule.scorable import ScoredAttemptV2
from laconian_eval.capsule.seal_models import SealV1, capsule_sha256
from laconian_eval.capsule.sharding import ShardPlanV1
from laconian_eval.capsule.sidecars import (
    VerifiedScoredCapsuleV2,
    load_verified_scored_capsule,
)

assert {
    value.__name__: value.__module__
    for value in (
        SealV1,
        capsule_sha256,
        FinalizeResultV1,
        finalize_capsule,
        ShardPlanV1,
        ScoredAttemptV2,
        VerifiedScoredCapsuleV2,
        load_verified_scored_capsule,
    )
} == {
    "SealV1": "laconian_eval.capsule.seal_models",
    "capsule_sha256": "laconian_eval.capsule.seal_models",
    "FinalizeResultV1": "laconian_eval.capsule.finalize",
    "finalize_capsule": "laconian_eval.capsule.finalize",
    "ShardPlanV1": "laconian_eval.capsule.sharding",
    "ScoredAttemptV2": "laconian_eval.capsule.scorable",
    "VerifiedScoredCapsuleV2": "laconian_eval.capsule.sidecars",
    "load_verified_scored_capsule": "laconian_eval.capsule.sidecars",
}
```

Run:

```bash
uv run pytest tests/test_public_contract.py tests/capsule/test_scorable.py tests/capsule/test_sidecars.py tests/capsule/test_verify_sealed.py tests/test_scoring.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit the sealed deterministic scoring boundary**

```bash
git add src/laconian_eval/capsule/scorable.py src/laconian_eval/capsule/sidecars.py src/laconian_eval/scoring.py src/laconian_eval/capsule/verify.py tests/test_public_contract.py tests/capsule/test_scorable.py tests/capsule/test_sidecars.py tests/capsule_helpers.py
git commit -m "feat: expose verified scored capsules"
```

### Task 10: Pack deterministic uncompressed USTAR checkpoints

**Files:**
- Modify: `src/laconian_eval/capsule/limits.py`
- Create: `src/laconian_eval/capsule/checkpoint.py`
- Modify: `src/laconian_eval/capsule/verify.py`
- Modify: `src/laconian_eval/capsule/filesystem.py`
- Modify: `tests/capsule/test_limits.py`
- Create: `tests/capsule/test_checkpoint.py`

- [ ] **Step 1: RED-test the exact checkpoint bounds**

Extend `ResourceLimitsV1` with these positive integer fields and exact defaults:

```python
checkpoint_archive_bytes: int = 9 * _GIB
checkpoint_members: int = 120_064
checkpoint_file_bytes: int = 8 * _GIB
checkpoint_aggregate_file_bytes: int = 8 * _GIB
checkpoint_path_depth: int = 64
checkpoint_restore_seconds: int = 300
```

In `tests/capsule/test_limits.py`, include all six in the complete field/default assertion, bool/nonpositive rejection matrix, and frozen/slotted checks.

Run:

```bash
uv run pytest tests/capsule/test_limits.py -q
```

Expected: FAIL because the six dataclass fields are absent.

- [ ] **Step 2: RED-test canonical USTAR bytes and sidecar**

Create `tests/capsule/test_checkpoint.py`. Prepare a deterministic small capsule, set distinct allowed
file modes, and include a nested directory archived as `0o555` with a regular child to prove packing
does not require owner-write mode. Construct this exact provenance, derive its required name, and call:

```python
provenance = CheckpointProvenanceV1(
    campaign_id="public-2026-08-30",
    model_id="gpt-5.6-sol",
    scenario_uid=SHA_B,
    batch_attempt_id=UUID(UUID_B),
    run_attempt=1,
)
archive_path = output_root / checkpoint_archive_name(provenance)
artifact = pack_checkpoint(capsule_path, archive_path, provenance=provenance)
```

Assert:

```python
assert archive_path.suffix == ".tar"
assert artifact.sidecar_path == Path(f"{archive_path}.sha256")
assert artifact.sha256 == sha256_bytes(archive_path.read_bytes())
assert artifact.byte_length == archive_path.stat().st_size
assert artifact.member_count > 0
assert artifact.sidecar_path.read_bytes() == (
    f"{artifact.sha256}  {archive_path.name}\n".encode("ascii")
)
```

Parse raw 512-byte headers in the test without production helpers. Assert USTAR magic/version, canonical UTF-8 ordering, directory-before-child order, `uid=gid=mtime=0`, empty owner/group names, exact preserved modes, regular/directory types only, zero data padding, and exactly two terminal zero blocks. Call pack twice at different destination names and assert archive bytes are identical.

- [ ] **Step 3: Run the packer RED gate**

Run:

```bash
uv run pytest tests/capsule/test_checkpoint.py::test_pack_checkpoint_writes_deterministic_uncompressed_ustar_and_sidecar -q
```

Expected: FAIL during collection because `checkpoint.py` does not exist.

- [ ] **Step 4: Expose one lock-owned descriptor verification boundary**

Add an internal context manager in `verify.py`:

```python
@contextmanager
def verified_checkpoint_source(path: Path) -> Iterator[VerifiedCheckpointSourceV1]:
    """Yield a stable verified root descriptor and exact inventory while retaining a shared lock."""
```

`VerifiedCheckpointSourceV1` is frozen/slotted and contains the borrowed root descriptor, strict `VerifyResultV1`, and an immutable UTF-8-sorted tuple of `(path, kind, mode, byte_length)` records. The context owns and closes the parent/root/lock descriptors exactly once. It requires `.laconian.lock` even for sealed source packing because the archive contract includes that file; transport-lock omission is accepted only when reading an already transported sealed capsule.

Recheck every descriptor/path identity immediately before and after streaming each member and recheck root/parent/lock identities before yielding completion.

- [ ] **Step 5: Implement a deterministic streaming USTAR writer**

Implement `CheckpointError(code)` with literal message `capsule checkpoint rejected`, strict `CheckpointProvenanceV1`, `checkpoint_archive_name`, `CheckpointArtifactV1`, and `pack_checkpoint`. Class-bound revalidate provenance, require its safe model component, and reject an archive path whose basename is not the exact derived provenance name before opening the capsule.

For each sorted verified member:

1. encode the relative UTF-8 path and split it at the latest slash fitting USTAR's 155-byte prefix and 100-byte name fields;
2. reject paths not representable in USTAR rather than creating PAX or GNU records;
3. write a 512-byte header with type `5` for a directory or `0` for a regular file;
4. encode mode, uid, gid, size, and mtime as fixed-width ASCII octal with canonical NUL/space terminators;
5. calculate the checksum with the checksum field treated as eight spaces;
6. stream regular content from its no-follow descriptor while hashing and enforcing the exact verified size;
7. write zero padding to the next 512-byte boundary; and
8. write exactly 1024 final zero bytes after the last member.

Write to one operation-owned same-directory temporary using exclusive creation, fsync it, no-replace publish the archive, fsync its parent, then write/fsync/no-replace publish the exact sidecar and fsync again. If archive publication succeeds but sidecar publication fails, return `checkpoint_sidecar_publish_failed`; retry accepts an existing archive only when its exact bytes/hash equal the deterministic reconstruction and then publishes the missing exact sidecar. Never replace either output.

- [ ] **Step 6: Test mutation, special-file, and output-collision failures**

Inject a source mutation after header creation, a short read, appended source byte, inode replacement, lock loss, FIFO/symlink/device member, USTAR-unrepresentable path, archive write failure, fsync failure, archive collision, sidecar collision, and parent identity change. Assert no accepted artifact, no overwrite, and cleanup only of the operation-owned temporary after identity validation.

Run:

```bash
uv run pytest tests/capsule/test_checkpoint.py -k 'pack or sidecar or collision or mutation' tests/capsule/test_limits.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit checkpoint packing**

```bash
git add src/laconian_eval/capsule/limits.py src/laconian_eval/capsule/checkpoint.py src/laconian_eval/capsule/verify.py src/laconian_eval/capsule/filesystem.py tests/capsule/test_limits.py tests/capsule/test_checkpoint.py
git commit -m "feat: pack deterministic capsule checkpoints"
```

### Task 11: Restore checkpoints in one bounded fd-relative pass

**Files:**
- Modify: `src/laconian_eval/capsule/checkpoint.py`
- Modify: `src/laconian_eval/capsule/tree_policy.py`
- Modify: `src/laconian_eval/capsule/filesystem.py`
- Modify: `tests/capsule/test_checkpoint.py`
- Modify: `tests/capsule/test_tree_policy.py`

- [ ] **Step 1: RED-test exact round-trip and binding checks**

Pack one unsealed partial shard capsule and one sealed complete shard capsule. Give each a nested
`0o555` directory containing at least one regular file, then restore each into a fresh parent with
`CheckpointExpectedBindingsV1` populated from the preflight parent/shard files, exact ordered
`(binding_id, sha256)` protocol bindings, and the archive-name provenance. Assert:

```python
restored = restore_checkpoint(
    archive_path,
    sidecar_path,
    destination_parent=restore_root,
    destination_name=source.name,
    expected=expected,
)
assert restored == restore_root / source.name
assert snapshot_tree(restored) == snapshot_tree(source)
assert verify_capsule(restored, mode=VerificationMode.PREPARED).status == "valid"
```

The tree snapshot compares every relative path, kind, permission mode, and regular-file byte string,
including the read-only directory and its child, `.laconian.lock`, and `seal.json` when present.

For each expected field, mutate only that expected value and assert `CheckpointError.code == "checkpoint_binding_mismatch"` with no published destination.

- [ ] **Step 2: Run the restore RED gate**

Run:

```bash
uv run pytest tests/capsule/test_checkpoint.py::test_checkpoint_round_trip_preserves_exact_capsule_tree_and_modes tests/capsule/test_checkpoint.py::test_restore_requires_exact_parent_shard_and_model_bindings -q
```

Expected: FAIL because `restore_checkpoint` is absent.

- [ ] **Step 3: Build raw hostile archives without using extraction helpers**

Add a test-only raw 512-byte header builder and parameterize rejection of:

```text
archive over checkpoint_archive_bytes
member count over checkpoint_members
one file over checkpoint_file_bytes
aggregate regular bytes over checkpoint_aggregate_file_bytes
path depth over checkpoint_path_depth
expired monotonic deadline
invalid header checksum
non-USTAR magic or version
PAX local header x
PAX global header g
GNU long name L
GNU long link K
GNU sparse S
hard link 1
symbolic link 2
character device 3
block device 4
FIFO 6
contiguous file 7
absolute path
backslash
NUL inside the decoded name
non-UTF-8 name
non-NFC name
empty component
dot component
parent component
duplicate normalized path
file before its parent directory
unexpected capsule member
noncanonical octal field
setuid, setgid, or sticky mode
declared size with short data
nonzero padding
missing second terminal zero block
nonzero data after terminal blocks
sidecar wrong hash
sidecar wrong basename
existing destination
destination parent identity change
```

For every vector, assert the final destination does not exist and an unrelated sentinel in the destination parent is byte-identical.

- [ ] **Step 4: Run the hostile RED matrix**

Run:

```bash
uv run pytest tests/capsule/test_checkpoint.py -k 'rejects_' -q
```

Expected: FAIL because no bounded raw USTAR parser or restore staging exists.

- [ ] **Step 5: Implement sidecar-first bounded archive validation**

Open sidecar and archive through parent descriptors with `O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`; require both stable regular files. Parse the sidecar as one ASCII LF-terminated line with exactly two spaces, lowercase 64-hex digest, and exact archive basename. Hash the archive through its retained descriptor, enforce `checkpoint_archive_bytes`, compare the digest, rewind, and recheck identity before parsing.

Use `time.monotonic()` to establish one deadline at entry and recheck it before every header read, content chunk, fsync, verification stage, and publish. A test seam may supply a monotonic callable; production always uses the real monotonic clock.

- [ ] **Step 6: Implement the one-pass USTAR parser and extractor**

Parse raw 512-byte headers directly. Accept only USTAR magic `ustar\0`, version `00`, canonical ASCII-octal numeric fields, type `0`/NUL regular files, and type `5` directories. Reject every extension and link type before applying any name extension semantics.

For each member, before creation:

1. combine prefix/name fields exactly once;
2. decode strict UTF-8 and require NFC identity;
3. reject NUL, backslash, absolute, empty, dot, and parent components;
4. enforce path-byte and depth limits;
5. require `capsule_path_kind(path)` to equal the header kind;
6. require no duplicate normalized path;
7. require every nonroot parent directory to have appeared earlier; and
8. reserve member/per-file/aggregate capacity before reading data.

Create one operation-owned `0700` staging directory under the already-open destination parent. Open
child directories one component at a time with no-follow descriptors. Create every directory as
`0700` regardless of its archived mode, retain its descriptor plus archived mode/depth, and keep it
owner-readable/writable/searchable while any descendant may still be created. Create regular files
with `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` and mode `0600`; write exactly declared bytes,
require zero block padding, fsync, then `fchmod` the regular file to its archived permission bits.

Only after every member, padding block, and both terminal zero blocks have been parsed successfully,
recheck every retained directory identity and apply archived directory modes with descriptor-relative
`fchmod`, deepest-first. Then fsync those directories deepest-first. Never apply an archived
directory mode while an unparsed or unwritten descendant remains.

Do not call `tarfile.extract`, `tarfile.extractall`, a shell tar command, or any path-based write API.

- [ ] **Step 7: Full-verify and atomically publish the restored capsule**

While staging is still hidden:

1. require `.laconian.lock` as a regular member;
2. acquire a fresh lock on the restored `.laconian.lock` descriptor and run descriptor-based full capsule verification while holding it; archived lock bytes never count as an inherited lock state;
3. load `capsule.json`, `manifest.json`, `plan.jsonl`, and optional captured parent/shard planning inputs from verified descriptors;
4. compare every `CheckpointExpectedBindingsV1` field exactly, with null parent/shard/scenario fields required only for a full-parent capsule and protocol bindings required in manifest declaration order;
5. fsync the root and destination parent;
6. publish with `rename_noreplace`; and
7. fsync the destination parent again.

On every prepublication failure, recursively remove only the operation-owned staging tree using
retained identity checks and bounded descriptor-relative cleanup. If archived directory modes were
already applied, cleanup first uses the retained descriptors to restore owner `rwx` bits without
widening group/other bits, deepest-first, and then removes children descriptor-relatively. Add a
fault-injection test after directory-mode application that proves the hidden read-only tree is fully
removed and an unrelated sentinel is unchanged. On postpublication directory-fsync failure, return
`checkpoint_restore_post_publish_fsync_failed` and include the known published path in the exception
object without deleting it.

- [ ] **Step 8: Prove no secret or ambient-path leakage**

Place canaries in `HOME`, `TMPDIR`, provider error text, a fake credential environment value, archive bytes after a rejected header, and exception subclasses. Assert no error string/code, destination path, sidecar, accepted archive member, or test-captured diagnostic contains a canary. Assert restore does not inspect ambient temporary-directory variables.

Run:

```bash
uv run pytest tests/capsule/test_checkpoint.py tests/capsule/test_tree_policy.py tests/capsule/test_filesystem.py tests/capsule/test_verify_prepared.py tests/capsule/test_verify_sealed.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit safe checkpoint restoration**

```bash
git add src/laconian_eval/capsule/checkpoint.py src/laconian_eval/capsule/tree_policy.py src/laconian_eval/capsule/filesystem.py tests/capsule/test_checkpoint.py tests/capsule/test_tree_policy.py
git commit -m "feat: restore capsule checkpoints safely"
```

### Task 12: Prove the complete Slice 1 evidence path and run quality gates

**Files:**
- Create: `tests/capsule/test_foundation_round_trip.py`
- Create: `tests/capsule/foundation_round_trip.py`

- [ ] **Step 1: Write the failing end-to-end shard lifecycle test**

Create `test_foundation_round_trip.py` with
`test_public_foundation_round_trip_from_parent_plan_to_restored_seal`. Import the test-owned
`run_public_foundation_round_trip` integration harness from `foundation_round_trip.py`; the harness
must wire only the already public Slice 1 APIs and must not duplicate their validation or hashing.
The test requires this exact offline sequence:

```python
from pathlib import Path

from tests.capsule.foundation_round_trip import run_public_foundation_round_trip


def test_public_foundation_round_trip_from_parent_plan_to_restored_seal(
    tmp_path: Path,
) -> None:
    evidence = run_public_foundation_round_trip(tmp_path=tmp_path)
    assert evidence.provider_call_count == 40
    assert evidence.request_contract_count == 40
    assert evidence.all_request_contracts_exact is True
    assert evidence.all_attempt_evidence_exact is True
    assert evidence.all_visible_token_subtractions_exact is True
    assert evidence.source_seal_sha256 == evidence.restored_seal_sha256
    assert evidence.source_tree_sha256 == evidence.restored_tree_sha256
    assert evidence.source_sidecar_evidence_sha256 == evidence.restored_sidecar_evidence_sha256
```

```text
construct the three exact native-v2 model manifests with medium reasoning/verbosity, literal default service tier, explicit/30m cache control, five sourced rates, and SDK/lock identity
materialize three stable 480-row parents
derive and validate all 36 40-row shard plans
prepare one captured shard capsule from one parent/shard pair
execute all 40 requests through a function-local recording `OpenAIProvider` test subclass whose exact
`generate_benchmark(request: PublicBenchmarkRequestV1) -> PublicBenchmarkProviderOutcomeV1` method
echoes applied explicit/30m, read zero, write zero, reported reasoning tokens, literal default tier,
and separately recorded returned model ID
assert every committed attempt has applied/read/write statuses reported_exact/reported_zero/reported_zero, requested and returned default tier with reported_default, exact source digests, and one consistent returned model ID
assert every visible-token value equals output_tokens minus reasoning_tokens
finalize the capsule
verify SEALED_COMPLETE and capsule_sha256
write and load the deterministic scored sidecar from sealed plan/raw/cases
pack deterministic USTAR plus sidecar
restore into a new parent with exact expected bindings
verify the restored capsule and compare its seal hash and complete tree to the source
load the same scored sidecar against the restored capsule and require equal verified evidence
```

Assert the recording provider received exactly 40 calls, every request carried `reasoning={effort:
medium}`, `text={verbosity: medium}`, exact `prompt_cache_options={mode: explicit, ttl: 30m}`, and
`service_tier=default` through the
exact `OpenAIProvider.generate_benchmark` boundary, every resulting attempt classified the returned tier as `reported_default`, and no
request from another scenario appears.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
uv run pytest tests/capsule/test_foundation_round_trip.py::test_public_foundation_round_trip_from_parent_plan_to_restored_seal -q
```

Expected: FAIL during collection because `tests/capsule/foundation_round_trip.py` and
`run_public_foundation_round_trip` do not exist. This RED is required; do not pre-create the helper
or weaken the test to call one component in isolation.

- [ ] **Step 3: Add the minimal integration wiring**

Create `foundation_round_trip.py` with the single keyword-only
`run_public_foundation_round_trip(*, tmp_path) -> FoundationRoundTripEvidence`
test helper. It calls the existing manifest/planning, capture/execution, finalize, sealed verification,
scored-sidecar, deterministic USTAR, restore, and restored-verification APIs in the exact order from
Step 1. Its frozen result contains only the call count, source/restored seal hashes, source/restored
tree hashes, and source/restored sidecar evidence hashes. It contains no production fallback,
credential lookup, live-provider client, copied verifier, path outside `tmp_path`, or new public API.

Define this exact test-owned result and signature; imports shown here are part of the new helper:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FoundationRoundTripEvidence:
    provider_call_count: int
    request_contract_count: int
    all_request_contracts_exact: bool
    all_attempt_evidence_exact: bool
    all_visible_token_subtractions_exact: bool
    source_seal_sha256: str
    restored_seal_sha256: str
    source_tree_sha256: str
    restored_tree_sha256: str
    source_sidecar_evidence_sha256: str
    restored_sidecar_evidence_sha256: str


def run_public_foundation_round_trip(
    *,
    tmp_path: Path,
) -> FoundationRoundTripEvidence:
    """Return facts freshly read from one exact offline Slice 1 round trip."""
```

The body contains no additional named adapter. Construct the three strict fixture inputs directly
with the earlier-owned `PublicBenchmarkRequestV1` and resolved-manifest models. Inside
`run_public_foundation_round_trip`, define a function-local recording subclass of the earlier-owned
`OpenAIProvider`; override only the exact Task 3 method
`generate_benchmark(request: PublicBenchmarkRequestV1) -> PublicBenchmarkProviderOutcomeV1` to
append each request to a local list and return strict typed `PublicBenchmarkProviderOutcomeV1`
evidence. No fake-provider class, constant, or alternate provider interface is imported.

Wire only these earlier-task-owned APIs, in this order, using each returned object as the next call's
input: `materialize_parent_plan`, `validate_parent_plan`, `project_shard_plans`,
`validate_public_generation_partition`, `materialize_shard_projection`, `prepare_shard_capsule`,
`OpenAIProvider.generate_benchmark(request: PublicBenchmarkRequestV1) ->
PublicBenchmarkProviderOutcomeV1` through the existing capsule execution path,
`finalize_capsule`, `verify_capsule`,
`write_scored_sidecar`, `load_verified_scored_capsule`, `pack_checkpoint`, `restore_checkpoint`,
`verify_capsule` again, and `load_verified_scored_capsule` against the restored capsule.
Use `checkpoint_archive_name` for the archive name and construct the already-defined
`CheckpointProvenanceV1` and `CheckpointExpectedBindingsV1` directly. Compute complete tree hashes
by byte-sorted descriptor reads in this test helper only; do not add a production tree-hash API.
Populate every `FoundationRoundTripEvidence` field directly from the local request list, committed
attempt evidence, `FinalizeResultV1`, both public verification results, and both
`VerifiedScoredCapsuleV2` values. There are no other helper names to define or fill in later.

If the integration test exposes an owning-component defect, first add the focused regression and
minimal fix in that earlier task's exact files and commit; do not hide the mismatch in this harness.

- [ ] **Step 4: Run focused GREEN and the complete Slice 1 suite**

Run:

```bash
uv run pytest tests/capsule/test_foundation_round_trip.py::test_public_foundation_round_trip_from_parent_plan_to_restored_seal -q
```

Expected: PASS with exactly 40 locally recorded provider calls and byte-identical restored evidence.

Then run:

Run:

```bash
uv run pytest tests/test_models.py tests/test_smoke_cases.py tests/test_cases.py tests/test_public_contract.py tests/test_openai_provider.py tests/test_providers.py tests/capsule/test_manifest_models.py tests/capsule/test_capture.py tests/capsule/test_planning.py tests/capsule/test_attempts_v2.py tests/capsule/test_execution.py tests/capsule/test_sharding.py tests/capsule/test_record_models.py tests/capsule/test_prepare.py tests/capsule/test_tree_policy.py tests/capsule/test_seal_models.py tests/capsule/test_finalize.py tests/capsule/test_verify_prepared.py tests/capsule/test_verify_sealed.py tests/capsule/test_cli_finalize.py tests/capsule/test_scorable.py tests/capsule/test_sidecars.py tests/capsule/test_checkpoint.py tests/capsule/test_foundation_round_trip.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the entire repository test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS with no live provider calls and no skipped Slice 1 tests.

- [ ] **Step 6: Run static quality gates**

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all three commands exit 0 with no findings.

- [ ] **Step 7: Inspect the final diff for scope and generated residue**

Run:

```bash
git status --short
git diff --check
git diff --stat -- evals/cases/response-smoke.yaml evals/README.md src/laconian_eval tests
```

Expected: only the files listed in the Slice 1 boundary are changed; `git diff --check` prints
nothing; no result capsule, archive, sidecar, credential-bearing file, cache directory, or provider
output is tracked.

- [ ] **Step 8: Commit the cross-component verification**

```bash
git add tests/capsule/test_foundation_round_trip.py tests/capsule/foundation_round_trip.py
git commit -m "test: verify public benchmark foundations"
```

## Completion evidence

Before handing off this slice, record the fresh command outputs and final commit IDs in the implementation session response. Completion requires all of the following facts:

- the only sentence-count gates are the two prompt-grounded `user-decline` localized cases;
- every material warning has exactly one frozen `material` or `critical` severity;
- benchmark-only native-v2 request identity and injected Responses kwargs contain medium reasoning, medium verbosity, literal reasoning-mode omission, exact explicit/30m cache control with recursive no-breakpoint proof, and literal `service_tier=default`, while legacy `GenerationRequest` bytes remain unchanged;
- OpenAI SDK 3.3.1, the `uv.lock` hash from C0 peeled from approved annotated T0 and verified through the paired T1/`ProtocolAttestationTagBindingV1` closure, typed request/response fields, the exact serializer projection, and canonical response paths verify before credentials with zero provider calls on failure;
- every plan row binds that exact default-tier request identity plus a conservative input-token bound at or below 272,000, and the price snapshot binds literal default tier plus five non-null sourced dimensions: ordinary uncached input, cache-read input, cache-write input, visible output, and reasoning output;
- every attempt independently preserves applied mode/TTL, read, write, tier, usage, reasoning, requested model, returned model, and raw source digests with the exact closed status vocabularies; only `reported_exact/reported_zero/reported_zero/reported_default` may reconcile trusted no-cache usage, while missing/mismatch/invalid or nonzero evidence retains exposure and requires Runtime STOP; the exact not-applicable values are restricted to independently proven no-result/no-usage delivery states;
- reported reasoning tokens yield visible tokens by exact subtraction, while missing or invalid reasoning breakdowns yield an unavailable metric;
- three stable 480-row parent plans produce 36 disjoint 40-row scenario projections totaling 1,440 request identities;
- a shard capsule captures its exact complete parent and shard plan and cannot execute outside its projection;
- complete and explicitly incomplete capsules finalize idempotently under the sole committed seal request;
- sealed verification derives the exact capsule hash and works without a transport lock or supported local locking filesystem;
- the scored sidecar binds the exact complete seal, manifest, case index, plan, raw journal, captured cases, and one deterministic terminal row per plan item before exposing `VerifiedScoredCapsuleV2`;
- deterministic uncompressed USTAR checkpoints include `.laconian.lock`, exact relative paths, and permission modes, while restore keeps staging directories owner-writable until every child exists and then applies archived modes deepest-first; and
- restore rejects hostile archives before publication, fully verifies the hidden staging capsule, compares exact parent/shard/model bindings, and publishes only with atomic no-replace semantics.
