# Public Benchmark Evaluation and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the immutable hard-score, blind-judge, statistical inference, human-audit, sensitivity, and reporting layer for the approved three-model public benchmark.

**Architecture:** Slice 2 consumes only verified, sealed generation evidence and strict scored-attempt projections supplied by Slice 1. It writes a content-addressed attachment DAG: generation capsule → hard-score request set → judge attachment → audit and analysis attachments, then derives each model outcome independently with fixed denominators, scenario-clustered uncertainty, and fail-closed audit sensitivity. Legacy v1 smoke scoring and reporting remain separate and byte-compatible.

**Tech Stack:** Python 3.11+, Pydantic 2 strict frozen models, NumPy Generator(PCG64), a new strict
CanonicalJSONV1 validator/encoder at the registry/attestation boundary (the existing capsule encoder
alone is insufficient), SHA-256, pytest, Ruff, mypy, uv.

---

## Authoritative design and scope

Implement against the normative
[Public Three-Model Benchmark Pipeline Design](../specs/2026-08-30-public-three-model-benchmark-design.md)
at full SHA `46147ef62b5bb009421d58928e879d92247d84b5`, especially Sections 6.2–6.6,
7.1, 7.7, 9–11, 13.1, and 14.1. Approval metadata is full SHA
`0e2981e32b5d8982e78c73a5e413b36e2b1495e9`, recording explicit maintainer approval on
2026-08-30. Milestone 0 is complete; implementation is pending and unblocked. Any later normative
amendment re-blocks the affected tasks until separately approved.

This is Slice 2. It starts only after Slice 1 exposes these public, tested interfaces:

~~~python
from laconian_eval.capsule.scorable import ScoredAttemptV2
from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2

def load_verified_scored_capsule(
    capsule_path: Path,
    scored_sidecar_path: Path,
) -> VerifiedScoredCapsuleV2:
    """Verify Slice 1 seal and sidecar bindings before exposing scored evidence."""
~~~

VerifiedScoredCapsuleV2 must contain the verified SealV1 capsule SHA-256, resolved-manifest SHA-256,
plan SHA-256, ordered PlanRowV1 rows, exact ordered ScoredAttemptV2 terminal rows, and captured
ResponseCase objects keyed by case_uid. Slice 2 must not accept an unsealed capsule, a nullable
capsule hash, externally supplied case text, or an unverified scored sidecar.

Dependency direction is locked: `laconian_eval.benchmark` may import Slice 1 capsule interfaces but
must never import `laconian_eval.campaign`. It owns `LayerRootIndexV1`,
`GenerationContextExpectationV1`, `GenerationContextIndexV1`, `JudgeAttemptEvidenceV1`,
`JudgeAttemptRootIndexV1`, `ProviderEvidenceIndexV1`,
`BenchmarkProviderEvidenceProjectionV1`, and `VerifiedBenchmarkProviderEvidenceV1`. The strict index
boundaries are phase-specific: Runtime's campaign-side adapter verifies and wraps the external
generation-context expectation before pre-judge work, while the post-judge provider index carries
the already-verified plaintext campaign seed, peeled input
commit, separate audit/protocol reviewer registries, protocol digests, the exact four layer-root
indexes, and the seal-time-verified judge-attempt root into Slice 2; the verified projection is
reconstructed only from the externally supplied Runtime-verified expectation wrapper, that explicit
index, and the four retained layer roots. Serialized provider-index fields alone never mint the
wrapper or a verified projection. Slice 3
and Slice 4 may import the benchmark types and construct the expectation/context/provider records from a verified
`CampaignRegistryV1`; Slice 4 then binds the projection digest into the provenance-rich campaign
inventory. Neither the campaign registry nor campaign inventory is ever an input type to Slice 2.

Out of scope for this slice:

- live provider dispatch, retry, batch, spend-ledger, and campaign-state machinery;
- GitHub API calls, workflow YAML, environment configuration, publication PRs, tags, and releases;
- documentation/social promotion after RELEASED;
- changes to legacy RawAttempt/ScoredAttempt/RunSummary v1 behavior.

## Locked file structure

Create:

- src/laconian_eval/benchmark/__init__.py — public Slice 2 exports only.
- src/laconian_eval/benchmark/attachments.py — strict CanonicalJSONV1, attachment digests, rational values, and no-replace writers.
- src/laconian_eval/benchmark/seeds.py — normative 128-bit domain-derived seeds.
- src/laconian_eval/benchmark/context.py — campaign-neutral layer-root indexes, reviewer/protocol bindings, and the sealed pre-judge generation context.
- src/laconian_eval/benchmark/hard_score.py — HardScoreRequestSetV1 models and builder.
- src/laconian_eval/benchmark/judge.py — blind requests, strict judgments, campaign-neutral judge-attempt roots, prompt rendering, and JudgeAttachmentV1.
- src/laconian_eval/benchmark/bootstrap.py — frozen PCG64 scenario vectors and type-7 percentile intervals.
- src/laconian_eval/benchmark/aggregation.py — H/S projections, fixed denominators, paired estimands, and model analysis inputs.
- src/laconian_eval/benchmark/outcomes.py — fixed outcome precedence and reason accumulation.
- src/laconian_eval/benchmark/provider_evidence.py — benchmark-owned provider index, exact-root verification, and sealed 36-chain projection.
- src/laconian_eval/benchmark/audit_sampling.py — exact 144-record design, blind packet, and atomic sample-root writer/loader.
- src/laconian_eval/benchmark/audit_commit_reveal.py — canonical labels, commitments, reveals, adjudication, and provenance verification.
- src/laconian_eval/benchmark/audit_metrics.py — design weights, Hajek estimates, authorizing two-sided design-weighted Wilson intervals, confusion tables, and audit gates.
- src/laconian_eval/benchmark/sensitivity.py — model/arm false-fail bounds, exact search, certificates, and verifier.
- src/laconian_eval/benchmark/reporting.py — verified audit/analysis root loaders and atomic machine-analysis/Markdown artifact writers.
- src/laconian_eval/replay/ — seven fixed secret-free offline non-evidentiary handlers reached only through the existing `laconian_eval.cli:main` dispatcher.
- tests/benchmark/__init__.py
- tests/benchmark/helpers.py — deterministic 36-capsule/1,440-row synthetic evidence builders.
- tests/benchmark/test_attachments.py
- tests/benchmark/test_seeds.py
- tests/benchmark/test_context.py
- tests/benchmark/test_hard_score.py
- tests/benchmark/test_judge.py
- tests/benchmark/test_bootstrap.py
- tests/benchmark/test_aggregation.py
- tests/benchmark/test_outcomes.py
- tests/benchmark/test_provider_evidence.py
- tests/benchmark/test_audit_sampling.py
- tests/benchmark/test_audit_commit_reveal.py
- tests/benchmark/test_audit_metrics.py
- tests/benchmark/test_sensitivity_direct.py
- tests/benchmark/test_sensitivity_certificate.py
- tests/benchmark/test_reporting.py
- tests/benchmark/test_synthetic_analysis.py
- tests/benchmark/test_cli.py — existing dispatcher compatibility and seven-handler import/call graph.

Modify:

- pyproject.toml — add NumPy and route the benchmark script to compatible `laconian_eval.cli:main`
  while preserving the existing legacy `entrypoint` path.
- uv.lock — lock the NumPy dependency.
- benchmarks/methodology.md — replace the no-interval limitation with the frozen public method.
- evals/README.md — document the new derived evidence layers.
- tests/test_public_contract.py — pin cumulative Slice 2 names, seven commands, methodology, and evidence-language requirements.

Do not put these models into src/laconian_eval/models.py or extend legacy
src/laconian_eval/reporting.py. The public campaign schemas have different denominators and
integrity requirements and must not silently reinterpret walking-skeleton artifacts.

### Task 1: Add canonical attachment primitives and the normative NumPy dependency

**Files:**

- Create: src/laconian_eval/benchmark/__init__.py
- Create: src/laconian_eval/benchmark/attachments.py
- Create: tests/benchmark/__init__.py
- Create: tests/benchmark/test_attachments.py
- Modify: pyproject.toml
- Modify: uv.lock

- [ ] **Step 1: Write the failing strict-model and digest tests**

Add these tests:

~~~python
def test_rational_v1_normalizes_sign_and_reduces_exactly() -> None:
    assert RationalV1(numerator=6, denominator=8).model_dump(mode="json") == {
        "numerator": 3,
        "denominator": 4,
    }
    with pytest.raises(ValidationError):
        RationalV1(numerator=1, denominator=0)


def test_attachment_digest_is_domain_separated_and_excludes_only_its_id() -> None:
    payload = {
        "schema_version": "1",
        "parent_sha256": "a" * 64,
        "rows": [{"ordinal": 0, "value": 7}],
    }
    expected = hashlib.sha256(
        b"laconian-test-attachment-v1\0" + canonical_json(payload)
    ).hexdigest()
    assert attachment_digest("laconian-test-attachment-v1", payload) == expected
    assert attachment_digest("laconian-other-v1", payload) != expected


def test_canonical_json_v1_is_strict_and_has_no_terminal_newline() -> None:
    assert canonical_json_v1({"é": 1, "a": [2], "verified": True}) == (
        b'{"a":[2],"verified":true,"\xc3\xa9":1}'
    )
    with pytest.raises(CanonicalJSONV1Error):
        canonical_json_v1({"e\\u0301": 1})
    for forbidden in (1.0, float("nan")):
        with pytest.raises(CanonicalJSONV1Error):
            canonical_json_v1({"value": forbidden})
    for forbidden_bytes in (
        b'{"a":1}\n', b'{ "a":1}', b'{"a":1,"a":1}', b'{"e\\u0301":1}'
    ):
        with pytest.raises(CanonicalJSONV1Error):
            parse_canonical_json_v1(forbidden_bytes)


def test_write_attachment_is_canonical_fsynced_and_never_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "attachment.json"
    calls: list[int] = []
    monkeypatch.setattr(os, "fsync", lambda descriptor: calls.append(descriptor))
    write_attachment_json(target, {"z": 1, "a": 2})
    assert target.read_bytes() == b'{"a":2,"z":1}\n'
    assert len(calls) == 2
    with pytest.raises(FileExistsError):
        write_attachment_json(target, {"a": 3})
    assert target.read_bytes() == b'{"a":2,"z":1}\n'
~~~

- [ ] **Step 2: Run the RED tests**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_attachments.py
~~~

Expected: collection fails because `laconian_eval.benchmark.attachments` and
`canonical_json_v1` do not exist.

- [ ] **Step 3: Implement the strict primitives**

Use CapsuleModel and the existing canonical encoder:

~~~python
from __future__ import annotations

import math
import os
import json
import hashlib
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, Self

from pydantic import model_validator

from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.schema import CapsuleModel


class CanonicalJSONV1Error(ValueError):
    pass


def _canonical_json_v1_tree(value: object) -> object:
    # JSON booleans remain booleans; "integers only" excludes non-integer numbers,
    # not the `verified: true` member required by SignatureEvidenceV1.
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        if unicodedata.normalize("NFC", value) != value:
            raise CanonicalJSONV1Error("strings must already be NFC")
        return value
    if type(value) in (list, tuple):
        return [_canonical_json_v1_tree(item) for item in value]
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise CanonicalJSONV1Error("object keys must be strings")
        items = sorted(value.items(), key=lambda item: item[0].encode("utf-8"))
        return {str(_canonical_json_v1_tree(key)): _canonical_json_v1_tree(item) for key, item in items}
    raise CanonicalJSONV1Error("only null, strings, integer JSON, arrays, and objects are allowed")


def canonical_json_v1(value: object) -> bytes:
    """UTF-8 CanonicalJSONV1: NFC strings, bytewise keys, integer JSON, no LF."""
    return json.dumps(
        _canonical_json_v1_tree(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def parse_canonical_json_v1(data: bytes) -> object:
    def reject_number(_: str) -> NoReturn:
        raise CanonicalJSONV1Error("only integer JSON numbers are allowed")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise CanonicalJSONV1Error("duplicate object key")
        return dict(pairs)

    try:
        text = data.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            parse_float=reject_number,
            parse_constant=reject_number,
            object_pairs_hook=unique_object,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CanonicalJSONV1Error("invalid CanonicalJSONV1 bytes") from error
    canonical = canonical_json_v1(parsed)
    if canonical != data:
        raise CanonicalJSONV1Error("noncanonical CanonicalJSONV1 bytes")
    return parsed


def canonical_json_v1_digest(domain: str, value: object) -> str:
    if unicodedata.normalize("NFC", domain) != domain or not domain:
        raise CanonicalJSONV1Error("digest domain must be nonempty NFC")
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + canonical_json_v1(value)).hexdigest()


class RationalV1(CapsuleModel):
    numerator: int
    denominator: int

    @model_validator(mode="after")
    def reduce_fraction(self) -> Self:
        if type(self.numerator) is not int or type(self.denominator) is not int:
            raise ValueError("rational components must be exact integers")
        if self.denominator <= 0:
            raise ValueError("rational denominator must be positive")
        divisor = math.gcd(self.numerator, self.denominator)
        normalized_numerator = self.numerator // divisor
        normalized_denominator = self.denominator // divisor
        if normalized_denominator != self.denominator:
            object.__setattr__(self, "numerator", normalized_numerator)
            object.__setattr__(self, "denominator", normalized_denominator)
        return self


def attachment_digest(domain: str, payload_without_id: Mapping[str, object]) -> str:
    return stable_digest(domain, dict(payload_without_id))


def write_attachment_json(path: Path, payload: Mapping[str, object]) -> None:
    encoded = canonical_json(dict(payload)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short attachment write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
~~~

Export RationalV1, attachment_digest, and write_attachment_json from benchmark/__init__.py.

- [ ] **Step 4: Add and lock NumPy**

Add this runtime dependency:

~~~toml
"numpy>=2,<3",
~~~

Run:

~~~bash
uv lock
~~~

Expected: uv.lock gains one locked NumPy distribution compatible with the supported Python range.

- [ ] **Step 5: Run the GREEN tests and static checks**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_attachments.py
uv run ruff check src/laconian_eval/benchmark/attachments.py tests/benchmark/test_attachments.py
uv run mypy src/laconian_eval/benchmark/attachments.py
~~~

Expected: all commands pass.

- [ ] **Step 6: Commit**

~~~bash
git add pyproject.toml uv.lock src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/attachments.py tests/benchmark/__init__.py tests/benchmark/test_attachments.py
git commit -m "feat: add benchmark attachment primitives"
~~~

### Task 2: Freeze campaign seed derivation

**Files:**

- Create: src/laconian_eval/benchmark/seeds.py
- Create: tests/benchmark/test_seeds.py
- Modify: src/laconian_eval/benchmark/__init__.py

- [ ] **Step 1: Write the failing seed golden and boundary tests**

~~~python
def test_seed128_matches_first_128_sha256_bits() -> None:
    material = (
        b"laconian-bootstrap-v1"
        + b"\0"
        + b"campaign-seed-2026"
        + b"\0"
        + b"a" * 40
        + b"\0"
        + b"b" * 64
    )
    expected = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
    assert derive_seed128(
        "laconian-bootstrap-v1",
        "campaign-seed-2026",
        "a" * 40,
        "b" * 64,
    ) == expected


@pytest.mark.parametrize(
    "arguments",
    [
        ("", "seed", "a" * 40, "b" * 64),
        ("domain", "", "a" * 40, "b" * 64),
        ("domain", "seed", "A" * 40, "b" * 64),
        ("domain", "seed", "a" * 40, "B" * 64),
        ("bad\0domain", "seed", "a" * 40, "b" * 64),
    ],
)
def test_seed128_rejects_noncanonical_material(arguments: tuple[str, str, str, str]) -> None:
    with pytest.raises(ValueError):
        derive_seed128(*arguments)
~~~

- [ ] **Step 2: Run the RED test**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_seeds.py
~~~

Expected: import fails because derive_seed128 is absent.

- [ ] **Step 3: Implement the exact derivation**

~~~python
import hashlib
import re

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def derive_seed128(
    domain: str,
    campaign_seed: str,
    input_tag_commit: str,
    judge_protocol_sha256: str,
) -> int:
    values = (domain, campaign_seed, input_tag_commit, judge_protocol_sha256)
    if any(type(value) is not str or not value for value in values):
        raise ValueError("seed material must be nonempty strings")
    if any("\0" in value for value in values):
        raise ValueError("seed material must not contain NUL")
    if _COMMIT.fullmatch(input_tag_commit) is None:
        raise ValueError("input tag commit must be lowercase SHA-1")
    if _SHA256.fullmatch(judge_protocol_sha256) is None:
        raise ValueError("judge protocol hash must be lowercase SHA-256")
    encoded = b"\0".join(value.encode("utf-8", errors="strict") for value in values)
    return int.from_bytes(hashlib.sha256(encoded).digest()[:16], "big", signed=False)
~~~

- [ ] **Step 4: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_seeds.py
uv run ruff check src/laconian_eval/benchmark/seeds.py tests/benchmark/test_seeds.py
uv run mypy src/laconian_eval/benchmark/seeds.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/seeds.py tests/benchmark/test_seeds.py
git commit -m "feat: freeze benchmark seed derivation"
~~~

### Task 3: Build sealed HardScoreRequestSetV1 attachments

**Files:**

- Create: `src/laconian_eval/benchmark/context.py`
- Create: `src/laconian_eval/benchmark/hard_score.py`
- Create: `tests/benchmark/helpers.py`
- Create: `tests/benchmark/test_context.py`
- Create: `tests/benchmark/test_hard_score.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`

This task owns the complete pre-judge `context.py` contract:
`LayerKindV1`, both discriminated layer-member models, `LayerRootIndexV1`, both reviewer registries
and canonical digest helpers, `ProtocolAttestationV1`, `GenerationContextIndexV1`,
`GenerationContextExpectationV1`, both verified context wrappers,
`write_layer_root_index`, `load_layer_root_index`,
`write_generation_context_index`, and `load_verified_generation_context_index`. Implement and test
their exact schemas and validators in `context.py` before importing that module from `hard_score.py`.
Task 4's judge builder also imports the same context module. Task 8 creates the downstream
`provider_evidence.py`, which imports `context.py`, `hard_score.py`, and `judge.py`; `context.py`
must never import any of those downstream modules or `laconian_eval.campaign`. Do not create a
second context type, weaken a field in a later task, or defer these tests past this commit.

- [ ] **Step 1: Add deterministic sealed-capsule fixtures**

In tests/benchmark/helpers.py, build one verified 40-row model/scenario fixture plus a full strict
`GenerationContextExpectationV1`, its Runtime-style verified wrapper, and
`VerifiedGenerationContextIndexV1`: two locales × four
arms × five repetitions. Give each row a unique ordinal, plan_item_id, terminal ScoredAttemptV2,
and exact captured case. Include one provider rejection, one deterministic format failure, and 38
hard passes. The fixture must expose a nonnull generation capsule hash and must fail construction
if Slice 1 returns an unsealed capsule. The expectation fixture binds campaign ID, both reviewer
registry digests, attestation root, predecessor authority root, generation layer, expected context
digest, and workflow root; its in-memory wrapper separately binds the reconstructed final authority
root. The context fixture binds the exact generation layer,
campaign/input identities, tagged hard-scorer source/protocol, judge protocol, requested tier,
statistics protocol and singular `audit_protocol_sha256`, both reviewer registries, all three attestations, and their shared
verified C0 workflow root.

- [ ] **Step 2: Write the failing request-set contract tests**

First create `tests/benchmark/test_context.py` with these exact pre-judge contract tests:

- `test_layer_root_index_binds_kind_campaign_ordered_paths_hashes_and_self_digest`.
- `test_layer_root_index_rejects_noncanonical_path_order_alias_or_wrong_kind`.
- `test_generation_layer_member_binds_capsule_and_scored_sidecar_paths_and_hashes`.
- `test_generation_context_index_binds_verified_plaintext_seed_commit_and_36_generation_parents`.
- `test_generation_context_binds_default_tier_code_protocol_registries_and_workflow_root`.
- `test_generation_context_binds_statistical_protocol_for_later_authority_checked_analysis`.
- `test_generation_context_binds_exact_runtime_registry_audit_protocol_for_all_downstream_evidence`.
- `test_reviewer_registry_hash_recomputes_from_exact_canonical_bindings_including_signing_mode`.
- `test_audit_and_protocol_reviewer_registries_have_separate_canonical_bytes_and_digests`.
- `test_protocol_reviewer_registry_requires_three_ordered_distinct_role_bound_identities`.
- `test_protocol_reviewer_registry_requires_null_github_fingerprint_and_exact_keyed_fingerprints`.
- `test_protocol_attestations_bind_both_registry_digests_role_identity_and_workflow_root`.
- `test_generation_context_and_all_three_attestations_bind_same_c0_workflow_root`.
- `test_generation_context_expectation_binds_registry_predecessor_generation_root_and_context`.
- `test_runtime_adapter_constructs_expectation_wrapper_only_after_bound_digest_predecessor_and_final_root_verify`.
- `test_context_loader_rejects_forged_context_with_rehashed_index_against_external_expectation`.
- `test_generation_context_loader_rejects_seed_commit_code_protocol_member_or_workflow_substitution`.
- `test_runtime_adapter_can_import_public_context_contract_without_provider_or_campaign_imports`.

The tests must statically prove the acyclic import direction, inspect the public builder/loader
signatures for the absence of raw identity overrides, and mutate each bound value even when the
substituted object is internally rehashed.

~~~python
def test_hard_score_request_set_covers_all_40_plan_rows_and_only_hard_passes() -> None:
    fixture = sealed_scored_scenario()
    attachment = build_hard_score_request_set(
        context=fixture.context,
        expectation=fixture.expectation,
        boundary_ordinal=fixture.boundary_ordinal,
    )
    assert tuple(row.ordinal for row in attachment.records) == tuple(range(40))
    assert tuple(row.plan_item_id for row in attachment.records) == tuple(
        row.plan_item_id for row in fixture.evidence.plan
    )
    assert len(attachment.ordered_judge_request_ids) == 38
    assert attachment.ordered_judge_request_ids == tuple(
        row.judge_request_id for row in attachment.records if row.hard_pass
    )
    assert all(row.judge_request_id is None for row in attachment.records if not row.hard_pass)


def test_zero_hard_pass_set_is_still_sealed() -> None:
    fixture = sealed_scored_scenario(all_hard_fail=True)
    attachment = build_hard_score_request_set(
        context=fixture.context,
        expectation=fixture.expectation,
        boundary_ordinal=fixture.boundary_ordinal,
    )
    assert attachment.ordered_judge_request_ids == ()
    assert attachment.hard_score_request_set_sha256 == recompute_hard_score_request_set_sha256(
        attachment
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "wrong_capsule"])
def test_hard_score_request_set_rejects_nonbijective_or_unbound_evidence(mutation: str) -> None:
    with pytest.raises(HardScoreError):
        build_mutated_hard_score_request_set(mutation)
~~~

Also add `test_hard_score_builder_has_no_raw_identity_or_protocol_scalar_parameters`,
`test_hard_score_derives_campaign_model_scenario_and_three_code_protocol_hashes_from_context`, and
`test_hard_score_builder_and_verifier_reject_context_member_source_protocol_or_workflow_root_substitution`,
plus `test_hard_score_rejects_forged_rehashed_context_against_external_expected_digest`.
Inspect the public signatures, mutate each of campaign ID, model, scenario, hard-scorer source,
hard-score protocol, judge protocol, singular audit protocol, generation member, and workflow root independently, and require
failure even when the substituted context/index is internally rehashed.

- [ ] **Step 3: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_context.py tests/benchmark/test_hard_score.py
~~~

Expected: imports fail because `context.py` and `hard_score.py` do not exist.

- [ ] **Step 4: Define the exact schemas**

Implement the strict frozen context schemas in `context.py` before the hard-score schemas below.
The exact normative `context.py` schema and loader contract is frozen in the dedicated subsection
immediately below; Task 8 only imports it and does not redefine it.

#### Frozen `context.py` contract

`LayerKindV1` is the closed literal `generation|hard-score|judge-request|judge`.
`GenerationLayerRootMemberV1` binds ordinal, model, scenario, both canonical relative paths, the
SealV1 capsule hash, and the scored-sidecar file hash. `AttachmentLayerRootMemberV1` binds ordinal,
model, scenario, one canonical relative path, and its attachment hash. A discriminated
`LayerRootMemberV1` union and `LayerRootIndexV1` require exactly 36 members in canonical
`(generation_model UTF-8 bytes, scenario_uid raw digest bytes)` order, ordinals `0..35`, a matching
member kind, unique safe paths under the kind's fixed subtree, and the domain-separated self digest.

`AuditReviewerRegistryV1` contains exactly two distinct ordered audit reviewers, including audit
role. `ProtocolReviewerRegistryV1` contains exactly three distinct entries in role order
`statistical_method`, `blind_judge_audit_protocol`, `security_evidence`. Both use the closed
`github_verified_commit | ssh_sha256 | openpgp_fingerprint` vocabulary. GitHub mode requires null
fingerprint; keyed modes require an exact fingerprint; `security_evidence` always requires nonnull
fingerprint and therefore cannot use GitHub mode. Registry and attestation bytes use Task 1
`CanonicalJSONV1` with no terminal newline and distinct domains.

`ProtocolSubjectV1` is exactly `{kind, sha256}`. `ProtocolAttestationV1` has, in schema order,
`schema_version`, `role`, `protocol_registry_sha256`, `reviewer_numeric_account_id`,
`reviewer_login`, `verification_mode`, `signing_fingerprint`, `input_tag_object_sha256`,
`peeled_c0_sha256`, `workflow_root`, `subjects`, `subject_root`, `signed_at`,
`signature_evidence`, `attestation_sha256`; extra fields are forbidden. GitHub signature evidence
has exactly `commit_oid`, `verified: true`, `reason: "valid"`, signer numeric ID/login. Keyed modes
add exact matching `fingerprint`. `subject_root` hashes the ordered subject array; the three complete
attestations hash in registry role order to `protocol_attestations_root`.

Exact subject inventories are owned by tasks: Task 4 owns `hard_score_protocol_sha256`,
`judge_prompt_sha256`, `judge_schema_sha256`; Task 5 owns `corpus_case_root`,
`estimand_protocol_sha256`, `statistical_protocol_sha256`; Task 6 owns
`bootstrap_protocol_sha256`; Task 7 owns `outcome_classification_protocol_sha256`; Task 8 owns
`audit_sampling_protocol_sha256`; Task 9 owns `audit_commit_reveal_protocol_sha256` and
`audit_adjudication_protocol_sha256`; Tasks 11–12 own `false_fail_sensitivity_protocol_sha256`.
The security role owns exactly `provider_request_contract_sha256`, `retry_spend_protocol_sha256`,
`campaign_state_schema_sha256`, `workflow_endpoint_policy_sha256`,
`artifact_security_protocol_sha256`, `publication_correction_protocol_sha256`,
`identity_registry_bundle_sha256`, `state_writer_git_identity_sha256`; Runtime supplies and verifies
the last subject. No role may omit, reorder, duplicate, add, or borrow a subject.

`GenerationContextIndexV1` is strict, frozen, extra-forbid, and contains exactly: schema version,
campaign ID, plaintext 64-hex campaign seed and its domain digest,
peeled 40-hex input commit,
hard-scorer source hash, hard-score protocol hash, judge protocol hash, literal requested tier
`default`, literal wire field `service_tier`, statistics protocol hash, audit protocol hash, frozen
C0 workflow-inventory root,
two ordered audit-reviewer bindings and their recomputed registry digest, the complete three-role
protocol-reviewer registry, three ordered protocol attestation bindings and their recomputed root,
the generation layer-root-index digest, the ordered 36 unique generation-capsule hashes, and its
own domain-separated digest. Its validator requires all three attestations to repeat the context's
same workflow root and both recomputed registry digests and to match the corresponding role-bound
account ID/login. No self-asserted verification Boolean is accepted.

`GenerationContextExpectationV1` is strict/frozen/extra-forbid and binds exactly campaign ID, both
registry digests, `protocol_attestations_root`, predecessor authority root, full generation-layer
root, `expected_context_index_sha256`, `workflow_root`, and its own domain-separated digest. Runtime
reconstructs it privately from current authority and keeps the verified wrapper only in memory.
Serialized expectation bytes may be ordinary offline replay evidence but never a capability. The
context payload additionally binds hard-scorer source, hard-score/judge/statistical/audit protocol
roots, provider-projection root, and ordered capsule roots. `GENERATION_SET_SEALED` later requires
the ordered 36 capsule hashes plus `generation_context_expectation_sha256` and
`verified_generation_context_root`; the expectation digest does not contain itself.

~~~python
import re


LayerKindV1 = Literal["generation", "hard-score", "judge-request", "judge"]


class GenerationLayerRootMemberV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    member_kind: Literal["generation"]
    ordinal: int = Field(ge=0, lt=36)
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    capsule_relative_path: str
    generation_capsule_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    scored_sidecar_relative_path: str
    scored_sidecar_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class AttachmentLayerRootMemberV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    member_kind: Literal["hard-score", "judge-request", "judge"]
    ordinal: int = Field(ge=0, lt=36)
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    relative_path: str
    attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")


LayerRootMemberV1 = Annotated[
    GenerationLayerRootMemberV1 | AttachmentLayerRootMemberV1,
    Field(discriminator="member_kind"),
]


class LayerRootIndexV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-layer-root-index-v1"]
    layer_kind: LayerKindV1
    campaign_id: str
    members: tuple[LayerRootMemberV1, ...] = Field(min_length=36, max_length=36)
    layer_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_closed_layer_index(self) -> Self:
        if tuple(member.ordinal for member in self.members) != tuple(range(36)):
            raise ValueError("layer members require ordinals 0..35")
        keys = tuple(
            (member.generation_model.encode("utf-8"), bytes.fromhex(member.scenario_uid))
            for member in self.members
        )
        if keys != tuple(sorted(keys)) or len(set(keys)) != 36:
            raise ValueError("layer members require unique canonical model/scenario order")
        if any(member.member_kind != self.layer_kind for member in self.members):
            raise ValueError("layer member kind mismatch")
        paths = tuple(
            path
            for member in self.members
            for path in (
                (member.capsule_relative_path, member.scored_sidecar_relative_path)
                if isinstance(member, GenerationLayerRootMemberV1)
                else (member.relative_path,)
            )
        )
        if len(set(paths)) != len(paths):
            raise ValueError("layer paths must be unique")
        if any(
            path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            for path in paths
        ):
            raise ValueError("layer paths must be canonical safe POSIX-relative paths")
        expected_prefix = {
            "generation": "generation/",
            "hard-score": "hard-score/",
            "judge-request": "judge-requests/",
            "judge": "judge/",
        }[self.layer_kind]
        if any(not path.startswith(expected_prefix) for path in paths):
            raise ValueError("layer member path is outside its fixed subtree")
        expected = stable_digest(
            "laconian-benchmark-layer-root-index-v1",
            self.model_dump(mode="json", exclude={"layer_root_index_sha256"}),
        )
        if self.layer_root_index_sha256 != expected:
            raise ValueError("layer root index self digest mismatch")
        return self


SignatureVerificationModeV1 = Literal[
    "github_verified_commit", "ssh_sha256", "openpgp_fingerprint"
]
ProtocolReviewRoleV1 = Literal[
    "statistical_method",
    "blind_judge_audit_protocol",
    "security_evidence",
]


def validate_signature_mode_fingerprint(
    mode: SignatureVerificationModeV1,
    fingerprint: str | None,
    *,
    require_keyed: bool = False,
) -> None:
    if mode == "github_verified_commit":
        if fingerprint is not None or require_keyed:
            raise ValueError("GitHub verification requires null fingerprint")
    elif mode == "ssh_sha256":
        if fingerprint is None or re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint) is None:
            raise ValueError("SSH verification requires an exact SHA256 fingerprint")
    elif fingerprint is None or re.fullmatch(r"(?:[0-9A-F]{40}|[0-9A-F]{64})", fingerprint) is None:
        raise ValueError("OpenPGP verification requires an uppercase primary-key fingerprint")


class ReviewerAccountBindingV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    reviewer_id: str
    reviewer_numeric_account_id: int = Field(gt=0)
    reviewer_login: str
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: str | None = Field(
        pattern=r"^(?:[0-9A-F]{40}|[0-9A-F]{64}|SHA256:[A-Za-z0-9+/]{43})$",
    )
    role: Literal["audit_reviewer"]

    @model_validator(mode="after")
    def validate_verification_mode(self) -> Self:
        validate_signature_mode_fingerprint(self.verification_mode, self.signing_fingerprint)
        return self


class AuditReviewerRegistryV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-reviewer-registry-v1"]
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1]
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_audit_reviewer_registry(self) -> Self:
        keys = tuple(item.reviewer_id.encode("utf-8") for item in self.reviewers)
        if keys != tuple(sorted(keys)) or len(set(keys)) != 2:
            raise ValueError("audit reviewer IDs must be distinct and bytewise ordered")
        if (
            len({item.reviewer_numeric_account_id for item in self.reviewers}) != 2
            or len({item.reviewer_login for item in self.reviewers}) != 2
        ):
            raise ValueError("audit reviewer identities must be distinct")
        if self.audit_reviewer_registry_sha256 != compute_audit_reviewer_registry_sha256(
            self.reviewers
        ):
            raise ValueError("audit reviewer registry digest mismatch")
        return self


class ProtocolReviewerBindingV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    role: ProtocolReviewRoleV1
    reviewer_numeric_account_id: int = Field(gt=0)
    reviewer_login: str
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: str | None = Field(
        pattern=r"^(?:[0-9A-F]{40}|[0-9A-F]{64}|SHA256:[A-Za-z0-9+/]{43})$",
    )


class ProtocolReviewerRegistryV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-protocol-reviewer-registry-v1"]
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ]
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_protocol_reviewer_registry(self) -> Self:
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        if tuple(reviewer.role for reviewer in self.reviewers) != expected_roles:
            raise ValueError("protocol reviewer role order mismatch")
        if (
            len({reviewer.reviewer_numeric_account_id for reviewer in self.reviewers}) != 3
            or len({reviewer.reviewer_login for reviewer in self.reviewers}) != 3
        ):
            raise ValueError("protocol reviewer identities must be distinct")
        for reviewer in self.reviewers:
            validate_signature_mode_fingerprint(
                reviewer.verification_mode,
                reviewer.signing_fingerprint,
                require_keyed=reviewer.role == "security_evidence",
            )
        expected = compute_protocol_reviewer_registry_sha256(self.reviewers)
        if self.protocol_reviewer_registry_sha256 != expected:
            raise ValueError("protocol reviewer registry digest mismatch")
        return self


ProtocolSubjectKindV1 = Literal[
    "corpus_case_root",
    "estimand_protocol_sha256",
    "statistical_protocol_sha256",
    "bootstrap_protocol_sha256",
    "outcome_classification_protocol_sha256",
    "false_fail_sensitivity_protocol_sha256",
    "hard_score_protocol_sha256",
    "judge_prompt_sha256",
    "judge_schema_sha256",
    "audit_sampling_protocol_sha256",
    "audit_commit_reveal_protocol_sha256",
    "audit_adjudication_protocol_sha256",
    "provider_request_contract_sha256",
    "retry_spend_protocol_sha256",
    "campaign_state_schema_sha256",
    "workflow_endpoint_policy_sha256",
    "artifact_security_protocol_sha256",
    "publication_correction_protocol_sha256",
    "identity_registry_bundle_sha256",
    "state_writer_git_identity_sha256",
]


class ProtocolSubjectV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: ProtocolSubjectKindV1
    sha256: str = Field(pattern="^[0-9a-f]{64}$")


class GitHubSignatureEvidenceV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    commit_oid: str = Field(pattern="^[0-9a-f]{40}$")
    verified: Literal[True]
    reason: Literal["valid"]
    signer_numeric_account_id: int = Field(gt=0)
    signer_login: str


class KeyedSignatureEvidenceV1(GitHubSignatureEvidenceV1):
    fingerprint: str = Field(
        pattern=r"^(?:[0-9A-F]{40}|[0-9A-F]{64}|SHA256:[A-Za-z0-9+/]{43})$"
    )


SignatureEvidenceV1 = GitHubSignatureEvidenceV1 | KeyedSignatureEvidenceV1


class ProtocolAttestationV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["protocol-attestation-v1"]
    role: ProtocolReviewRoleV1
    protocol_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reviewer_numeric_account_id: int = Field(gt=0)
    reviewer_login: str
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: str | None = Field(
        pattern=r"^(?:[0-9A-F]{40}|[0-9A-F]{64}|SHA256:[A-Za-z0-9+/]{43})$",
    )
    input_tag_object_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    peeled_c0_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    subjects: tuple[ProtocolSubjectV1, ...]
    subject_root: str = Field(pattern="^[0-9a-f]{64}$")
    signed_at: str
    signature_evidence: SignatureEvidenceV1
    attestation_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_role_subjects_signature_and_digest(self) -> Self:
        expected_subjects: dict[ProtocolReviewRoleV1, tuple[ProtocolSubjectKindV1, ...]] = {
            "statistical_method": (
                "corpus_case_root", "estimand_protocol_sha256",
                "statistical_protocol_sha256", "bootstrap_protocol_sha256",
                "outcome_classification_protocol_sha256",
                "false_fail_sensitivity_protocol_sha256",
            ),
            "blind_judge_audit_protocol": (
                "hard_score_protocol_sha256", "judge_prompt_sha256",
                "judge_schema_sha256", "audit_sampling_protocol_sha256",
                "audit_commit_reveal_protocol_sha256",
                "audit_adjudication_protocol_sha256",
            ),
            "security_evidence": (
                "provider_request_contract_sha256", "retry_spend_protocol_sha256",
                "campaign_state_schema_sha256", "workflow_endpoint_policy_sha256",
                "artifact_security_protocol_sha256",
                "publication_correction_protocol_sha256",
                "identity_registry_bundle_sha256", "state_writer_git_identity_sha256",
            ),
        }
        if tuple(item.kind for item in self.subjects) != expected_subjects[self.role]:
            raise ValueError("protocol attestation subject inventory/order mismatch")
        validate_signature_mode_fingerprint(
            self.verification_mode,
            self.signing_fingerprint,
            require_keyed=self.role == "security_evidence",
        )
        keyed = self.verification_mode != "github_verified_commit"
        if keyed != (self.signing_fingerprint is not None):
            raise ValueError("protocol attestation mode/fingerprint mismatch")
        if keyed:
            if not isinstance(self.signature_evidence, KeyedSignatureEvidenceV1):
                raise ValueError("keyed attestation requires keyed signature evidence")
            if self.signature_evidence.fingerprint != self.signing_fingerprint:
                raise ValueError("keyed signature fingerprint mismatch")
        elif isinstance(self.signature_evidence, KeyedSignatureEvidenceV1):
            raise ValueError("GitHub verification forbids fingerprint evidence")
        if (
            self.signature_evidence.signer_numeric_account_id
            != self.reviewer_numeric_account_id
            or self.signature_evidence.signer_login != self.reviewer_login
        ):
            raise ValueError("protocol attestation signer identity mismatch")
        expected_subject_root = canonical_json_v1_digest(
            "laconian-protocol-attestation-subject-root-v1",
            [item.model_dump(mode="json") for item in self.subjects],
        )
        if self.subject_root != expected_subject_root:
            raise ValueError("protocol attestation subject root mismatch")
        expected = canonical_json_v1_digest(
            "laconian-protocol-attestation-v1",
            self.model_dump(mode="json", exclude={"attestation_sha256"}),
        )
        if self.attestation_sha256 != expected:
            raise ValueError("protocol attestation digest mismatch")
        return self


def canonical_reviewer_registry_bytes(
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
) -> bytes:
    return canonical_json_v1(
        {
            "schema_version": "benchmark-reviewer-registry-v1",
            "reviewers": [item.model_dump(mode="json") for item in reviewers],
        }
    )


def compute_audit_reviewer_registry_sha256(
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
) -> str:
    return hashlib.sha256(canonical_reviewer_registry_bytes(reviewers)).hexdigest()


def canonical_protocol_reviewer_registry_bytes(
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ],
) -> bytes:
    return canonical_json_v1(
        {
            "schema_version": "benchmark-protocol-reviewer-registry-v1",
            "reviewers": [item.model_dump(mode="json") for item in reviewers],
        }
    )


def compute_protocol_reviewer_registry_sha256(
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ],
) -> str:
    return hashlib.sha256(canonical_protocol_reviewer_registry_bytes(reviewers)).hexdigest()


def compute_protocol_attestations_root(
    attestations: tuple[
        ProtocolAttestationV1,
        ProtocolAttestationV1,
        ProtocolAttestationV1,
    ],
) -> str:
    expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    if tuple(item.role for item in attestations) != expected_roles:
        raise ValueError("protocol attestation root role order mismatch")
    return canonical_json_v1_digest(
        "laconian-protocol-review-attestations-root-v1",
        [item.model_dump(mode="json") for item in attestations],
    )


class BenchmarkProtocolBindingsV1(BaseModel):
    """One centrally owned immutable projection repeated by every downstream attachment."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    hard_scorer_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    corpus_case_root: str = Field(pattern="^[0-9a-f]{64}$")
    estimand_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bootstrap_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    outcome_classification_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    false_fail_sensitivity_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")


def protocol_bindings_from_context(
    context: "GenerationContextIndexV1",
) -> BenchmarkProtocolBindingsV1:
    return BenchmarkProtocolBindingsV1.model_validate(
        {
            name: getattr(context, name)
            for name in BenchmarkProtocolBindingsV1.model_fields
        }
    )


class GenerationContextIndexV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-generation-context-index-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    input_tag_commit: str = Field(pattern="^[0-9a-f]{40}$")
    hard_scorer_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_requested_service_tier: Literal["default"]
    judge_service_tier_wire_field: Literal["service_tier"]
    corpus_case_root: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    estimand_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bootstrap_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    outcome_classification_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    false_fail_sensitivity_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    audit_reviewer_registry: AuditReviewerRegistryV1
    protocol_reviewer_registry: ProtocolReviewerRegistryV1
    protocol_attestations: tuple[
        ProtocolAttestationV1,
        ProtocolAttestationV1,
        ProtocolAttestationV1,
    ]
    generation_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_closed_generation_context(self) -> Self:
        expected_seed_sha256 = stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": self.campaign_seed,
            },
        )
        if self.campaign_seed_sha256 != expected_seed_sha256:
            raise ValueError("generation context campaign seed digest mismatch")
        if len(set(self.ordered_generation_capsule_sha256s)) != 36:
            raise ValueError("generation context requires 36 unique capsule parents")
        reviewers = self.audit_reviewer_registry.reviewers
        reviewer_keys = tuple(reviewer.reviewer_id.encode("utf-8") for reviewer in reviewers)
        if (
            reviewer_keys != tuple(sorted(reviewer_keys))
            or len(set(reviewer_keys)) != 2
            or len({reviewer.reviewer_numeric_account_id for reviewer in reviewers}) != 2
            or len({reviewer.reviewer_login for reviewer in reviewers}) != 2
        ):
            raise ValueError("generation context requires two ordered distinct reviewers")
        if self.audit_reviewer_registry_sha256 != compute_audit_reviewer_registry_sha256(reviewers):
            raise ValueError("generation context reviewer registry digest mismatch")
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        protocol_reviewers = self.protocol_reviewer_registry.reviewers
        if tuple(item.role for item in self.protocol_attestations) != expected_roles:
            raise ValueError("generation context requires the ordered protocol review roles")
        if tuple(reviewer.role for reviewer in protocol_reviewers) != expected_roles:
            raise ValueError("generation context protocol reviewer role order mismatch")
        if (
            len({item.attestation_sha256 for item in self.protocol_attestations}) != 3
            or len({reviewer.reviewer_numeric_account_id for reviewer in protocol_reviewers}) != 3
            or len({reviewer.reviewer_login for reviewer in protocol_reviewers}) != 3
        ):
            raise ValueError("generation context requires three distinct protocol reviewers")
        if self.protocol_reviewer_registry.protocol_reviewer_registry_sha256 != (
            compute_protocol_reviewer_registry_sha256(protocol_reviewers)
        ):
            raise ValueError("generation context protocol reviewer registry digest mismatch")
        for attestation, reviewer in zip(
            self.protocol_attestations,
            protocol_reviewers,
            strict=True,
        ):
            if (
                attestation.role != reviewer.role
                or attestation.reviewer_numeric_account_id != reviewer.reviewer_numeric_account_id
                or attestation.reviewer_login != reviewer.reviewer_login
                or attestation.protocol_registry_sha256
                != self.protocol_reviewer_registry.protocol_reviewer_registry_sha256
                or attestation.workflow_root
                != self.workflow_root
            ):
                raise ValueError("generation context protocol attestation identity mismatch")
        if self.protocol_attestations_root != (
            compute_protocol_attestations_root(self.protocol_attestations)
        ):
            raise ValueError("generation context protocol review root mismatch")
        expected = stable_digest(
            "laconian-benchmark-generation-context-index-v1",
            self.model_dump(mode="json", exclude={"generation_context_index_sha256"}),
        )
        if self.generation_context_index_sha256 != expected:
            raise ValueError("generation context self digest mismatch")
        return self


class GenerationContextExpectationV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-generation-context-expectation-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    predecessor_authority_root_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_layer_root: str = Field(pattern="^[0-9a-f]{64}$")
    expected_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = stable_digest(
            "laconian-benchmark-generation-context-expectation-v1",
            self.model_dump(
                mode="json",
                exclude={"generation_context_expectation_sha256"},
            ),
        )
        if self.generation_context_expectation_sha256 != expected:
            raise ValueError("generation context expectation self digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedGenerationContextExpectationV1:
    expectation: GenerationContextExpectationV1
    bound_generation_complete_authority_root_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedGenerationContextIndexV1:
    expectation: VerifiedGenerationContextExpectationV1
    index: GenerationContextIndexV1
    root_index: LayerRootIndexV1
    generation_evidence: tuple[VerifiedScoredCapsuleV2, ...]


def write_layer_root_index(root: Path, index: LayerRootIndexV1) -> None:
    """Write the kind-specific fixed index.json canonically with no replacement."""


def load_layer_root_index(root: Path, *, expected_kind: LayerKindV1) -> LayerRootIndexV1:
    """Load the fixed layer subtree, reject aliases/extras, and recompute its digest."""


def write_generation_context_index(
    generation_index_path: Path,
    index: GenerationContextIndexV1,
) -> None:
    """No-replace write the Slice 3 adapter's canonical pre-judge context file."""


def load_verified_generation_context_index(
    *,
    generation_index_path: Path,
    generation_root: Path,
    expectation: VerifiedGenerationContextExpectationV1,
) -> VerifiedGenerationContextIndexV1:
    """Verify context against external expectation, layer index, and all 36 capsule/sidecar pairs."""
~~~

The two registry byte contracts are exact and independent:
`canonical_json_v1({"schema_version": "benchmark-reviewer-registry-v1", "reviewers":
[item.model_dump(mode="json") for item in audit_reviewers]})` for the two
bytewise-reviewer-ID-ordered audit bindings, and
`canonical_json_v1({"schema_version": "benchmark-protocol-reviewer-registry-v1", "reviewers":
[item.model_dump(mode="json") for item in protocol_reviewers]})` for the three fixed-role protocol
bindings. Neither byte string has a terminal newline. Each digest
is raw SHA-256 over its own freshly
regenerated bytes. The attestation root is
`canonical_json_v1_digest("laconian-protocol-review-attestations-root-v1",
[item.model_dump(mode="json") for item in protocol_attestations])` over the three complete
attestations in fixed role order. Tests reject any cross-population reuse, reordered identity, string/Boolean numeric ID,
login rename, omitted protocol fingerprint, or digest copied without exact byte equality.

`context.py` intentionally provides no raw-file-to-verified-expectation loader. The fixed
campaign-side module `laconian_eval.campaign.runtime` owns that trust transition: it
reconstructs the predecessor and final `GENERATION_COMPLETE` authority roots read-only, parses the
fixed expectation child canonically, recomputes its self digest, verifies every expectation field
against the campaign registry and generation-layer roots, requires the final authority root to bind
that exact expectation digest,
and only then constructs `VerifiedGenerationContextExpectationV1` in memory. Its three stage
functions `Runtime.hard_score`, `Runtime.prepare_judge`, and `Runtime.seal_judge` import and
call the benchmark loaders/builders with that wrapper. These are the Runtime-owned first three of
the seven live boundaries frozen in Task 15; Publication's four exact `evaluation_stage` boundaries
reconstruct/reuse the same wrapper for provider/audit/analysis loading. `context.py`,
`hard_score.py`, and `judge.py` never import the
campaign module. Runtime Task 7 must own adapter tests for wrong predecessor/final
root, copied expectation bytes, a forged internally rehashed context, and a context digest not bound
by the retained transition; the wrapper's final-root field must be exactly 64 lowercase hexadecimal
characters and equal the freshly reconstructed final root. Publication invokes the campaign-side
stage functions; it never treats a standalone expectation path or a raw digest as authorization.

The loader accepts only the exact `GENERATION/generation-context.json` file and the exact
`GENERATION/generation/index.json` root index, revalidates both, verifies every retained
capsule/sidecar pair with `load_verified_scored_capsule`, and requires the ordered vector and every
model/scenario identity to match. Before reading context authority fields it derives the expected
digest only from `expectation.expectation.expected_context_index_sha256`, requires the parsed
context self digest to equal that value, and requires campaign, both reviewer registries,
attestation, workflow, and generation-root digests to match the expectation. There is no raw expected-digest
argument, argv option, environment value, or value read from the context/index under test. Runtime
Task 7 is the sole producer adapter; it constructs this
campaign-neutral record from verified `CampaignRegistryV1` and the class-bound tagged C0 inventory,
including the statistics protocol later consumed by analysis, but no campaign type crosses into
`context.py`.

The singular `audit_protocol_sha256` is not an additional attestation subject and does not alter the
three approved role inventories above. Runtime derives it from the exact verified-C0
`benchmarks/protocols/public-three-model-v1/audit.json` member and supplies it through its verified
registry adapter. `GenerationContextIndexV1` and `BenchmarkProtocolBindingsV1` store that exact value;
their validators reject a caller scalar, a second audit-digest alias, or any value that differs from
the Runtime registry binding. Every downstream object that carries `protocol_bindings` therefore
inherits this singular audit-protocol authority without redefining its source.

Then define the hard-score schemas:

~~~python
HardReasonCode = Literal[
    "hard_pass",
    "provider_rejected",
    "retry_exhausted",
    "blank_output",
    "required_literal",
    "forbidden_literal",
    "json_object",
    "json_key_set",
    "yaml_mapping",
    "yaml_key_set",
    "min_sentences",
    "max_sentences",
]


class HardScoreRecordV1(CapsuleModel):
    ordinal: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    response_id: Sha256 | None
    terminal_reason: TerminalReason
    hard_pass: StrictBool
    reason_codes: tuple[HardReasonCode, ...] = Field(min_length=1)
    judge_request_id: Sha256 | None


class HardScoreRequestSetV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    generation_model: BoundedNonBlankString
    scenario_uid: Sha256
    generation_capsule_sha256: Sha256
    manifest_sha256: Sha256
    plan_sha256: Sha256
    hard_scorer_source_sha256: Sha256
    hard_score_protocol_sha256: Sha256
    judge_protocol_sha256: Sha256
    protocol_bindings: BenchmarkProtocolBindingsV1
    records: tuple[HardScoreRecordV1, ...] = Field(min_length=1, max_length=40)
    ordered_judge_request_ids: tuple[Sha256, ...]
    hard_score_request_set_sha256: Sha256
~~~

Hard-pass rows require a nonnull response_id, reason_codes exactly ("hard_pass",), and a nonnull
judge_request_id. Hard-fail rows require judge_request_id null and sorted unique reason codes.
Provider failures retain response_id null; successful deterministic failures retain their persisted
response_id. Records must have ordinals 0..39 and exact plan order.

Derive each judge request without a circular attachment dependency:

~~~python
def derive_judge_request_id(
    *,
    campaign_id: str,
    generation_capsule_sha256: str,
    plan_item_id: str,
    response_id: str,
    judge_protocol_sha256: str,
) -> str:
    return stable_digest(
        "laconian-judge-request-v1",
        {
            "campaign_id": campaign_id,
            "generation_capsule_sha256": generation_capsule_sha256,
            "plan_item_id": plan_item_id,
            "response_id": response_id,
            "judge_protocol_sha256": judge_protocol_sha256,
        },
    )
~~~

Derive hard_score_request_set_sha256 over every preceding field using domain
laconian-hard-score-request-set-v1; exclude only hard_score_request_set_sha256 itself.

- [ ] **Step 5: Implement the builder and verifier**

~~~python
def build_hard_score_request_set(
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> HardScoreRequestSetV1:
    """Derive every identity from one verified context member and build its exact 40 rows."""


def recompute_hard_score_request_set_sha256(
    attachment: HardScoreRequestSetV1,
) -> str:
    """Revalidate the model, omit only its self hash, and recompute the domain digest."""


def verify_hard_score_request_set(
    attachment: HardScoreRequestSetV1,
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> None:
    """Rebuild from verified context and require canonical equality, including all six identities."""
~~~

Map existing CheckResult names to the closed HardReasonCode enum. Unknown check names are an
integrity error, never free-form reason text.
`boundary_ordinal` selects exactly one aligned generation root member and verified scored capsule;
both functions first require the separately supplied verified Runtime-bound expectation to equal
the wrapper retained by the context and derive the expected digest from it internally. The wrapper
is threaded only by the in-process campaign-stage caller; neither a digest nor an expectation path
is exposed as a benchmark CLI option.
The builder derives campaign ID, generation model, scenario UID, hard-scorer source hash,
hard-score protocol hash, and judge protocol hash from that class-bound context and never accepts
them as scalar arguments. The verifier class-bound revalidates the context, root index, selected
member, and capsule/sidecar, invokes the builder, and canonical-byte compares the result. No source
hash, protocol hash, campaign/model/scenario identity, or workflow root comes from a CLI option,
environment value, attachment-under-test, or caller inference.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_context.py tests/benchmark/test_hard_score.py
uv run ruff check src/laconian_eval/benchmark/context.py src/laconian_eval/benchmark/hard_score.py tests/benchmark
uv run mypy src/laconian_eval/benchmark/context.py src/laconian_eval/benchmark/hard_score.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/context.py src/laconian_eval/benchmark/hard_score.py tests/benchmark/helpers.py tests/benchmark/test_context.py tests/benchmark/test_hard_score.py
git commit -m "feat: seal hard-score request sets"
~~~

### Task 4: Freeze the blind-judge request, result, and attachment schemas

**Files:**

- Create: `src/laconian_eval/benchmark/judge.py`
- Create: `tests/benchmark/test_judge.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write schema and blinding tests**

Create tests named:

- `test_blind_request_schema_exposes_only_allowed_fields`; assert its dumped keys equal exactly
  `judge_request_id`, `blind_id`, `prompt`, `locale`, `rubric`,
  `material_warning_requirement`, `material_warning_severity`, and `candidate_response`.
- `test_candidate_text_remains_delimited_untrusted_data`.
- `test_judgment_overall_pass_is_derivable_and_malformed_rows_fail_closed`.
- `test_judge_attachment_binds_capsule_and_request_set_with_exact_coverage`.
- `test_zero_request_judge_attachment_is_sealed_without_calls`.
- `test_judge_attempt_evidence_binds_request_blind_response_usage_delivery_terminal_and_parents`.
- `test_judge_attempt_root_requires_exact_36_boundaries_including_explicit_empty_files`.
- `test_judge_attempt_root_rejects_missing_reordered_duplicate_retry_or_cross_parent_rows`.
- `test_judge_attachment_derives_records_only_from_verified_terminal_attempts`.
- `test_judge_attachment_builder_and_verifier_require_external_verified_context_expectation`.
- `test_provider_ready_judge_request_hashes_literal_service_tier_default_wire_field`.
- `test_judge_attempt_records_requested_and_returned_service_tier_without_inference`.
- `test_judge_wire_uses_exact_explicit_30m_cache_control_and_no_recursive_breakpoint`.
- `test_judge_response_uses_only_canonical_applied_read_write_reasoning_tier_model_paths`.
- `test_judge_requires_openai_3_3_1_and_tagged_uv_lock_before_credentials`.
- `test_judge_attempt_tracks_requested_and_returned_judge_model_ids_separately`.
- `test_judge_success_requires_reported_exact_read_zero_write_zero`.
- `test_judge_nonzero_missing_mismatched_or_invalid_cache_evidence_is_terminal_stop_evidence`.
- `test_judge_sanitized_nulls_retain_independent_applied_read_write_tier_usage_reasoning_model_source_digests`.
- `test_judge_attempt_reuses_foundation_service_tier_status_without_alias`.
- `test_runtime_to_benchmark_handoff_round_trips_all_five_exact_tier_statuses`.
- `test_judge_request_builder_and_verifier_require_verified_generation_context`.
- `test_judge_request_builder_has_no_raw_campaign_seed_or_protocol_tier_identity_parameters`.
- `test_judge_request_rejects_seed_campaign_protocol_tier_member_or_workflow_root_substitution`.
- `test_judge_request_rejects_forged_rehashed_context_against_external_expected_digest`.
- `test_missing_or_nondefault_returned_service_tier_stops_and_retains_worst_case`.
- `test_definitely_rejected_429_uses_exact_not_applicable_definitely_rejected_and_retries`.
- `test_only_structured_429_can_schedule_or_exhaust_retry`.
- `test_two_exact_not_applicable_statuses_require_matching_delivery_and_no_response_usage`.
- `test_unknown_delivery_with_missing_or_mismatched_tier_stops_and_retains_worst_case`.
- `test_runtime_adapter_can_import_campaign_neutral_judge_attempt_contract`.
- `test_judge_attempt_module_has_no_campaign_import`.

The injection fixture must contain closing XML, a Markdown fence, an instruction to call a tool,
an absolute path, and a forged JSON judgment. Assert that each byte remains only inside one
length-prefixed candidate-data field and never changes the authority, schema, or settings block.
The no-alias test imports `AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`, and
`ServiceTierStatus` from `laconian_eval.providers`, requires each exact Foundation vocabulary, and
statically rejects any benchmark-local status `Literal` declaration. The handoff test canonical-JSON
round-trips one Runtime-shaped attempt for each status, mutates status/value/delivery independently,
and proves that only the exact derived combination validates. A response may enter a successful
judge attachment only with applied `explicit`/`30m`, `reported_exact`, read `reported_zero`, write
`reported_zero`, and tier `reported_default`. Nonzero, missing, mismatched, or invalid applied/read/
write evidence is a terminal STOP attachment with retained raw-source digests, never a semantic
judgment or retry. The returned judge model ID may differ from `JUDGE_REQUESTED_MODEL_ID`, but all
successful judge responses in one campaign must report one byte-identical returned ID.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_judge.py
~~~

Expected: collection fails with `ModuleNotFoundError: No module named
'laconian_eval.benchmark.judge'`.

- [ ] **Step 3: Add closed models and the derivable decision rule**

Implement these public models and signatures:

~~~python
WarningSeverity = Literal["material", "critical"]


class RubricItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_index: int = Field(ge=0)
    requirement: str = Field(min_length=1, max_length=2_000)


class BlindJudgeRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    judge_request_id: str
    blind_id: str
    prompt: str = Field(min_length=1, max_length=20_000)
    locale: str
    rubric: tuple[RubricItemV1, ...]
    material_warning_requirement: str | None = Field(default=None, min_length=1, max_length=2_000)
    material_warning_severity: WarningSeverity | None
    candidate_response: str = Field(min_length=1, max_length=40_000)


class RubricItemJudgmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    item_index: int = Field(ge=0)
    passed: bool
    evidence: str = Field(min_length=1, max_length=1_000)


class WarningJudgmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    passed: bool
    evidence: str = Field(min_length=1, max_length=1_000)


class StructuredJudgmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    judge_request_id: str
    blind_id: str
    rubric_items: tuple[RubricItemJudgmentV1, ...]
    material_warning: WarningJudgmentV1 | None
    material_contradiction: bool
    contradiction_evidence: str | None = Field(default=None, max_length=1_000)
    semantic_pass: bool


def derive_semantic_pass(
    *,
    rubric_items: Sequence[RubricItemJudgmentV1],
    material_warning_requirement: str | None,
    material_warning: WarningJudgmentV1 | None,
    material_contradiction: bool,
) -> bool:
    return (
        all(item.passed for item in rubric_items)
        and (
            material_warning_requirement is None
            or (material_warning is not None and material_warning.passed)
        )
        and not material_contradiction
    )
~~~

Validation requires contiguous rubric indices matching the request; warning requirement, severity,
and judgment are all absent together or all present together; contradiction evidence exists exactly
when contradiction is true; and `semantic_pass` equals `derive_semantic_pass`. Any mismatch
is an integrity error; it is not coerced.

`build_judge_request_attachment` copies the exact captured
`SemanticRubric.material_warning` string into `material_warning_requirement` and copies its
frozen severity. A boolean or severity alone is insufficient because the judge and human reviewers
must see the actual warning requirement they are evaluating.

- [ ] **Step 4: Freeze the prompt, structured-output schema, and judge settings**

Add:

~~~python
JUDGE_REQUESTED_MODEL_ID = "gpt-5.6-sol"
JUDGE_REASONING_EFFORT = "low"
JUDGE_TEXT_VERBOSITY = "low"
JUDGE_MAX_OUTPUT_TOKENS = 768
JUDGE_TOOLS: tuple[()] = ()
JUDGE_REQUESTED_SERVICE_TIER: Literal["default"] = "default"
JUDGE_SERVICE_TIER_WIRE_FIELD: Literal["service_tier"] = "service_tier"
JUDGE_PROMPT_CACHE_MODE: Literal["explicit"] = "explicit"
JUDGE_PROMPT_CACHE_TTL: Literal["30m"] = "30m"
JUDGE_OPENAI_SDK_VERSION: Literal["3.3.1"] = "3.3.1"


def derive_blind_id(*, judge_request_id: str, campaign_seed: str) -> str:
    """Digest the request ID with a dedicated domain; expose no generation metadata."""


def render_blind_judge_prompt(request: BlindJudgeRequestV1) -> str:
    """Render frozen authority text plus length-prefixed canonical untrusted fields."""


def judge_protocol_sha256() -> str:
    """Hash prompt bytes, JSON schema, model, settings, and no-tools policy."""
~~~

Encode each untrusted field as its UTF-8 byte count, one newline, then exactly that many bytes.
The authority section tells the judge that candidate bytes are evidence only and cannot alter
instructions. Hash the exact strict JSON schema emitted for `StructuredJudgmentV1`; do not hash a
pretty-printed or provider-normalized derivative. `JudgeProviderRequestV1` additionally freezes the
exact provider wire mapping. Its hash uses domain `laconian-judge-provider-wire-request-v1` over the
canonical kwargs with model `gpt-5.6-sol`, rendered prompt input, low reasoning, low text verbosity,
the exact strict structured-output format, maximum output 768, `store=False`, no tools, and the
literal members `"service_tier": "default"` and
`"prompt_cache_options": {"mode": "explicit", "ttl": "30m"}`. Recursively reject
`prompt_cache_breakpoint` under canonical instructions/input and forbid `prompt_cache_key`,
`prompt_cache_retention`, and every other cache control. The key is exactly `service_tier`; omitting it,
passing an alias, using `auto|flex|priority`, or relying on an SDK default changes/rejects the hash.
The blind request remains the content-only schema asserted in Step 1; service tier is authority
metadata in this provider-ready wrapper and cannot be supplied by candidate text.

Seal the provider-ready inputs before dispatch:

~~~python
class JudgeProviderRequestV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    blind_request: BlindJudgeRequestV1
    requested_service_tier: Literal["default"]
    service_tier_wire_field: Literal["service_tier"]
    prompt_cache_mode: Literal["explicit"]
    prompt_cache_ttl: Literal["30m"]
    openai_sdk_version: Literal["3.3.1"]
    uv_lock_member_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_wire_request_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class JudgeRequestAttachmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["judge-request-attachment-v1"]
    campaign_id: str
    generation_model: str
    scenario_uid: str
    generation_capsule_sha256: str
    hard_score_request_set_sha256: str
    judge_protocol_sha256: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    campaign_seed_sha256: str
    requested_service_tier: Literal["default"]
    service_tier_wire_field: Literal["service_tier"]
    prompt_cache_mode: Literal["explicit"]
    prompt_cache_ttl: Literal["30m"]
    requests: tuple[JudgeProviderRequestV1, ...]
    judge_request_attachment_sha256: str


def build_judge_request_attachment(
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
    request_set: HardScoreRequestSetV1,
) -> JudgeRequestAttachmentV1:
    """Derive authority from context and build ordered blind inputs from its sealed member."""


def verify_judge_request_attachment(
    attachment: JudgeRequestAttachmentV1,
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
    request_set: HardScoreRequestSetV1,
) -> None:
    """Rebuild from verified context and require exact request, blind, tier, parent, and bytes."""
~~~

Request IDs inside `JudgeProviderRequestV1.blind_request` must exactly equal the hard-score set's
ordered IDs. Both attachment-level tier fields and every wrapper must equal the frozen constants,
and every wire-request hash is independently regenerated from the rendered prompt/settings. The request attachment digest
excludes only its own field and uses domain `laconian-judge-request-attachment-v1`. A zero-request
hard-score set produces a sealed empty request attachment and no provider input rows.
Before credentials, verify installed OpenAI SDK `3.3.1`, the C0-derived `uv.lock` member hash, and
typed support for the frozen wire/response members. Judge evidence reads only
`response.service_tier`, `response.prompt_cache_options.mode/ttl`,
`response.usage.input_tokens`, `response.usage.input_tokens_details.cached_tokens`,
`response.usage.input_tokens_details.cache_write_tokens`, `response.usage.output_tokens`,
`response.usage.output_tokens_details.reasoning_tokens`, `response.usage.total_tokens`, and
`response.model`, retaining an independent source digest for each dimension.
The boundary ordinal selects the same generation member used by the hard-score set. Both functions
first require the separately supplied verified Runtime-bound expectation to equal the wrapper held
by the context, derive its expected context digest, and require that digest to equal the context
index. They then class-bound revalidate `VerifiedGenerationContextIndexV1`, derive the evidence object, campaign ID,
plaintext seed, seed digest, judge protocol, requested literal tier, and exact wire-field name from
that context, and recompute every blind ID. They reject a context/request-set member mismatch even
when the attacker recomputes both self hashes; an independently rehashed forged context also fails
against the retained expectation. No overload accepts a raw seed, campaign ID, protocol
hash, tier, wire field, generation model, scenario, or independently supplied evidence object.

- [ ] **Step 5: Add capsule-bound judge attachments and exact coverage verification**

~~~python
from laconian_eval.providers import (
    AppliedCacheControlStatus,
    CacheReadStatus,
    CacheWriteStatus,
    ProviderMetadataString,
    ServiceTierStatus,
)


JudgeAttemptDispositionV1 = Literal[
    "success",
    "retry_scheduled",
    "retry_exhausted",
    "provider_rejected",
    "authentication_stopped",
    "ambiguous_delivery",
    "service_tier_unverified",
    "service_tier_mismatch",
    "cache_control_policy_incident",
    "cache_read_policy_incident",
    "cache_write_policy_incident",
]
JudgeDeliveryCertaintyV1 = Literal[
    "definitely_not_sent",
    "definitely_rejected",
    "response_received",
    "unknown",
]
JudgeUsageAvailabilityV1 = Literal["complete", "partial", "unavailable"]
ReasoningAccountingStatusV1 = Literal["reported", "not_reported", "not_applicable", "invalid"]
JudgeCostAvailabilityV1 = Literal[
    "trusted_usage",
    "definitely_rejected_zero",
    "retained_worst_case",
]


class JudgeAttemptUsageV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    ordinary_uncached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    availability: JudgeUsageAvailabilityV1
    cache_read_status: CacheReadStatus
    cache_write_status: CacheWriteStatus
    reasoning_accounting: ReasoningAccountingStatusV1

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        core = (self.input_tokens, self.output_tokens, self.total_tokens)
        present = sum(value is not None for value in core)
        if self.availability == "unavailable" and any(
            value is not None
            for value in (
                *core,
                self.cache_read_tokens,
                self.cache_write_tokens,
                self.reasoning_tokens,
            )
        ):
            raise ValueError("unavailable judge usage has counts")
        if self.availability == "partial" and present not in (1, 2):
            raise ValueError("partial judge usage requires one or two core counts")
        if self.availability == "complete" and (
            present != 3
            or self.total_tokens != self.input_tokens + self.output_tokens  # type: ignore[operator]
        ):
            raise ValueError("complete judge usage is inconsistent")
        for status, value in (
            (self.cache_read_status, self.cache_read_tokens),
            (self.cache_write_status, self.cache_write_tokens),
        ):
            if (status in {"reported_zero", "reported_nonzero"}) != (value is not None):
                raise ValueError("judge cache status/value mismatch")
            if status == "reported_zero" and value != 0:
                raise ValueError("judge reported_zero requires zero")
            if status == "reported_nonzero" and (value is None or value <= 0):
                raise ValueError("judge reported_nonzero requires positive value")
        if (
            (self.cache_read_tokens is not None or self.cache_write_tokens is not None)
            and self.input_tokens is None
        ):
            raise ValueError("judge cache components require input tokens")
        if (
            self.input_tokens is not None
            and (self.cache_read_tokens or 0) + (self.cache_write_tokens or 0)
            > self.input_tokens
        ):
            raise ValueError("judge cache components exceed input")
        if self.input_tokens is not None and self.ordinary_uncached_input_tokens != (
            self.input_tokens - (self.cache_read_tokens or 0) - (self.cache_write_tokens or 0)
        ):
            raise ValueError("judge ordinary uncached input mismatch")
        if (
            self.reasoning_tokens is not None
            and (
                self.output_tokens is None
                or self.reasoning_tokens > self.output_tokens
            )
        ):
            raise ValueError("judge reasoning tokens exceed output")
        return self


class JudgeAttemptEvidenceV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["judge-attempt-evidence-v1"]
    campaign_id: str
    boundary_ordinal: int = Field(ge=0, lt=36)
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    generation_capsule_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_request_set_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    judge_request_id: str = Field(pattern="^[0-9a-f]{64}$")
    blind_id: str = Field(pattern="^[0-9a-f]{64}$")
    blind_request_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    attempt_number: int = Field(ge=1, le=6)
    judge_attempt_id: str = Field(pattern="^[0-9a-f]{64}$")
    retry_of_judge_attempt_sha256: str | None = Field(
        default=None,
        pattern="^[0-9a-f]{64}$",
    )
    retry_authorization_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    structured_retry_status: Literal[429] | None = None
    batch_plan_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    consumed_batch_receipt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reservation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    retry_evidence_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    spend_event_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    delivery_evidence_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    delivery_certainty: JudgeDeliveryCertaintyV1
    terminal: bool
    disposition: JudgeAttemptDispositionV1
    requested_service_tier: Literal["default"]
    service_tier_wire_field: Literal["service_tier"]
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    provider_wire_request_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    service_tier_status: ServiceTierStatus
    returned_service_tier: ProviderMetadataString | None = None
    cost_availability: JudgeCostAvailabilityV1
    provider_request_id: str | None = Field(
        default=None,
        pattern=r"^[\x21-\x7E]{1,512}$",
    )
    requested_judge_model_id: Literal["gpt-5.6-sol"]
    returned_judge_model_id: ProviderMetadataString | None
    applied_cache_control_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_read_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_write_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    service_tier_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    usage_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reasoning_tokens_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    returned_judge_model_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    raw_response_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    usage: JudgeAttemptUsageV1
    judgment: StructuredJudgmentV1 | None
    terminal_evidence_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    judge_attempt_evidence_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        expected_service_tier_status: ServiceTierStatus
        if self.returned_service_tier == "default":
            expected_service_tier_status = "reported_default"
        elif self.returned_service_tier is not None:
            expected_service_tier_status = "mismatch"
        elif self.delivery_certainty == "definitely_not_sent":
            expected_service_tier_status = "not_applicable_definitely_not_sent"
        elif self.delivery_certainty == "definitely_rejected":
            expected_service_tier_status = "not_applicable_definitely_rejected"
        else:
            expected_service_tier_status = "missing"
        if self.service_tier_status != expected_service_tier_status:
            raise ValueError("judge service-tier status mismatch")
        expected_not_applicable = {
            "definitely_not_sent": "not_applicable_definitely_not_sent",
            "definitely_rejected": "not_applicable_definitely_rejected",
        }.get(self.delivery_certainty)
        if expected_not_applicable is not None and (
            self.usage.availability != "unavailable"
            or self.usage.cache_read_status != expected_not_applicable
            or self.usage.cache_write_status != expected_not_applicable
            or self.applied_cache_control_status != expected_not_applicable
            or self.usage.reasoning_accounting != "not_applicable"
            or self.provider_request_id is not None
            or self.returned_judge_model_id is not None
            or self.raw_response_sha256 is not None
            or self.judgment is not None
        ):
            raise ValueError("not-applicable judge tier requires no response or usage")
        expected_attempt_id = stable_digest(
            "laconian-judge-attempt-id-v1",
            {
                "judge_request_id": self.judge_request_id,
                "attempt_number": self.attempt_number,
                "batch_plan_sha256": self.batch_plan_sha256,
                "consumed_batch_receipt_sha256": self.consumed_batch_receipt_sha256,
            },
        )
        if self.judge_attempt_id != expected_attempt_id:
            raise ValueError("judge attempt ID mismatch")
        if self.attempt_number == 1 and (
            self.retry_of_judge_attempt_sha256 is not None
            or self.retry_authorization_sha256 is not None
        ):
            raise ValueError("judge retry lineage shape mismatch")
        if self.attempt_number > 1 and (
            self.retry_of_judge_attempt_sha256 is None
            or self.retry_authorization_sha256 is None
        ):
            raise ValueError("judge retry lineage shape mismatch")
        if (
            (self.disposition in {"retry_scheduled", "retry_exhausted"})
            != (self.structured_retry_status == 429)
        ):
            raise ValueError("only a structured 429 may schedule or exhaust a retry")
        if self.disposition == "success":
            if (
                not self.terminal
                or self.delivery_certainty != "response_received"
                or self.service_tier_status != "reported_default"
                or self.returned_service_tier != "default"
                or self.cost_availability != "trusted_usage"
                or self.usage.availability != "complete"
                or self.applied_prompt_cache_mode != "explicit"
                or self.applied_prompt_cache_ttl != "30m"
                or self.applied_cache_control_status != "reported_exact"
                or self.usage.cache_read_status != "reported_zero"
                or self.usage.cache_write_status != "reported_zero"
                or (self.usage.cache_write_tokens or 0) != 0
                or self.provider_request_id is None
                or self.returned_judge_model_id is None
                or self.raw_response_sha256 is None
                or self.judgment is None
                or self.judgment.judge_request_id != self.judge_request_id
                or self.judgment.blind_id != self.blind_id
                or self.terminal_evidence_sha256 is None
                or self.retry_evidence_sha256 is not None
            ):
                raise ValueError("invalid successful judge attempt")
        elif self.disposition == "retry_scheduled":
            if (
                self.terminal
                or self.attempt_number >= 6
                or self.delivery_certainty != "definitely_rejected"
                or self.service_tier_status
                != "not_applicable_definitely_rejected"
                or self.cost_availability != "definitely_rejected_zero"
                or self.usage.availability != "unavailable"
                or self.retry_evidence_sha256 is None
                or self.terminal_evidence_sha256 is not None
                or any(
                    value is not None
                    for value in (
                        self.returned_service_tier,
                        self.provider_request_id,
                        self.returned_judge_model_id,
                        self.raw_response_sha256,
                        self.judgment,
                    )
                )
            ):
                raise ValueError("invalid scheduled judge retry")
        elif self.disposition in {"service_tier_unverified", "service_tier_mismatch"}:
            tier_shape_valid = (
                (
                    self.delivery_certainty == "response_received"
                    and self.returned_service_tier is None
                    and self.service_tier_status == "missing"
                )
                if self.disposition == "service_tier_unverified"
                else (
                    self.returned_service_tier not in {None, "default"}
                    and self.service_tier_status == "mismatch"
                )
            )
            if (
                not self.terminal
                or self.delivery_certainty not in {"response_received", "unknown"}
                or not tier_shape_valid
                or self.cost_availability != "retained_worst_case"
                or (
                    self.delivery_certainty == "response_received"
                    and (
                        self.provider_request_id is None
                        or self.raw_response_sha256 is None
                    )
                )
                or self.judgment is not None
                or self.terminal_evidence_sha256 is None
                or self.retry_evidence_sha256 is not None
            ):
                raise ValueError("invalid judge service-tier incident")
        elif self.disposition in {
            "cache_control_policy_incident",
            "cache_read_policy_incident",
            "cache_write_policy_incident",
        }:
            cache_incident = (
                self.applied_cache_control_status != "reported_exact"
                if self.disposition == "cache_control_policy_incident"
                else self.usage.cache_read_status != "reported_zero"
                if self.disposition == "cache_read_policy_incident"
                else self.usage.cache_write_status != "reported_zero"
            )
            if (
                not self.terminal
                or self.delivery_certainty != "response_received"
                or self.service_tier_status != "reported_default"
                or self.returned_service_tier != "default"
                or not cache_incident
                or self.cost_availability != "retained_worst_case"
                or self.provider_request_id is None
                or self.raw_response_sha256 is None
                or self.judgment is not None
                or self.terminal_evidence_sha256 is None
                or self.retry_evidence_sha256 is not None
            ):
                raise ValueError("invalid judge cache policy incident")
        else:
            expected_delivery = {
                "retry_exhausted": "definitely_rejected",
                "authentication_stopped": "definitely_rejected",
                "ambiguous_delivery": "unknown",
            }.get(self.disposition)
            if (
                not self.terminal
                or self.terminal_evidence_sha256 is None
                or self.retry_evidence_sha256 is not None
                or (
                    expected_delivery is not None
                    and self.delivery_certainty != expected_delivery
                )
                or (
                    self.disposition == "provider_rejected"
                    and self.delivery_certainty
                    not in {"definitely_not_sent", "definitely_rejected"}
                )
                or (
                    self.delivery_certainty
                    in {"definitely_not_sent", "definitely_rejected"}
                    and self.cost_availability != "definitely_rejected_zero"
                )
                or (
                    self.disposition == "ambiguous_delivery"
                    and (
                        self.service_tier_status != "missing"
                        or self.cost_availability != "retained_worst_case"
                    )
                )
                or any(
                    value is not None
                    for value in (
                        self.returned_service_tier,
                        self.provider_request_id,
                        self.returned_judge_model_id,
                        self.raw_response_sha256,
                        self.judgment,
                    )
                )
            ):
                raise ValueError("invalid terminal judge failure")
        expected = stable_digest(
            "laconian-judge-attempt-evidence-v1",
            self.model_dump(mode="json", exclude={"judge_attempt_evidence_sha256"}),
        )
        if self.judge_attempt_evidence_sha256 != expected:
            raise ValueError("judge attempt evidence digest mismatch")
        return self


class JudgeAttemptBoundaryV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["judge-attempt-boundary-v1"]
    boundary_ordinal: int = Field(ge=0, lt=36)
    campaign_id: str
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    generation_capsule_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_request_set_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_judge_request_ids: tuple[str, ...] = Field(max_length=40)
    attempts: tuple[JudgeAttemptEvidenceV1, ...] = Field(max_length=240)
    judge_attempt_boundary_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_boundary(self) -> Self:
        if len(set(self.ordered_judge_request_ids)) != len(self.ordered_judge_request_ids):
            raise ValueError("judge boundary request IDs must be unique")
        parent_fields = (
            "boundary_ordinal",
            "campaign_id",
            "generation_model",
            "scenario_uid",
            "generation_capsule_sha256",
            "hard_score_request_set_sha256",
            "judge_request_attachment_sha256",
            "judge_protocol_sha256",
        )
        if any(
            any(getattr(attempt, field) != getattr(self, field) for field in parent_fields)
            for attempt in self.attempts
        ):
            raise ValueError("judge boundary attempt parent mismatch")
        grouped_ids: list[str] = []
        for attempt in self.attempts:
            if not grouped_ids or grouped_ids[-1] != attempt.judge_request_id:
                grouped_ids.append(attempt.judge_request_id)
        if tuple(grouped_ids) != self.ordered_judge_request_ids:
            raise ValueError("judge boundary request history order mismatch")
        for request_id in self.ordered_judge_request_ids:
            history = tuple(
                attempt for attempt in self.attempts if attempt.judge_request_id == request_id
            )
            if tuple(attempt.attempt_number for attempt in history) != tuple(
                range(1, len(history) + 1)
            ):
                raise ValueError("judge boundary attempt-number gap")
            if sum(attempt.terminal for attempt in history) != 1 or not history[-1].terminal:
                raise ValueError("judge boundary requires one final terminal attempt")
            for previous, current in zip(history, history[1:]):
                if (
                    previous.disposition != "retry_scheduled"
                    or current.retry_of_judge_attempt_sha256
                    != previous.judge_attempt_evidence_sha256
                    or current.retry_authorization_sha256
                    != previous.retry_evidence_sha256
                ):
                    raise ValueError("judge boundary retry chain mismatch")
        expected = stable_digest(
            "laconian-judge-attempt-boundary-v1",
            self.model_dump(mode="json", exclude={"judge_attempt_boundary_sha256"}),
        )
        if self.judge_attempt_boundary_sha256 != expected:
            raise ValueError("judge attempt boundary digest mismatch")
        return self


class JudgeAttemptRootMemberV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    ordinal: int = Field(ge=0, lt=36)
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    relative_path: str
    judge_request_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_boundary_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    request_count: int = Field(ge=0, le=40)
    attempt_count: int = Field(ge=0, le=240)


class JudgeAttemptRootIndexV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["judge-attempt-root-index-v1"]
    campaign_id: str
    judge_request_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    members: tuple[JudgeAttemptRootMemberV1, ...] = Field(min_length=36, max_length=36)
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_root_index(self) -> Self:
        if tuple(member.ordinal for member in self.members) != tuple(range(36)):
            raise ValueError("judge attempt root requires ordinals 0..35")
        keys = tuple(
            (member.generation_model.encode("utf-8"), bytes.fromhex(member.scenario_uid))
            for member in self.members
        )
        if keys != tuple(sorted(keys)) or len(set(keys)) != 36:
            raise ValueError("judge attempt root order mismatch")
        if any(
            member.relative_path != f"judge-attempts/{member.ordinal:03d}.json"
            for member in self.members
        ):
            raise ValueError("judge attempt root member path mismatch")
        if (
            len({member.judge_request_attachment_sha256 for member in self.members}) != 36
            or len({member.judge_attempt_boundary_sha256 for member in self.members}) != 36
        ):
            raise ValueError("judge attempt root parents must be unique")
        expected = stable_digest(
            "laconian-judge-attempt-root-index-v1",
            self.model_dump(mode="json", exclude={"judge_attempt_root_index_sha256"}),
        )
        if self.judge_attempt_root_index_sha256 != expected:
            raise ValueError("judge attempt root digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedJudgeAttemptRootV1:
    index: JudgeAttemptRootIndexV1
    boundaries: tuple[JudgeAttemptBoundaryV1, ...]


def write_judge_attempt_root(
    attempt_root: Path,
    *,
    index: JudgeAttemptRootIndexV1,
    boundaries: Sequence[JudgeAttemptBoundaryV1],
) -> None:
    """Write the fixed complete ATTEMPTS tree canonically with no replacement."""


def load_verified_judge_attempt_root(
    attempt_root: Path,
    *,
    expected_request_root_index_sha256: str,
    request_attachments: Sequence[JudgeRequestAttachmentV1],
) -> VerifiedJudgeAttemptRootV1:
    """Verify the fixed 36 boundaries, retry chains, terminal coverage, and every parent."""


class JudgeRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    judge_request_id: str
    blind_id: str
    raw_judge_attempt_sha256: str
    returned_judge_model_id: ProviderMetadataString
    requested_service_tier: Literal["default"]
    service_tier_status: Literal["reported_default"]
    returned_service_tier: Literal["default"]
    judgment: StructuredJudgmentV1


class JudgeAttachmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["judge-attachment-v1"]
    campaign_id: str
    generation_model: str
    scenario_uid: str
    generation_capsule_sha256: str
    hard_score_request_set_sha256: str
    judge_request_attachment_sha256: str
    judge_protocol_sha256: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    requested_judge_model_id: Literal["gpt-5.6-sol"]
    requested_service_tier: Literal["default"]
    service_tier_wire_field: Literal["service_tier"]
    records: tuple[JudgeRecordV1, ...]
    judge_attachment_sha256: str


def build_judge_attachment(
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    request_set: HardScoreRequestSetV1,
    request_attachment: JudgeRequestAttachmentV1,
    attempt_root: VerifiedJudgeAttemptRootV1,
    boundary_ordinal: int,
) -> JudgeAttachmentV1:
    """Derive records only from verified terminal attempts, including sealed empty boundaries."""


def verify_judge_attachment(
    attachment: JudgeAttachmentV1,
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    request_set: HardScoreRequestSetV1,
    request_attachment: JudgeRequestAttachmentV1,
) -> None:
    """Verify exact ordered coverage, bindings, model identity, decisions, and self hash."""
~~~

`JudgeAttemptEvidenceV1` is the campaign-neutral Slice 3→Slice 2 handoff: it imports no campaign,
controller, batch, spend, or authority model. Runtime Task 7 imports this benchmark type and writes
it; Runtime's `Runtime.seal_judge` never reads a controller-private attempt object or reconstructs
evidence from a directory name. `blind_request_sha256` is raw SHA-256 of the exact canonical
`BlindJudgeRequestV1` bytes already sealed in the request attachment. `judge_attempt_id` is
`stable_digest("laconian-judge-attempt-id-v1", {"judge_request_id": judge_request_id,
"attempt_number": attempt_number, "batch_plan_sha256": batch_plan_sha256,
"consumed_batch_receipt_sha256": consumed_batch_receipt_sha256})`.
`judge_attempt_evidence_sha256` uses domain `laconian-judge-attempt-evidence-v1` over every preceding
field and excludes only itself. Thus the evidence binds the exact request/blind identity, all four
upstream benchmark parents, runtime batch/receipt/reservation/retry/spend/delivery/terminal parents,
provider wire-request/service-tier identity, response identity, complete usage/cost-availability
evidence, parsed judgment, and retry lineage without
depending on a campaign class.

Validate the attempt truth table exactly. A `success` is terminal, has delivery
`response_received`, nonnull provider request ID, a nonnull returned model ID recorded separately
from `requested_judge_model_id="gpt-5.6-sol"`, raw response
hash, returned service tier exactly `default`, judgment, and terminal-evidence hash, and its judgment
request/blind IDs equal the sealed request. It repeats the literal requested tier/wire-field and exact
provider-wire-request hash from `JudgeProviderRequestV1`, and records
`service_tier_status="reported_default"`, `applied_cache_control_status="reported_exact"`, and
cache read/write statuses both `reported_zero`. Across successful judge responses the returned model
ID must be one consistent value but need not equal the requested ID. `retry_scheduled` is nonterminal, has delivery
`definitely_rejected`, `structured_retry_status=429`, nonnull retry evidence,
`service_tier_status="not_applicable_definitely_rejected"`,
unavailable usage whose applied/read/write statuses are all
`not_applicable_definitely_rejected` and reasoning status is `not_applicable`, zero definitely
rejected cost, null terminal evidence, and no provider request/model/response/judgment fields. A
structured pre-response 429 with that exact evidence is therefore retryable even though no Responses
object or returned service tier exists, except that attempt six cannot schedule a seventh call.
`retry_exhausted` also requires the same structured 429;
every nonretry disposition requires null `structured_retry_status`. Every other
ordinary failure disposition is terminal with nonnull terminal evidence and no accepted response or judgment:
`retry_exhausted` requires `definitely_rejected`, `authentication_stopped` requires
`definitely_rejected`, `ambiguous_delivery` requires `unknown`, and `provider_rejected` permits only
`definitely_not_sent|definitely_rejected`; all ordinary failures have null retry evidence. Definite
non-send/rejection respectively uses `not_applicable_definitely_not_sent` or
`not_applicable_definitely_rejected` only with no response or usage and zero cost, while unknown
delivery with no returned tier is terminal `ambiguous_delivery`, uses `missing`, and retains
worst-case cost. A received response with absent returned service tier is terminal
`service_tier_unverified`; a returned tier other than literal `default` under received or unknown
delivery is terminal `service_tier_mismatch`. The two tier dispositions respectively record
`missing` or `mismatch`, preserve
every provider request ID, response hash, returned tier, and usage field that exists, and require
`cost_availability="retained_worst_case"`, null accepted judgment/retry evidence, and STOP/terminal
evidence. A `response_received` incident requires its provider request ID and raw response hash;
unknown delivery may lack both. A nonzero cache read or write, applied-control
missing/mismatch/invalid, or read/write missing/invalid is terminal STOP evidence, preserves every
usage/charge/source digest, and cannot become success. A nonzero write is charged before STOP.
Attempt one has null retry parent/authorization; attempt n>1 must point
to the immediately preceding evidence hash for the same request and carry the exact retry
authorization emitted by that preceding row. Only a preceding `retry_scheduled` row permits it, and
the prior row's `retry_evidence_sha256` must equal the next row's `retry_authorization_sha256`. There
is exactly one terminal row per nonempty request history and
no later row. A completed root accepted by Runtime's `Runtime.seal_judge` requires that terminal
row to be `success`;
a stopped, tier-mismatched/unverified, policy-incident, ambiguous, failed, missing, duplicated, or
nonterminal-only request cannot be converted to a judge record.

`JudgeAttemptUsageV1` preserves cached-read, cache-write, and uncached evidence independently.
Complete core usage requires all three core counts and `total_tokens == input_tokens +
output_tokens`; partial has one or two; unavailable has none. Each accounting status is closed:
`reported` requires its corresponding count, while `not_reported|not_applicable|invalid` requires
null. When present, cached-read plus cache-write cannot exceed input; reported reasoning cannot
exceed output. Missing/invalid cache-write detail remains missing/invalid for retained-worst-case
cost and integrity limitations, and nonzero writes remain policy-incident evidence; neither is
folded into cached or uncached input or used in the visible-token objective. Failure attempts may
retain usage when the provider supplied it.

Import `ServiceTierStatus` from `laconian_eval.providers`; do not redeclare or normalize a
benchmark-only alias. Its exact five-state vocabulary is `reported_default`,
`not_applicable_definitely_not_sent`, `not_applicable_definitely_rejected`, `missing`, and
`mismatch`. `reported_default` requires returned tier `default`; `mismatch` requires a nonnull
different tier; `missing` requires a null tier under `response_received|unknown`; and each exact
`not_applicable_*` state requires its named delivery certainty plus no response object and completely
unavailable/not-applicable usage. The status is never inferred from the requested tier, SDK defaults,
HTTP status alone, or cost accounting.

The only valid attempt-root layout is
`ATTEMPTS/judge-attempts/index.json` plus exactly
`ATTEMPTS/judge-attempts/000.json` through `035.json`. Every file is canonical JSON. Each boundary
copies one corresponding request attachment's campaign/model/scenario and generation/hard/request/
protocol parents, exact ordered request IDs, all attempt histories in request order then increasing
attempt number, and a domain `laconian-judge-attempt-boundary-v1` self digest. Empty request
attachments still require their own boundary file with empty request and attempt tuples. The root
index has ordinals 0..35 in the same canonical `(generation_model UTF-8 bytes, scenario_uid raw
SHA-256 bytes)` order as the verified request-root index; each member path is exactly
`judge-attempts/<ordinal:03d>.json` and binds the request attachment, boundary digest, request count,
and attempt count. Its self digest uses domain `laconian-judge-attempt-root-index-v1` and excludes
only itself.

`write_judge_attempt_root` class-bound revalidates the index and all 36 boundaries, requires exact
index/boundary equality, and writes the 37-file tree with descriptor-relative no-replace/fsync
semantics. `load_verified_judge_attempt_root` descriptor-opens the fixed allowlist, rejects
symlinks, aliases, duplicate inodes, extra/missing files, noncanonical bytes, count/hash/order
mismatches, and requires the explicit expected request-root-index digest plus all 36 already
verified `JudgeRequestAttachmentV1` objects. It recomputes blind/request hashes, every attempt ID,
self digest, retry chain, truth-table state, boundary digest, and root digest, including explicit
empty boundaries. It returns the verified wrapper only after a final descriptor identity recheck.
Runtime Task 7 owns construction from its verified controller records and must fresh-reload the
complete root before handing it to Slice 2.

`build_judge_attachment` accepts only the externally expectation-anchored generation context, the
matching expected context digest, the verified attempt-root wrapper, and one boundary ordinal,
selects each request's sole terminal success, and constructs `JudgeRecordV1` with
`raw_judge_attempt_sha256 == judge_attempt_evidence_sha256`. It has no overload accepting arbitrary
records or raw provider output. Immediately after building, Runtime's `Runtime.seal_judge`
canonical-byte compares each record, including the derived accepted-only
`service_tier_status="reported_default"`, to its source terminal attempt
before discarding controller-private input authority;
`verify_judge_attachment` first repeats the context/expectation equality check, then rechecks the
self-contained request/blind/decision/attempt-hash bindings and self digest used by the later
four-root provider-evidence loader.

The record IDs must equal the request set's ordered judge-request IDs exactly: no missing,
duplicate, extra, or reordered record is accepted. The attachment and every record copy the
literal requested tier `default`; every record's returned tier must also be exactly `default` and
its source attempt's provider-wire hash must equal the corresponding request wrapper. The attachment digest excludes only
`judge_attachment_sha256` and uses domain `laconian-judge-attachment-v1`.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_judge.py
uv run ruff check src/laconian_eval/benchmark/judge.py tests/benchmark/test_judge.py
uv run mypy src/laconian_eval/benchmark/judge.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/judge.py tests/benchmark/helpers.py tests/benchmark/test_judge.py
git commit -m "feat: freeze blind semantic judge attachments"
~~~

### Task 5: Build the fixed-denominator H/S table and visible-token eligibility

**Files:**

- Create: `src/laconian_eval/benchmark/aggregation.py`
- Create: `tests/benchmark/test_aggregation.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write denominator, failure, and token-accounting tests**

Create tests named:

- `test_h_and_s_use_120_planned_key_denominators`.
- `test_provider_rejections_are_zero_but_missing_or_ambiguous_keys_invalidate`.
- `test_planned_observation_provider_failures_require_null_response_and_zero_h_s`.
- `test_planned_observation_success_requires_response_and_exact_h_s_reason_matrix`.
- `test_cache_write_counts_accounting_and_cost_basis_remain_distinct`.
- `test_missing_cache_write_detail_retains_worst_case_cost_and_integrity_limitation`.
- `test_cache_write_evidence_never_changes_visible_output_or_pair_eligibility`.
- `test_visible_tokens_subtract_reasoning_and_never_fall_back_to_billed_output`.
- `test_eligible_pairs_and_token_pairs_are_distinct`.

The first fixture must contain exactly 12 scenarios, two locales, and five repetitions for one arm,
then assert `hard_pass_rate == Fraction(sum_h, 120)` and
`semantic_success_rate == Fraction(sum_s, 120)`. The token test covers missing reasoning usage,
reasoning greater than output, and a valid zero-visible-token response.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_aggregation.py
~~~

Expected: collection fails because `laconian_eval.benchmark.aggregation` does not exist.

- [ ] **Step 3: Materialize one row per planned observation**

Import `AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`, and
`ServiceTierStatus` from the Foundations owner without aliases, then implement:

~~~python
TerminalZeroReason = Literal[
    "provider_rejected",
    "retry_exhausted",
    "blank_response",
    "hard_fail",
]

ArmName = Literal["baseline", "caveman", "if", "concise"]
GateName = Literal["hard", "semantic"]
CachePolicyStatusV1 = Literal[
    "conformant_zero_write",
    "terminal_no_usage",
    "missing_write_detail",
    "forbidden_nonzero_write",
]
CostAvailabilityV1 = Literal[
    "trusted_usage",
    "definitely_rejected_zero",
    "retained_worst_case",
    "unavailable",
]
CacheIntegrityLimitationV1 = Literal[
    "cache_write_detail_missing",
    "forbidden_cache_write_observed",
]


class InferenceIntegrityError(ValueError):
    """Evidence cannot be mapped bijectively to the frozen planned population."""


class PlannedObservationV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    generation_model: str
    scenario_uid: str
    case_id: str
    locale: str
    repetition: int = Field(ge=0, lt=5)
    arm: Literal["baseline", "caveman", "if", "concise"]
    response_id: str | None
    hard_pass: bool
    semantic_success: bool
    terminal_zero_reason: TerminalZeroReason | None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    ordinary_uncached_input_tokens: int | None = Field(default=None, ge=0)
    applied_cache_control_status: AppliedCacheControlStatus
    cache_read_status: CacheReadStatus
    cache_write_status: CacheWriteStatus
    service_tier_status: ServiceTierStatus
    cache_policy_status: CachePolicyStatusV1
    total_tokens: int | None = Field(default=None, ge=0)
    visible_output_tokens: int | None = Field(default=None, ge=0)
    reconciled_cost_usd: Decimal | None = Field(default=None, ge=0)
    cost_availability: CostAvailabilityV1
    latency_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_terminal_projection(self) -> Self:
        provider_failure = self.terminal_zero_reason in {
            "provider_rejected",
            "retry_exhausted",
        }
        successful_zero = self.terminal_zero_reason in {"blank_response", "hard_fail"}
        if provider_failure:
            if self.response_id is not None or self.hard_pass or self.semantic_success:
                raise ValueError("provider failure projection mismatch")
            return self
        if self.response_id is None:
            raise ValueError("provider success requires response_id")
        if successful_zero:
            if self.hard_pass or self.semantic_success:
                raise ValueError("successful zero projection mismatch")
            return self
        if not self.hard_pass:
            raise ValueError("hard failure requires terminal_zero_reason")
        return self

    @model_validator(mode="after")
    def validate_cache_and_cost_projection(self) -> Self:
        cache_fields = (
            (self.cache_read_status, self.cache_read_tokens),
            (self.cache_write_status, self.cache_write_tokens),
        )
        for status, value in cache_fields:
            if status == "reported_zero" and value != 0:
                raise ValueError("reported_zero requires zero")
            if status == "reported_nonzero" and (value is None or value <= 0):
                raise ValueError("reported_nonzero requires a positive count")
            if status not in {"reported_zero", "reported_nonzero"} and value is not None:
                raise ValueError("missing/invalid/not-applicable cache status forbids a count")
        complete_cache_detail = all(
            status in {"reported_zero", "reported_nonzero"} for status, _ in cache_fields
        )
        if complete_cache_detail and self.input_tokens is not None:
            assert self.cache_read_tokens is not None
            assert self.cache_write_tokens is not None
            expected_ordinary_uncached = (
                self.input_tokens - self.cache_read_tokens - self.cache_write_tokens
            )
            if expected_ordinary_uncached < 0 or self.ordinary_uncached_input_tokens != expected_ordinary_uncached:
                raise ValueError("uncached input projection mismatch")
        elif self.ordinary_uncached_input_tokens is not None:
            raise ValueError("uncached input requires complete cache detail")
        if (self.cost_availability == "unavailable") != (self.reconciled_cost_usd is None):
            raise ValueError("cost availability/value mismatch")
        if self.response_id is not None and self.cache_write_status in {"missing", "invalid"}:
            if (
                self.cache_policy_status != "missing_write_detail"
                or self.cost_availability != "retained_worst_case"
            ):
                raise ValueError("missing cache-write detail must retain worst-case cost")
        if self.response_id is not None and self.cache_write_status.startswith("not_applicable_"):
            raise ValueError("explicit cache policy requires write accounting on success")
        if self.cache_write_status in {"reported_zero", "reported_nonzero"}:
            expected_status = (
                "conformant_zero_write"
                if self.cache_write_status == "reported_zero"
                else "forbidden_nonzero_write"
            )
            if self.cache_policy_status != expected_status:
                raise ValueError("cache-write policy status mismatch")
        elif self.response_id is None and self.cache_policy_status != "terminal_no_usage":
            raise ValueError("response-free terminal row requires terminal_no_usage")
        if self.cost_availability == "definitely_rejected_zero" and (
            self.response_id is not None or self.reconciled_cost_usd != 0
        ):
            raise ValueError("definitely rejected zero-cost projection mismatch")
        return self


class PairDenominatorsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    planned_pairs: Literal[120] = 120
    eligible_pairs: int = Field(ge=0, le=120)
    token_pairs: int = Field(ge=0, le=120)
    eligible_scenarios: int = Field(ge=0, le=12)


class AggregatedModelV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generation_model: str
    rows: tuple[PlannedObservationV1, ...]
    denominators_by_gate: Mapping[Literal["hard", "semantic"], PairDenominatorsV1]
    integrity_limitations: tuple[CacheIntegrityLimitationV1, ...]


def aggregate_verified_evidence(
    *,
    evidence: Sequence[VerifiedScoredCapsuleV2],
    hard_sets: Sequence[HardScoreRequestSetV1],
    judge_attachments: Sequence[JudgeAttachmentV1],
) -> tuple[AggregatedModelV1, ...]:
    """Verify all joins and emit one canonical 120-key arm table per generation model."""
~~~

Require a bijection over the canonical 120 keys in every model/arm. Provider rejection,
retry exhaustion, blank response, and deterministic hard failure produce `H = S = 0`.
Missing keys, unknown delivery, authentication stop, inconsistent returned model, duplicate key,
or unverifiable provenance raise `InferenceIntegrityError`; they are never zero-imputed.

Import `Self` and `model_validator` and class-bound revalidate every projected row. The terminal
matrix is exact: `provider_rejected` and `retry_exhausted` require `response_id=None` and
`H=S=0`; `blank_response` and `hard_fail` require a nonnull persisted response ID and `H=S=0`;
and `terminal_zero_reason=None` requires a nonnull response ID and `H=1`, while `S` may be either
the verified judge pass or fail. No other combination is valid. The two matrix tests must mutate
each of `response_id`, `hard_pass`, `semantic_success`, and `terminal_zero_reason` independently
and assert validation failure rather than relying only on the aggregation builder.

- [ ] **Step 4: Freeze token and pair eligibility formulas**

For every terminal success with complete usage, calculate exactly:

~~~python
visible_output_tokens = output_tokens - reasoning_tokens
~~~

Reject negative values. If either provider value is absent, leave visible tokens unavailable; do
not substitute billed output, total tokens, tokenizer estimates, or character counts. Preserve
provider cache reads and cache writes as separate accounting statuses and counts. Derive
`ordinary_uncached_input_tokens = input_tokens - cache_read_tokens - cache_write_tokens` only when both
cache details are reported; never infer a zero cache-write count from omission or fold writes into
cached/uncached input. Keep input, uncached input, cached reads, cache writes, visible output,
reasoning output, provider output, total, reconciled cost, cost availability, latency, and characters
as distinct fields.

The frozen explicit/no-breakpoint policy expects a reported zero write count. A terminal success
with missing write detail must retain the runtime ledger's worst-case amount with
`cost_availability="retained_worst_case"`, set `cache_policy_status="missing_write_detail"`, and add
`cache_write_detail_missing` to `AggregatedModelV1.integrity_limitations`. A reported nonzero write
remains immutable billable evidence, sets `forbidden_nonzero_write`, retains its reconciled charge,
and adds `forbidden_cache_write_observed`; it is not rewritten to zero. Both conditions propagate to
the campaign limitations and operational-integrity outcome instead of disappearing. Cache-write,
uncached-input, and cost fields are descriptive only and never enter visible-output computation,
pair eligibility, delta, bootstrap quality/brevity, or sensitivity assignment logic.

For a selected gate, a primary pair is eligible only when matched `if` and `concise` rows both pass
that gate. It is a token pair only when it is eligible and both visible-token values exist. Compute
`delta = visible_tokens(concise) - visible_tokens(if)`, so a positive value favors `if`.

- [ ] **Step 5: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_aggregation.py
uv run ruff check src/laconian_eval/benchmark/aggregation.py tests/benchmark/test_aggregation.py
uv run mypy src/laconian_eval/benchmark/aggregation.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/aggregation.py tests/benchmark/helpers.py tests/benchmark/test_aggregation.py
git commit -m "feat: aggregate fixed-denominator benchmark evidence"
~~~

### Task 6: Implement the frozen scenario-cluster bootstrap

**Files:**

- Create: `src/laconian_eval/benchmark/bootstrap.py`
- Create: `tests/benchmark/test_bootstrap.py`
- Modify: `src/laconian_eval/benchmark/aggregation.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`

- [ ] **Step 1: Write RNG, clustering, quantile, and invalidity tests**

Create tests named:

- `test_cluster_vectors_keep_locales_repetitions_and_matched_arms_together`.
- `test_type7_quantile_matches_frozen_golden_vector`.
- `test_cluster_bootstrap_recomputes_complete_estimator_per_replicate`.
- `test_fewer_than_9990_valid_replicates_is_inconclusive`.
- `test_bootstrap_interval_names_the_fixed_campaign_conditional_scenario_target`.
- `test_twelve_cluster_percentile_coverage_is_labelled_nominal_and_approximate`.

Commit literal golden scenario-index bytes and literal expected 0.025/0.975 quantiles in the test;
do not generate the expected values by calling the implementation under test.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_bootstrap.py
~~~

Expected: collection fails because `laconian_eval.benchmark.bootstrap` does not exist.

- [ ] **Step 3: Freeze bootstrap vectors and type-7 quantiles**

Implement:

~~~python
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_CLUSTER_COUNT = 12
BOOTSTRAP_MIN_VALID = 9_990


class BootstrapVectorsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = Field(ge=0, lt=2**128)
    scenario_uids: tuple[str, ...]
    replicates: Literal[10_000] = 10_000
    index_dtype: Literal["uint8"] = "uint8"
    indices_sha256: str


class BootstrapIntervalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    point: float | None
    lower: float | None
    upper: float | None
    valid_replicates: int = Field(ge=0, le=10_000)
    total_replicates: Literal[10_000] = 10_000
    available: bool
    inferential_target: Literal[
        "scenario-superpopulation-conditional-on-fixed-campaign"
    ] = "scenario-superpopulation-conditional-on-fixed-campaign"
    coverage: Literal[
        "nominal-95-percent-approximate-12-cluster-percentile"
    ] = "nominal-95-percent-approximate-12-cluster-percentile"


def make_cluster_vectors(*, seed: int, scenario_uids: Sequence[str]) -> tuple[BootstrapVectorsV1, NDArray[np.uint8]]:
    ordered = tuple(sorted(scenario_uids, key=lambda value: value.encode("utf-8")))
    if len(ordered) != 12 or len(set(ordered)) != 12:
        raise ValueError("exactly twelve distinct scenario UIDs are required")
    generator = np.random.Generator(np.random.PCG64(seed))
    indices = generator.integers(0, 12, size=(10_000, 12), dtype=np.uint8)
    return seal_vector_metadata(seed, ordered, indices), indices


def type7_quantile(values: NDArray[np.float64], q: float) -> float:
    ordered = np.sort(values)
    h = (len(ordered) - 1) * q
    j = math.floor(h)
    g = h - j
    return float(ordered[j] + g * (ordered[min(j + 1, len(ordered) - 1)] - ordered[j]))
~~~

The index digest uses canonical C-order bytes and binds dtype, shape, seed, and ordered scenario
UIDs. Loading rejects a digest mismatch rather than regenerating vectors implicitly.

- [ ] **Step 4: Recompute each complete estimator inside each replicate**

Expose:

~~~python
def cluster_percentile_interval(
    *,
    point: float | None,
    rows: Sequence[PlannedObservationV1],
    indices: NDArray[np.uint8],
    estimator: Callable[[Sequence[PlannedObservationV1]], float | None],
) -> BootstrapIntervalV1:
    """Rebuild sampled scenario blocks and return frozen type-7 percentile endpoints."""


def median_visible_delta(rows: Sequence[PlannedObservationV1], *, gate: GateName) -> float | None:
    """Return median concise-minus-if visible tokens among jointly eligible token pairs."""


def arm_pass_proportion(rows: Sequence[PlannedObservationV1], *, arm: ArmName, gate: GateName) -> float:
    """Return the selected gate successes over the fixed 120 planned observations."""


def paired_pass_rate_difference(rows: Sequence[PlannedObservationV1], *, gate: GateName) -> float:
    """Return mean if-minus-concise success over all 120 matched planned keys."""
~~~

Each sampled scenario block carries both locales, all repetitions, and every matched arm. Duplicate
sampled scenarios duplicate the whole block. Re-run pair eligibility and the median or mean after
sampling; do not resample already-computed deltas. Preserve ties. Quantiles use only finite valid
replicates. When valid count is below 9,990, return `available=False` with null endpoints.

The inferential target is variation across exchangeable scenarios represented by the preregistered
12-scenario corpus, conditional on the exact three generation models, provider versions, input-tag
commit, cases, locales, arms, repetitions, judge protocol, and completed campaign evidence. It does
not authorize inference to new models, provider versions, time periods, prompts, or task domains.
With only 12 independent clusters, the percentile endpoints are a nominal 95% approximate interval,
not an exact finite-sample 95% coverage guarantee. Persist both closed labels above in every interval
and render them adjacent to each inferential result.

- [ ] **Step 5: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_bootstrap.py tests/benchmark/test_aggregation.py
uv run ruff check src/laconian_eval/benchmark/bootstrap.py src/laconian_eval/benchmark/aggregation.py tests/benchmark
uv run mypy src/laconian_eval/benchmark/bootstrap.py src/laconian_eval/benchmark/aggregation.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/aggregation.py src/laconian_eval/benchmark/bootstrap.py tests/benchmark/test_bootstrap.py
git commit -m "feat: add frozen scenario-cluster bootstrap"
~~~

### Task 7: Encode strict model-outcome precedence

**Files:**

- Create: `src/laconian_eval/benchmark/outcomes.py`
- Create: `tests/benchmark/test_outcomes.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`

- [ ] **Step 1: Write precedence, multi-reason, and boundary tests**

Create tests named:

- `test_outcome_precedence_is_operational_invalid_then_negative_quality_then_brevity_then_supported`.
- `test_all_applicable_negative_reasons_are_retained`.
- `test_boundary_values_are_inconclusive_because_thresholds_are_strict`.

Use table rows where every lower-priority condition is simultaneously true, plus exact endpoints
`-0.05` and `0.0` to prove that equality never satisfies a strict interval decision.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_outcomes.py
~~~

Expected: collection fails because `laconian_eval.benchmark.outcomes` does not exist.

- [ ] **Step 3: Implement the closed outcome contract**

~~~python
class ModelOutcome(str, Enum):
    OPERATIONALLY_INVALID = "operationally-invalid"
    NEGATIVE_QUALITY = "negative-quality"
    NEGATIVE_BREVITY = "negative-brevity"
    SUPPORTED = "supported"
    INCONCLUSIVE = "inconclusive"


class OutcomeEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    integrity_valid: bool
    integrity_reasons: tuple[str, ...]
    coverage_valid: bool
    hard_quality: BootstrapIntervalV1
    semantic_sensitivity_min_lower: float | None
    semantic_sensitivity_max_upper: float | None
    token_sensitivity_min_lower: float | None
    token_sensitivity_max_upper: float | None
    audit_gate_passed: bool
    sensitivity_complete: bool


class ModelOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: ModelOutcome
    reasons: tuple[str, ...]


def classify_model_outcome(evidence: OutcomeEvidenceV1) -> ModelOutcomeV1:
    """Apply the frozen precedence and retain all applicable negative reasons."""
~~~

Apply this exact order:

1. Any protocol, identity, security, missing-ledger, inconsistent-model, ambiguous-delivery, or
   provenance failure returns `operationally-invalid`; do not issue a performance classification.
2. A hard-quality upper endpoint strictly below -0.05 establishes hard negative quality. Semantic
   negative quality additionally requires a complete sensitivity proof whose maximum semantic
   upper endpoint is strictly below -0.05.
3. With integrity, coverage, quality, model-specific audit, and complete sensitivity all passing,
   maximum token upper endpoint strictly below zero returns `negative-brevity`.
4. Under the same gates, minimum token lower endpoint strictly above zero returns `supported`.
5. Every other statistically valid case returns `inconclusive`.

Collect every applicable negative reason before selecting the highest-precedence outcome. Audit
failure makes semantic conclusions inconclusive, but does not suppress valid hard-quality
inferiority. Never aggregate the three generation-model outcomes into a family decision.

- [ ] **Step 4: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_outcomes.py
uv run ruff check src/laconian_eval/benchmark/outcomes.py tests/benchmark/test_outcomes.py
uv run mypy src/laconian_eval/benchmark/outcomes.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/outcomes.py tests/benchmark/test_outcomes.py
git commit -m "feat: classify benchmark model outcomes"
~~~

### Task 8: Seal benchmark provider indexes and select the exact 144-record human-audit sample

**Files:**

- Create: `src/laconian_eval/benchmark/audit_sampling.py`
- Create: `src/laconian_eval/benchmark/provider_evidence.py`
- Create: `tests/benchmark/test_provider_evidence.py`
- Create: `tests/benchmark/test_audit_sampling.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

`provider_evidence.py` is the downstream post-judge bridge and imports `context.py`; the exact path
lines above deliberately contain no commentary so task/staging audits can resolve them literally.

- [ ] **Step 1: Write exact-quota and blinding tests**

Create tests named:

- `test_generation_context_and_provider_index_bind_default_judge_service_tier_and_wire_field`.
- `test_generation_and_provider_indexes_bind_two_ordered_numeric_reviewer_accounts`.
- `test_protocol_attestations_bind_both_registry_digests_and_exact_role_identity`.
- `test_adapter_rejects_protocol_attestation_not_verified_against_role_fingerprint`.
- `test_provider_index_projection_and_loader_reject_workflow_root_substitution`.
- `test_provider_index_projection_and_loader_bind_authority_checked_statistical_protocol`.
- `test_provider_index_projection_and_loader_bind_exact_registry_audit_protocol`.
- `test_benchmark_neutral_records_do_not_duplicate_runtime_workflow_inventory_type`.
- `test_generation_and_provider_indexes_bind_exact_three_role_protocol_review_root`.
- `test_prepare_judge_requires_generation_context_index_before_provider_index_exists`.
- `test_provider_evidence_index_binds_plaintext_seed_commit_registry_and_four_layer_indexes`.
- `test_provider_index_copies_expectation_digest_and_bound_final_authority_root_without_serializing_capability`.
- `test_provider_writer_requires_the_same_live_expectation_wrapper_and_final_root`.
- `test_verified_provider_loader_requires_external_live_expectation_wrapper_and_never_mints_one`.
- `test_verified_provider_loader_rejects_expectation_predecessor_or_final_authority_mismatch`.
- `test_provider_evidence_index_rejects_wrong_seed_hash_self_hash_or_parent_vector`.
- `test_provider_loader_rejects_registry_binding_or_protocol_attestation_root_substitution`.
- `test_provider_loader_requires_explicit_index_and_rejects_seed_commit_or_root_substitution`.
- `test_provider_loader_requires_authority_bound_context_expectation_and_rejects_rehashed_forgery`.
- `test_slice4_adapter_can_construct_index_without_benchmark_importing_campaign`.
- `test_runtime_adapter_imports_context_and_provider_contracts_from_distinct_owner_modules`.
- `test_benchmark_provider_projection_loads_exact_four_layer_roots_and_attempt_root_vector`.
- `test_benchmark_provider_projection_rejects_missing_reordered_or_cross_parent_members`.
- `test_benchmark_provider_projection_is_campaign_package_independent_and_input_read_only`.
- `test_benchmark_provider_projection_preserves_cache_write_evidence_and_accounting_status`.
- `test_benchmark_provider_projection_preserves_closed_judge_service_tier_status`.
- `test_audit_population_is_a_bijection_over_verified_judged_records`.
- `test_audit_population_attachment_binds_every_provider_evidence_parent`.
- `test_audit_population_parents_require_exact_36_unique_index_aligned_chains`.
- `test_audit_population_reload_rejects_provider_projection_or_judge_parent_substitution`.
- `test_audit_population_writer_and_loader_use_the_same_exact_two_member_layout`.
- `test_audit_sample_has_144_records_six_per_stratum_and_all_critical_certainty_units`.
- `test_hamilton_allocation_and_global_fill_match_golden_manifest`.
- `test_certainty_overflow_expands_target_instead_of_subsampling`.
- `test_blind_packet_omits_model_arm_judge_tokens_and_provider_metadata`.
- `test_audit_sample_root_writer_loader_round_trip_exact_four_member_layout`.
- `test_audit_sample_root_writer_is_failure_atomic_no_replace_and_fresh_reloads`.
- `test_audit_sample_root_loader_rejects_extra_missing_alias_or_parent_substitution`.

The golden fixture must exercise both Hamilton branches, a full cell skipped during residual-seat
allocation, a fractional-remainder tie resolved by UTF-8 byte order, and at least two global-fill
passes.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_provider_evidence.py tests/benchmark/test_audit_sampling.py
~~~

Expected: imports fail because the downstream `provider_evidence.py` and `audit_sampling.py` do not
yet exist; the already-green Task 3 `context.py` suite remains unchanged.

- [ ] **Step 3: Add population, manifest, and blind-packet schemas**

Import the exact Task 3 context types and helpers from `laconian_eval.benchmark.context`; do not
redefine or re-export shadow copies. The block below begins only the downstream
`provider_evidence.py` and audit schemas. That module may import `context.py`, `hard_score.py`, and
`judge.py`; none of those earlier modules may import `provider_evidence.py`.
Import `AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`,
`ProviderMetadataString`, and `ServiceTierStatus` from their Foundations owner; never redeclare or
alias their vocabularies.

~~~python
class RequestedReturnedModelEvidenceV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    purpose: Literal["generation", "judge"]
    requested_model_id: Literal["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]
    returned_model_id: ProviderMetadataString
    returned_model_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class PublicBenchmarkCacheEvidenceV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    attempt_id: str = Field(pattern="^[0-9a-f]{64}$")
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    ordinary_uncached_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_read_status: CacheReadStatus
    cache_write_tokens: int | None = Field(default=None, ge=0)
    cache_write_status: CacheWriteStatus
    visible_output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    requested_service_tier: Literal["default"]
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    applied_cache_control_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_read_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_write_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    service_tier_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    usage_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reasoning_tokens_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ProviderEvidenceIndexV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-provider-evidence-index-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    input_tag_commit: str = Field(pattern="^[0-9a-f]{40}$")
    hard_scorer_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_requested_service_tier: Literal["default"]
    judge_service_tier_wire_field: Literal["service_tier"]
    corpus_case_root: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    estimand_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bootstrap_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    outcome_classification_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    false_fail_sensitivity_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    audit_reviewer_registry: AuditReviewerRegistryV1
    protocol_reviewer_registry: ProtocolReviewerRegistryV1
    protocol_attestations: tuple[
        ProtocolAttestationV1,
        ProtocolAttestationV1,
        ProtocolAttestationV1,
    ]
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bound_generation_complete_authority_root_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    requested_returned_model_ids: tuple[RequestedReturnedModelEvidenceV1, ...]
    generation_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    judge_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_closed_index(self) -> Self:
        exact_model_projection = (
            ("generation", "gpt-5.6-sol"),
            ("generation", "gpt-5.6-terra"),
            ("generation", "gpt-5.6-luna"),
            ("judge", "gpt-5.6-sol"),
        )
        if tuple(
            (item.purpose, item.requested_model_id)
            for item in self.requested_returned_model_ids
        ) != exact_model_projection:
            raise ValueError("provider index requested/returned model projection mismatch")
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("provider index requires 36 unique parents per bound source")
        reviewers = self.audit_reviewer_registry.reviewers
        reviewer_keys = tuple(reviewer.reviewer_id.encode("utf-8") for reviewer in reviewers)
        if (
            reviewer_keys != tuple(sorted(reviewer_keys))
            or len(set(reviewer_keys)) != 2
            or len({reviewer.reviewer_numeric_account_id for reviewer in reviewers}) != 2
            or len({reviewer.reviewer_login for reviewer in reviewers}) != 2
        ):
            raise ValueError("provider index requires two ordered distinct reviewers")
        if self.audit_reviewer_registry_sha256 != compute_audit_reviewer_registry_sha256(reviewers):
            raise ValueError("provider index reviewer registry digest mismatch")
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        if tuple(item.role for item in self.protocol_attestations) != expected_roles:
            raise ValueError("provider index requires the three ordered protocol review roles")
        if len({item.attestation_sha256 for item in self.protocol_attestations}) != 3:
            raise ValueError("provider index requires three distinct protocol reviews")
        protocol_reviewers = self.protocol_reviewer_registry.reviewers
        if tuple(reviewer.role for reviewer in protocol_reviewers) != expected_roles:
            raise ValueError("provider index protocol reviewer role order mismatch")
        if (
            len({reviewer.reviewer_numeric_account_id for reviewer in protocol_reviewers}) != 3
            or len({reviewer.reviewer_login for reviewer in protocol_reviewers}) != 3
        ):
            raise ValueError("provider index requires three distinct protocol reviewers")
        if self.protocol_reviewer_registry.protocol_reviewer_registry_sha256 != (
            compute_protocol_reviewer_registry_sha256(protocol_reviewers)
        ):
            raise ValueError("provider index protocol reviewer registry digest mismatch")
        for attestation, reviewer in zip(
            self.protocol_attestations,
            protocol_reviewers,
            strict=True,
        ):
            if (
                attestation.role != reviewer.role
                or attestation.reviewer_numeric_account_id != reviewer.reviewer_numeric_account_id
                or attestation.reviewer_login != reviewer.reviewer_login
                or attestation.protocol_registry_sha256
                != self.protocol_reviewer_registry.protocol_reviewer_registry_sha256
                or attestation.workflow_root
                != self.workflow_root
            ):
                raise ValueError("provider index protocol attestation identity mismatch")
        if self.protocol_attestations_root != (
            compute_protocol_attestations_root(self.protocol_attestations)
        ):
            raise ValueError("provider index protocol review root mismatch")
        expected_seed_sha256 = stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": self.campaign_seed,
            },
        )
        if self.campaign_seed_sha256 != expected_seed_sha256:
            raise ValueError("provider index campaign seed digest mismatch")
        expected_index_sha256 = stable_digest(
            "laconian-benchmark-provider-evidence-index-v1",
            self.model_dump(
                mode="json",
                exclude={"provider_evidence_index_sha256"},
            ),
        )
        if self.provider_evidence_index_sha256 != expected_index_sha256:
            raise ValueError("provider index self digest mismatch")
        return self


class BenchmarkProviderEvidenceProjectionV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-provider-evidence-v1"]
    campaign_id: str
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bound_generation_complete_authority_root_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    requested_returned_model_ids: tuple[RequestedReturnedModelEvidenceV1, ...]
    generation_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    judge_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    benchmark_provider_evidence_sha256: str

    @model_validator(mode="after")
    def require_unique_parent_vectors(self) -> Self:
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("provider projection requires 36 unique parents per bound source")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedBenchmarkProviderEvidenceV1:
    generation_expectation: VerifiedGenerationContextExpectationV1
    generation_context: VerifiedGenerationContextIndexV1
    index: ProviderEvidenceIndexV1
    projection: BenchmarkProviderEvidenceProjectionV1
    generation_evidence: tuple[VerifiedScoredCapsuleV2, ...]
    hard_score_request_sets: tuple[HardScoreRequestSetV1, ...]
    judge_request_attachments: tuple[JudgeRequestAttachmentV1, ...]
    judge_attempt_root: VerifiedJudgeAttemptRootV1
    judge_attachments: tuple[JudgeAttachmentV1, ...]


class AuditPopulationAttachmentV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["audit-population-attachment-v1"]
    campaign_id: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_evidence_index_sha256: str
    benchmark_provider_evidence_sha256: str
    judge_attempt_root_index_sha256: str
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    record_count: int = Field(ge=0, le=1_440)
    records_sha256: str
    population_attachment_sha256: str

    @model_validator(mode="after")
    def require_unique_parent_vectors(self) -> Self:
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("audit population requires 36 unique parents per bound source")
        return self


class AuditPopulationRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    canonical_record_id: str
    generation_capsule_sha256: str
    hard_score_request_set_sha256: str
    judge_request_attachment_sha256: str
    judge_attachment_sha256: str
    plan_item_id: str
    response_id: str
    judge_request_id: str
    generation_model: str
    scenario_uid: str
    locale: str
    repetition: int = Field(ge=0, lt=5)
    arm: Literal["baseline", "caveman", "if", "concise"]
    blinded_judge_decision: bool
    case_id: str
    case_category: str
    warning_severity: WarningSeverity | None
    prompt: str
    rubric: tuple[RubricItemV1, ...]
    material_warning_requirement: str | None
    candidate_response: str


class CellAllocationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cell_id: str
    noncertainty_population: int
    local_minimum: int
    proportional_numerator: int
    proportional_denominator: int
    floor_seats: int
    fractional_remainder: RationalV1
    residual_rank: int | None
    global_fill_passes: tuple[int, ...]
    selected_noncertainty: int
    seed: int
    permutation: tuple[str, ...]
    inclusion_probability: RationalV1


class AuditSampleManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["audit-sample-manifest-v1"]
    campaign_id: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    population_attachment_sha256: str
    target: int = Field(ge=144)
    total_certainty_count: int = Field(ge=0)
    certainty_record_ids: tuple[str, ...]
    stratum_quotas: Mapping[str, int]
    cells: tuple[CellAllocationV1, ...]
    ordered_selected_record_ids: tuple[str, ...]
    sample_manifest_sha256: str


class BlindAuditRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    audit_record_id: str
    prompt: str
    rubric: tuple[RubricItemV1, ...]
    material_warning_requirement: str | None
    warning_severity: WarningSeverity | None
    locale: str
    candidate_response: str


class BlindAuditPacketV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sample_manifest_sha256: str
    records: tuple[BlindAuditRecordV1, ...]
    packet_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedAuditPopulationV1:
    attachment: AuditPopulationAttachmentV1
    records: tuple[AuditPopulationRecordV1, ...]


@dataclass(frozen=True, slots=True)
class VerifiedAuditSampleRootV1:
    population: VerifiedAuditPopulationV1
    manifest: AuditSampleManifestV1
    packet: BlindAuditPacketV1
    audit_sample_root_sha256: str
~~~

- [ ] **Step 4: Build and verify the complete audit population**

Implement these exact boundaries:

~~~python
def write_provider_evidence_index(
    provider_index_path: Path,
    index: ProviderEvidenceIndexV1,
    *,
    generation_expectation: VerifiedGenerationContextExpectationV1,
) -> None:
    """Match live expectation, revalidate, and no-replace write one canonical provider index."""


def load_provider_evidence_index(
    provider_index_path: Path,
) -> ProviderEvidenceIndexV1:
    """Load the canonical index and recompute seed, registries, roots, and self digest."""


def load_verified_benchmark_provider_evidence(
    *,
    provider_index_path: Path,
    generation_root: Path,
    hard_score_root: Path,
    judge_request_root: Path,
    judge_attempt_root: Path,
    judge_root: Path,
    generation_expectation: VerifiedGenerationContextExpectationV1,
) -> VerifiedBenchmarkProviderEvidenceV1:
    """Verify the live capability, four layer roots, and separate attempt root."""


def build_audit_population(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    """Derive the complete judged-record population from one verified 36-chain projection."""


def write_audit_population(
    audit_root: Path,
    population: VerifiedAuditPopulationV1,
) -> None:
    """Write only population-attachment.json and population.jsonl beneath audit_root."""


def load_verified_audit_population(
    audit_root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    """Reload those same two files and rederive them from the expected provider parents."""
~~~

`LayerRootIndexV1` is the only accepted root-index byte schema. Its fixed locations are
`GENERATION/generation/index.json`, `HARD/hard-score/index.json`,
`REQUESTS/judge-requests/index.json`, and `JUDGES/judge/index.json`. Each member path is a canonical
UTF-8 POSIX-relative path beneath the retained root descriptor; absolute paths, empty/dot segments,
backslashes, aliases, symlinks, and duplicate paths/inodes are rejected. The 36 members are ordered
by `(generation_model UTF-8 bytes, scenario_uid raw SHA-256 bytes)` with ordinals 0 through 35, and
the discriminated member kind must equal the index kind. A generation member binds both explicit
`capsule_relative_path`/SealV1 capsule hash and
`scored_sidecar_relative_path`/canonical sidecar-file hash; neither path is derived from the other.
The generation-context loader passes those exact two retained-descriptor children to
`load_verified_scored_capsule` and compares both hashes and the resulting model/scenario identity.
Each other kind binds one exact attachment path/hash. The kind-local layer loader class-bound
revalidates each attachment, recomputes its canonical bytes/self hash, and checks model/scenario
identity; it cannot claim cross-layer parent verification from only a root and kind. The
parent-aware producer and `load_verified_benchmark_provider_evidence` subsequently call the exact
attachment verifier with the already verified preceding-layer objects and reject every internal
parent mismatch. The index digest uses
domain `laconian-benchmark-layer-root-index-v1` and excludes only
`layer_root_index_sha256`; changing a path is therefore an integrity change even when file bytes are
copied. The Slice 3 `GENERATION_COMPLETE` adapter produces the generation index after verifying all
36 Slice 1 capsule/sidecar pairs. Runtime's campaign-side `Runtime.hard_score`,
`Runtime.prepare_judge`, and `Runtime.seal_judge` functions respectively produce the other
three indexes in the same transaction as their 36 attachment files by calling the neutral library
APIs directly. No standalone command synthesizes an index by directory enumeration during a later
phase. The layer loader owns the exact allowlist inside its
kind subdirectory only. The complete generation-root loader additionally permits exactly
`generation-context.json`; the complete hard-score and judge-request roots permit only their single
kind subdirectory; and the complete judge-root loader additionally permits exactly
`provider-evidence-index.json`. Every complete-root loader rejects the standalone CLI's
`offline-non-evidentiary.json` marker, so replay bytes cannot be promoted into a live parent by
renaming or copying. No layer loader mistakes required bound sibling files for an unexpected layer
member.

At `GENERATION_COMPLETE`, before any blind judge request exists, the Slice 3 runtime Task 7 adapter
also constructs `GenerationContextIndexV1` from the verified `CampaignRegistryV1` and the just-sealed
generation layer index, then writes it at the fixed canonical path
`GENERATION/generation-context.json` via `write_generation_context_index`. Its self digest uses domain
`laconian-benchmark-generation-context-index-v1`. In the same authority transition it writes the
separate fixed expectation file described in Task 3 and binds that file's digest into the final
authority root. The campaign-side stage adapter verifies both authority roots and supplies the
in-memory `VerifiedGenerationContextExpectationV1`; the benchmark command surface cannot construct
that wrapper from argv. `load_verified_generation_context_index` requires that wrapper plus the
explicit context file, derives the expected context digest only from the wrapper, recomputes the campaign-seed and context digests, reloads the generation
`LayerRootIndexV1`, requires kind `generation`, campaign/digest/vector equality, and verifies each of
the 36 capsule/sidecar parents. The adapter obtains `hard_scorer_source_sha256`,
`hard_score_protocol_sha256`, `judge_protocol_sha256`, `judge_prompt_sha256`,
`judge_schema_sha256`, `estimand_protocol_sha256`, `statistical_protocol_sha256`, the singular
`audit_protocol_sha256`,
`bootstrap_protocol_sha256`, `outcome_classification_protocol_sha256`,
`false_fail_sensitivity_protocol_sha256`, `audit_sampling_protocol_sha256`,
`audit_commit_reveal_protocol_sha256`, and `audit_adjudication_protocol_sha256` only from Runtime's
class-bound, tagged, verified C0 code/protocol inventory
under the same `workflow_root`; Evaluation carries those neutral hashes and root
but never duplicates or imports the Runtime inventory type. The context self digest binds every
field, and context loading rejects any source/protocol/root substitution before any hard-score
attachment can be built.

The two-person audit reviewer-registry projection is exact and shared with Slice 3: its bytes are
`canonical_json_v1({"schema_version": "benchmark-reviewer-registry-v1", "reviewers":
[reviewer.model_dump(mode="json") for reviewer in reviewers]})`, where reviewers are in
bytewise reviewer-ID order. `canonical_reviewer_registry_bytes` first class-bound revalidates both
strict bindings and rejects duplicate reviewer IDs, account IDs, or exact logins;
`compute_audit_reviewer_registry_sha256` is raw SHA-256 over those no-newline bytes. Each binding
contains the numeric account ID, exact login, literal audit role, closed verification mode, and
mode-dependent null, uppercase OpenPGP, or `SHA256:` SSH fingerprint. The Slice 3 adapter copies those complete
bindings from the verified `CampaignRegistryV1`, independently regenerates the canonical bytes,
requires byte equality with the registry's retained projection, and recomputes rather than copies
`audit_reviewer_registry_sha256`. A field hash with different binding bytes is invalid.

Protocol reviewers are a separate authority population and never enter those bytes or change that
digest. Slice 3 adds a strict tagged `protocol-reviewers.yaml`; its benchmark projection is
`ProtocolReviewerRegistryV1` with exactly three distinct non-bot identities in role order
`statistical_method`, `blind_judge_audit_protocol`, `security_evidence`, each carrying numeric
account ID, exact login, required signing-verification mode, and its exact mode-discriminated
fingerprint. GitHub mode requires null; keyed modes require nonnull; `security_evidence` always
requires nonnull and therefore cannot use GitHub mode. Its exact bytes are
`canonical_json_v1({"schema_version": "benchmark-protocol-reviewer-registry-v1",
"reviewers": [item.model_dump(mode="json") for item in protocol_reviewers]})`, and its independent raw SHA-256 is
`protocol_reviewer_registry_sha256`. The Runtime input-package loader owns both source YAML files and
retains both canonical projections; substituting either population never silently changes the
other's digest.

The adapter copies that complete protocol registry plus exactly three
`ProtocolAttestationV1` records from the verified campaign registry. Each attestation repeats its
role, numeric account ID/login, verification mode/fingerprint, the separate protocol-registry
digest, complete exact role subject inventory, and the same verified C0 `workflow_root`; all must
match the corresponding role-bound protocol reviewer and generation-context root. The generation
context, not the attestation schema, separately repeats the audit-registry digest. Their root is
`canonical_json_v1_digest("laconian-protocol-review-attestations-root-v1",
[binding.model_dump(mode="json") for binding in attestations])`; duplicate record hashes, a missing
or fourth role, role/identity reordering, either registry mismatch, or root mismatch fails. Thus the generation context binds the
runtime's exact three-role review authorization, not an assumed two-reviewer audit count. This is
accepted only after the Slice 3 registry loader has cryptographically verified each attestation's
signed commit or detached proof under its role binding and exact required fingerprint, including
`security_evidence`; a copied fingerprint or `signature_verified` Boolean is not a verified source
binding. The attestation hash carried here must be the digest of that complete verified source
record, including the workflow root. Evaluation deliberately carries only this neutral verified
SHA-256: Runtime remains the sole owner of the 15-member workflow inventory schema, canonical-byte
loader, and member verification, and no Runtime or campaign inventory type is duplicated or
imported below `laconian_eval.benchmark`. This is
the only context from which Runtime's `Runtime.prepare_judge` obtains the
plaintext seed, peeled input commit, judge protocol, literal requested service tier `default`, or
literal wire field `service_tier` and from which Runtime's `Runtime.seal_judge` obtains the singular
`audit_protocol_sha256`, reviewer registry, or protocol-review root. None may come from a post-judge index, CLI scalar,
environment variable, generation attachment field, or hash inversion.

`ProviderEvidenceIndexV1` is the sole benchmark-owned bridge for values that cannot be inferred from
the four evidence roots. After all four roots are sealed, Runtime's Slice 3-facing
`Runtime.seal_judge` adapter must
construct it only from the fully verified `GenerationContextIndexV1` plus the exact canonical index
bytes at the four supplied roots: the context's plaintext campaign seed and `seed_sha256`, peeled
input commit, judge and statistics protocol hashes, singular `audit_protocol_sha256`, verified C0 workflow-inventory root, the
hard-scorer source and hard-score protocol hashes,
audit-registry digest and both exact audit
reviewer bindings, the exact requested judge service tier/wire field, the complete separate
three-role protocol-reviewer registry, the exact three
ordered protocol-attestation bindings/root, the authority-bound generation-context expectation
digest (never the expectation object), bound `GENERATION_COMPLETE` authority-root digest, and
context digest, plus all four
layer-root-index digests/four ordered 36-member attachment vectors and the separately verified
`JudgeAttemptRootIndexV1` digest/ordered 36 boundary hashes. It canonical-byte compares every
generation-context value and the generation root/vector, recomputes both registry hashes and the
protocol-review root from the copied bindings,
before construction. It then calls
`write_provider_evidence_index`; the writer
requires the same verified in-memory expectation wrapper, compares its expectation digest and bound
final authority root with the index, class-bound revalidates, canonicalizes, fsyncs, and
installs the single file without replacement.
There is no command or library overload accepting a raw seed, raw commit, independently supplied
vector, or inferred parent value in place of this file.
The requested/returned model projection is exactly four entries in order: generation
`gpt-5.6-sol`, generation `gpt-5.6-terra`, generation `gpt-5.6-luna`, judge `gpt-5.6-sol`.
Construction compares every successful response in each entry and rejects two different returned
IDs; a returned ID need not equal its requested ID. Each returned value binds the digest of the
exact `response.model` source independently of cache, tier, usage, and reasoning sources.
The attempt root is a sealed source-provenance parent, not a fifth published evidence layer:
Runtime's `Runtime.seal_judge` obtains its digest/vector only from
`VerifiedJudgeAttemptRootV1`, and every emitted judge record names its exact successful attempt
hash. Later provider loaders carry that immutable root and
vector through the projection, thereby binding every closed service-tier status including
retryable `not_applicable_definitely_rejected` 429s, usage-free
`not_applicable_definitely_not_sent` failures, and terminal `missing|mismatch` incidents;
accepted judge records independently repeat `reported_default`. Slice 4 must match them to the verified `judge_attempt_batch`
artifact/inventory before provenance sealing. No later command may invent or replace them.

Slice 4 may independently construct the identical generation context and provider index from its
verified `CampaignRegistryV1`, the same authority-bound generation-context expectation, and the
same exact roots, then canonical-byte compare its result with
the Slice 3 files. Campaign-side code
imports `ProviderEvidenceIndexV1`; `provider_evidence.py` never imports a campaign type. Slice 4 may
then wrap `benchmark_provider_evidence_sha256` in `EvidenceInventoryV1`, but that inventory is neither
an input to sampling nor a way to reverse the dependency. The adapter/interface test imports the
benchmark model from a fake campaign-side module and statically proves that
`laconian_eval.benchmark.provider_evidence` has no `laconian_eval.campaign` import.

`load_verified_benchmark_provider_evidence` is the only constructor for the verified dataclass. It
requires `provider_index_path` to be the exact retained-descriptor child
`judge_root/provider-evidence-index.json`, requires the caller's
`generation_expectation: VerifiedGenerationContextExpectationV1`, calls
`load_provider_evidence_index`, and opens the exact four layer roots plus the separate
`judge_attempt_root` read-only. After verifying the judge-request attachments, it calls
`load_verified_judge_attempt_root(judge_attempt_root,
expected_request_root_index_sha256=provider_index.judge_request_root_index_sha256,
request_attachments=judge_request_attachments)`, retains that
`VerifiedJudgeAttemptRootV1` in the returned wrapper, and requires its index digest and ordered 36
boundary hashes to equal the provider index and projection. The provider index must
contain only `generation_context_expectation_sha256`, the context and layer roots, and the bound
final authority-root digest copied by Runtime's live `Runtime.seal_judge`; it must not nest or copy
`GenerationContextExpectationV1`. The loader compares those digests and the bound final root to the
externally supplied in-memory wrapper, then requires the provider index and projection to repeat the
expectation/context digests exactly. The expected context, two reviewer registries, attestation,
workflow, and generation-layer roots from that supplied wrapper/context must match the freshly
loaded context. The loader never constructs a verified wrapper from serialized provider-index
fields.
`load_provider_evidence_index` is structural only: it parses/recomputes the serialized index and
never calls a verified context/root loader or constructs any `Verified*` wrapper. It does not
confer workflow authority. A live caller first reconstructs the Runtime authority wrapper and
compares the provider-index digest with the
`JUDGE_COMPLETE`/`PROVIDER_EVIDENCE_VERIFIED` authority record. The loader then calls
`load_verified_generation_context_index` with the supplied wrapper on the fixed
`generation_root/generation-context.json` child and requires its complete fields and digest to equal
the provider index, including the exact workflow-inventory root, both audit reviewer bindings/their
independently recomputed canonical-byte registry hash, the distinct protocol-reviewer registry/hash,
all three ordered protocol-review bindings/root, the exact `default`/`service_tier` pair, and the
tagged statistics protocol hash plus singular `audit_protocol_sha256` later required by analysis and
audit evidence; this is a fixed parent
verification, not caller inference. It recomputes and
byte-compares each root's canonical index digest to the corresponding
`*_root_index_sha256`, then requires exactly 36 unique generation capsules, 36 unique hard-score
sets, 36 unique judge-request attachments, and 36 unique judge attachments in canonical
`(generation_model UTF-8 bytes, scenario_uid raw SHA-256 bytes)` order. At every index require one
campaign/model/scenario chain, then call `load_verified_scored_capsule`,
`verify_hard_score_request_set(hard_score_set, context=generation_context,
expectation=generation_expectation, boundary_ordinal=ordinal)`,
`verify_judge_request_attachment(judge_request_attachment, context=generation_context,
expectation=generation_expectation, boundary_ordinal=ordinal, request_set=hard_score_set)`, and
`verify_judge_attachment(judge_attachment, context=generation_context,
expectation=generation_expectation, request_set=hard_score_set,
request_attachment=judge_request_attachment)`. The provider index's generation vector must equal the ordered
`GenerationLayerRootMemberV1.generation_capsule_sha256` values; each other vector must equal the
corresponding ordered `AttachmentLayerRootMemberV1.attachment_sha256` values. Every campaign ID,
judge protocol hash, requested service-tier/wire-field pair, judge-request campaign-seed hash, four
parent link, and ordered attachment digest must exactly equal the explicit provider index. Every
request wrapper and judge attachment must carry `default`/`service_tier`, and every accepted
`JudgeRecordV1` must carry returned tier `default` plus tier status `reported_default`; a
missing/nondefault tier is retained only as terminal attempt/STOP and worst-case spend evidence and
can never enter the judge root. Definite pre-response rejection remains exact
`not_applicable_definitely_rejected` attempt evidence and may follow the verified structured-429
retry path; it is never mislabeled as a missing returned tier. The
loader never recovers plaintext seed or input commit from an attachment, hashes, CLI values, sibling
directory, or caller inference. It builds a projection that copies the provider-index digest, four
layer-root-index digests/vectors, the generation-context expectation/context digests, the bound
`GENERATION_COMPLETE` authority root, the judge-attempt root digest/vector, and the exact
`workflow_root`, `statistical_protocol_sha256`, and the singular `audit_protocol_sha256`. The
projection self-digest excludes only
`benchmark_provider_evidence_sha256` and uses domain
`laconian-benchmark-provider-evidence-v1`. This module must not import
`laconian_eval.campaign`, GitHub locators, workflow inventory records, deployments, or spend-ledger
types. Projection construction and every provider/audit loader reject a projection, generation
context, provider index, or any one of the three attestations whose workflow root differs, even
when all substituted objects are internally self-hashed.
The projection must preserve each scored attempt's independent cache-read count/status/source,
cache-write count/status/source, applied-control mode/TTL/status/source, service-tier status/source,
usage/reasoning sources, requested/returned model mapping, and reconciled cost basis. Missing or forbidden write evidence is
retained for the integrity limitation path; it is never filtered merely to make the projection
eligible for analysis.

Class-bound revalidate the provider index, projection, and every parent again in both
audit-population entry points. The population attachment must copy
`provider_evidence_index_sha256`, `benchmark_provider_evidence_sha256`, and the four exact ordered
layer hash vectors plus the exact judge-attempt root digest and ordered boundary vector. A missing,
duplicate, extra, reordered, substituted, or cross-parent member is an
integrity error, including a self-consistent population presented with the wrong provider index,
wrong benchmark projection digest, or any one of the 36 wrong judge parents.

The builder emits exactly one row for every judged hard-pass response and no other row.
`canonical_record_id` binds campaign, all four parent attachment hashes, plan item, response,
and judge-request ID. It rejects a missing, duplicate, extra, reordered, or cross-parent record.

Serialize records as canonical byte-sorted JSONL. `records_sha256` hashes those exact bytes;
`population_attachment_sha256` uses domain
`laconian-audit-population-attachment-v1` over every preceding attachment field. Implement
`write_audit_population` with no-replace/fsync semantics. The loader reads exactly
`audit_root/population-attachment.json` and `audit_root/population.jsonl`, rejects noncanonical
bytes, missing files, aliases, symlinks, and any attachment/record/parent mismatch, and byte-compares
the loaded result with `build_audit_population(provider_evidence=provider_evidence)`. It does not
reject the other allowlisted audit files that may share `audit_root`; the complete audit loader owns
that directory allowlist. The returned population is the only accepted input to sampling.

- [ ] **Step 5: Implement certainty selection, Hamilton allocation, and global fill**

Expose:

~~~python
def select_audit_sample(
    *,
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> tuple[AuditSampleManifestV1, BlindAuditPacketV1]:
    """Apply certainty, exact Hamilton, frozen cell permutations, and global fill."""
~~~

Class-bound revalidate both arguments, require the population's campaign, provider-index digest,
projection digest, four layer-parent vectors, and judge-attempt root/vector to equal `provider_evidence.index` and
`provider_evidence.projection`, and use only `provider_evidence.index.campaign_seed`,
`provider_evidence.index.input_tag_commit`, and `provider_evidence.index.judge_protocol_sha256` for
sampling. Neither sampling nor sample verification accepts those three values separately.
Use exactly 24 base strata `(generation model, locale, arm)`, initial quota six each. Select every
judge-pass `safety-medical` record in `if` and `concise` as a certainty unit with inclusion
probability 1. For stratum s, compute:

~~~text
q_s = max(0, min(6 - c_s, N_s))
~~~

where c_s is certainty count and N_s is noncertainty population. Split noncertainty units into
cells `(generation model, locale, arm, blinded judge decision)`. If q_s is at least the count of
nonempty cells, assign one seat to each and use Hamilton largest remainder over remaining capacity.
Otherwise apply Hamilton without minima. Compute every quota and remainder with integers and
`RationalV1`; sort residuals by descending exact fraction, then bytewise cell ID, skipping full
cells.

Within each cell sort canonical record IDs bytewise, then permute with
`Generator(PCG64(derive_seed128("laconian-human-audit-v1/cell/" + cell_id,
campaign_seed, input_tag_commit, judge_protocol_sha256)))`. Set total target to
`max(144, total_certainty_count)`. Fill a shortfall one record
per pass over bytewise cell IDs, skipping full cells, until target or population exhaustion. Select
the first n_h records from each frozen permutation. Record all N_h, n_h, capacities, minima,
floors, exact remainders, tie ranks, global passes, seeds, permutations, certainty flags, and exact
inclusion probabilities.

Derive opaque audit IDs from campaign ID, sample-manifest hash precursor, and canonical record ID.
The packet schema must make it impossible to serialize model, arm, record order, response length,
tokens, latency, judge decision, cost, or provider metadata.

- [ ] **Step 6: Add verifier tests and implementation**

Create tests named
`test_sample_verifier_recomputes_seeds_permutations_quotas_probabilities_and_digest` and
`test_sample_verifier_rejects_duplicate_or_unrepresented_population_record`.

Then implement:

~~~python
def verify_audit_sample(
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
    *,
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> None:
    """Recompute the complete design and compare canonical bytes, not selected IDs alone."""


def write_audit_sample_root(
    output_root: Path,
    *,
    population: VerifiedAuditPopulationV1,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditSampleRootV1:
    """Atomically write and fresh-reload the fixed four-member audit-sample root."""


def load_verified_audit_sample_root(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditSampleRootV1:
    """Reload exactly four sample members and rederive population, design, and root digest."""
~~~

The sample root layout is exactly:

~~~text
root/audit/population-attachment.json
root/audit/population.jsonl
root/audit/sample-manifest.json
root/audit/blind-packet.json
~~~

`audit_sample_root_sha256` is
`stable_digest("laconian-audit-sample-root-v1",
{"population_attachment_sha256": population.attachment.population_attachment_sha256,
"records_sha256": population.attachment.records_sha256,
"sample_manifest_sha256": manifest.sample_manifest_sha256,
"blind_packet_sha256": packet.packet_sha256})` in that fixed field order. The writer class-bound
revalidates every argument, calls `verify_audit_sample`, stages
only beneath an operation-owned empty sibling of an absent `output_root`, emits the four canonical
members with final newlines, fsyncs every file and directory, installs without replacement, and
returns only the result of a fresh `load_verified_audit_sample_root` call. The loader descriptor-
opens that exact allowlist, rejects extras/missing files/symlinks/aliases/noncanonical bytes, calls
`load_verified_audit_population(root / "audit", provider_evidence=provider_evidence)`, replays
`verify_audit_sample`, recomputes the root digest, and returns the frozen wrapper. Neither function
accepts a raw seed, index digest, or caller-asserted verified Boolean. On failure the writer removes
only its validated staging directory and leaves the destination absent.
Export `VerifiedAuditSampleRootV1`, `write_audit_sample_root`, and
`load_verified_audit_sample_root` from their owner `laconian_eval.benchmark.audit_sampling` and
re-export those exact objects from `laconian_eval.benchmark`; do not define adapter aliases.

- [ ] **Step 7: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_provider_evidence.py tests/benchmark/test_audit_sampling.py
uv run ruff check src/laconian_eval/benchmark/provider_evidence.py src/laconian_eval/benchmark/audit_sampling.py tests/benchmark/test_provider_evidence.py tests/benchmark/test_audit_sampling.py
uv run mypy src/laconian_eval/benchmark/provider_evidence.py src/laconian_eval/benchmark/audit_sampling.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/provider_evidence.py src/laconian_eval/benchmark/audit_sampling.py tests/benchmark/helpers.py tests/benchmark/test_provider_evidence.py tests/benchmark/test_audit_sampling.py
git commit -m "feat: verify benchmark evidence and freeze audit sampling"
~~~

### Task 9: Verify two-person commit-reveal and immutable adjudication

**Files:**

- Create: `src/laconian_eval/benchmark/audit_commit_reveal.py`
- Create: `tests/benchmark/test_audit_commit_reveal.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write canonical-byte and PR-ordering tests**

Create tests named:

- `test_commitment_matches_domain_header_salt_and_exact_canonical_jsonl_bytes`
- `test_commitment_artifact_does_not_disclose_salt_or_labels`
- `test_reveal_rejects_actor_mismatch_modified_commitment_duplicate_or_missing_label`
- `test_reviewer_identity_binds_positive_account_id_login_and_reviewer_registry_digest`
- `test_all_github_identity_and_proof_ids_reject_strings_booleans_and_zero`
- `test_account_id_mismatch_or_login_rename_requires_a_new_reviewer_registry`
- `test_reviewer_chain_runs_required_git_commit_verification_mode_and_matches_fingerprint`
- `test_audit_chain_recomputes_registry_hash_from_provider_bindings_not_hash_only`
- `test_reveal_requires_both_commitment_merges_in_its_ancestry`
- `test_adjudication_core_digest_binds_reveals_consensus_without_a_signoff_cycle`
- `test_each_signoff_replays_exact_github_review_provenance_for_the_core_head`
- `test_exact_github_review_record_digest_is_recomputed_offline_from_stable_api_fields`
- `test_pr_or_review_numeric_actor_id_mismatch_rejects_even_when_login_matches`
- `test_reviewer_chain_digest_binds_identity_numeric_actors_and_both_pr_proofs`
- `test_final_adjudication_envelope_hash_binds_core_signoffs_and_pr_proof`
- `test_missing_or_stale_signoff_rejects_final_envelope_and_blocks_audit_seal`

The ancestry fixture must include one graph in which reviewer A reveals after only A's commitment
merged and prove rejection, then add reviewer B's merge as an ancestor and prove acceptance. The
byte fixture must include non-ASCII evidence and a final newline so newline normalization changes
the commitment. The adjudication fixture independently computes the core hash before either review,
then mutates each repository, PR, review, actor-account ID, actor login, state, reviewed head, fixed
body hash, API-record digest, and final envelope field to prove there is no self-referential digest
and no trusted Boolean signoff shortcut. A dedicated fixture keeps the login text fixed while
substituting the numeric account ID, and another keeps the numeric ID fixed while renaming the login;
both fail closed against the immutable `reviewers.yaml` registry until a new input tag is approved.
For every reviewer, actor, merge actor, repository, PR, and review ID, also mutate a positive integer
to its numeric string, `True`, zero, and a negative integer and require strict validation failure.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_audit_commit_reveal.py
~~~

Expected: collection fails because `laconian_eval.benchmark.audit_commit_reveal` does not exist.

- [ ] **Step 3: Freeze reviewer labels and commitment bytes**

Implement these closed schemas:

~~~python
class ReviewerIdentityV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    reviewer_id: str
    reviewer_numeric_account_id: int = Field(gt=0)
    reviewer_login: str
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: str | None = Field(
        default=None,
        pattern=r"^(?:[0-9A-F]{40}|[0-9A-F]{64}|SHA256:[A-Za-z0-9+/]{43})$",
    )
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class HumanAuditLabelV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    audit_record_id: str
    rubric_items: tuple[RubricItemJudgmentV1, ...]
    material_warning: WarningJudgmentV1 | None
    material_contradiction: bool
    contradiction_evidence: str | None = Field(default=None, max_length=1_000)
    semantic_pass: bool


class CommitmentHeaderV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["audit-commitment-v1"]
    campaign_id: str
    reviewer_id: str
    sample_manifest_sha256: str


class ReviewerCommitmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    header: CommitmentHeaderV1
    commitment_sha256: str


def canonical_label_jsonl(labels: Sequence[HumanAuditLabelV1]) -> bytes:
    """Sort by UTF-8 audit ID, emit one canonical JSON object per line and one final newline."""


def compute_commitment(
    *, header: CommitmentHeaderV1, salt: bytes, exact_label_bytes: bytes
) -> str:
    """Require a 32-byte salt and return the fixed commitment digest defined below."""
~~~

Use this exact preimage:

~~~text
SHA256(
  UTF8("laconian-audit-commitment-v1") || NUL ||
  canonical_json(header) || NUL ||
  salt_32_bytes || NUL ||
  exact_canonical_label_jsonl_bytes
)
~~~

The commitment file contains only the header and `commitment_sha256`. Human labels must cover the
blind packet exactly once in bytewise audit-ID order; validate each derived semantic decision with
the same rule used for the judge.

- [ ] **Step 4: Bind reveal and pull-request provenance**

~~~python
class PullRequestProofV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    repository_id: int = Field(gt=0)
    pr_number: int = Field(gt=0)
    actor_account_id: int = Field(gt=0)
    actor: str
    base_sha: str = Field(pattern="^[0-9a-f]{40}$")
    head_sha: str = Field(pattern="^[0-9a-f]{40}$")
    merge_commit_sha: str = Field(pattern="^[0-9a-f]{40}$")
    merge_actor_account_id: int = Field(gt=0)
    merge_actor: str
    verification_mode: SignatureVerificationModeV1
    head_signing_fingerprint: str | None
    signature_evidence: SignatureEvidenceV1
    changed_paths: tuple[str, ...]
    exact_pr_api_record_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    pull_request_proof_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ReviewerRevealV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["audit-reveal-v1"]
    campaign_id: str
    reviewer_id: str
    sample_manifest_sha256: str
    commitment_sha256: str
    salt_hex: str
    labels_byte_length: int = Field(gt=0)
    labels_sha256: str
    labels: tuple[HumanAuditLabelV1, ...]
    reveal_sha256: str


class ReviewerChainV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    identity: ReviewerIdentityV1
    commitment: ReviewerCommitmentV1
    commitment_pr: PullRequestProofV1
    reveal: ReviewerRevealV1
    reveal_pr: PullRequestProofV1
    reviewer_chain_proof_sha256: str = Field(pattern="^[0-9a-f]{64}$")


def verify_reviewer_chain(
    chain: ReviewerChainV1,
    *,
    other_commitment_merge_sha: str,
    packet: BlindAuditPacketV1,
    expected_reviewer: ReviewerAccountBindingV1,
    expected_audit_reviewer_registry_sha256: str,
    git_object_database: Path,
) -> None:
    """Verify identity, signature, paths, immutable bytes, commitment, order, and coverage."""
~~~

The only changed commitment path is
`benchmarks/audits/<campaign-id>/commitments/<reviewer-id>.json`; the reveal PR adds only immutable
files under `benchmarks/audits/<campaign-id>/reveals/<reviewer-id>/`. Identity registry digest,
numeric GitHub account ID, login, commit-signing verification mode, and optional fingerprint must
exactly equal the corresponding binding in
`provider_evidence.index.audit_reviewer_registry.reviewers`; every
commitment/reveal PR actor must match both that numeric account ID and login. Before accepting either
PR proof, `verify_reviewer_chain` uses its fixed Git object reader over `git_object_database` to
parse commit/tree/parent objects and compute ancestry itself. It verifies exact mode-discriminated
`SignatureEvidenceV1`: captured GitHub verification with `verified=true`, `reason=valid`, numeric
ID/login and null fingerprint, or keyed SSH/OpenPGP verification with the exact registry
fingerprint. No injected ancestry/signature callback, caller-supplied Boolean, GitHub badge text, or
copied fingerprint authorizes the chain. A login
rename is not silently followed: even with the same stable account ID it requires a newly reviewed
registry and input tag. The PR proof also binds the numeric repository ID and merge-actor account
ID/login from the captured API record. Recompute `exact_pr_api_record_sha256` from the canonical
stable GitHub API projection, then compute `pull_request_proof_sha256` with domain
`laconian-audit-pull-request-proof-v1` over every preceding proof field. Both reviewers' commitment
merge SHAs must be ancestors of each
reveal head and reveal merge commit. The original commitment blob hash must remain unchanged.
`reviewer_chain_proof_sha256` uses domain `laconian-audit-reviewer-chain-proof-v1` over every
preceding chain field, so both identity/registry fields and both complete PR proofs are immutable.
Before any identity comparison, both `verify_reviewer_chain` and `verify_audit_chain` class-bound
revalidate the expected two reviewers, regenerate `canonical_reviewer_registry_bytes`, recompute raw
`audit_reviewer_registry_sha256`, and require that value to equal the provider index, every identity,
signoff, and audit attachment. A self-consistent substituted hash without the exact two binding
bytes therefore fails closed.

- [ ] **Step 5: Seal adjudication without exposing judge labels**

~~~python
class ConsensusLabelV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    audit_record_id: str
    semantic_pass: bool | None
    resolution: Literal["reviewer-agreement", "adjudicated", "unresolved"]
    rationale: str | None = Field(default=None, max_length=2_000)


class AuditAdjudicationCoreV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["audit-adjudication-core-v1"]
    campaign_id: str
    sample_manifest_sha256: str
    reveal_sha256s: tuple[str, str]
    consensus: tuple[ConsensusLabelV1, ...]
    judge_labels_were_available: Literal[False] = False
    adjudication_core_sha256: str


class ExactGitHubReviewRecordV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["audit-github-review-record-v1"]
    repository_id: int = Field(gt=0)
    pr_number: int = Field(gt=0)
    review_id: int = Field(gt=0)
    actor_account_id: int = Field(gt=0)
    actor_login: str
    reviewed_head_sha: str = Field(pattern="^[0-9a-f]{40}$")
    body: str
    state: Literal["APPROVED"]
    submitted_at_utc: AwareDatetime
    exact_api_record_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ExactGitHubReviewSignoffV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["audit-adjudication-github-review-v1"]
    reviewer_id: str
    reviewer_numeric_account_id: int = Field(gt=0)
    reviewer_login: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    adjudication_core_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    repository_id: int = Field(gt=0)
    pr_number: int = Field(gt=0)
    review_id: int = Field(gt=0)
    state: Literal["APPROVED"]
    reviewed_head_sha: str = Field(pattern="^[0-9a-f]{40}$")
    submitted_at_utc: AwareDatetime
    fixed_body_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    exact_api_record_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    signoff_proof_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class AuditAdjudicationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["audit-adjudication-v1"]
    core: AuditAdjudicationCoreV1
    signoffs: tuple[ExactGitHubReviewSignoffV1, ExactGitHubReviewSignoffV1]
    adjudication_pr: PullRequestProofV1
    adjudication_sha256: str


def verify_audit_chain(
    *,
    identities: tuple[ReviewerIdentityV1, ReviewerIdentityV1],
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    adjudication: AuditAdjudicationV1,
    packet: BlindAuditPacketV1,
    expected_reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
    expected_audit_reviewer_registry_sha256: str,
    git_object_database: Path,
    github_review_records: tuple[ExactGitHubReviewRecordV1, ExactGitHubReviewRecordV1],
) -> None:
    """Verify reveal chains, core, exact review proofs, final envelope, and append-only PRs."""
~~~

Agreement rows derive consensus without a rationale. Disagreements require either one bounded
rationale and a Boolean consensus or explicit unresolved status with null consensus. Compute
`adjudication_core_sha256` with domain `laconian-audit-adjudication-core-v1` over every preceding core
field before requesting either review. The adjudication PR head contains the exact canonical core
file and both reveal merges in its ancestry.

Each preregistered reviewer then submits an exact GitHub `APPROVED` review on that same immutable
head. The only permitted body bytes are
`b"laconian-audit-adjudication-core-v1\0" + core_hash_ascii + b"\n"`; bind their SHA-256, exact
repository/PR/review IDs, numeric actor account ID, actor login, reviewed commit, state, submission
time, reviewer-registry digest, and API-record digest in `ExactGitHubReviewSignoffV1`.
The private helper has the exact boundary
`load_exact_github_review(captured_records: tuple[ExactGitHubReviewRecordV1,
ExactGitHubReviewRecordV1], *, repository_id: int, pr_number: int,
review_id: int) -> ExactGitHubReviewRecordV1`. It retrieves the canonical captured record by those
exact numeric IDs, validates `ExactGitHubReviewRecordV1`, recomputes
`exact_api_record_sha256` with domain `laconian-audit-github-review-record-v1` over every preceding
field, and canonical-byte compare every duplicated signoff field. It also recomputes
`fixed_body_sha256` from the record's exact UTF-8 body. No network call, mutable login-only lookup, or
caller-supplied `signature_verified` Boolean is accepted during offline reload. Both distinct
preregistered account IDs/logins must approve the exact core head after both reveals and before the
adjudication PR merges.

Only after those proofs exist, compute `adjudication_sha256` with domain
`laconian-audit-adjudication-v1` over `core`, both bytewise-reviewer-ordered signoff proofs, and the
adjudication PR proof, excluding only the final hash. Thus neither signoff references the final
envelope digest and no digest cycle exists. A missing, stale, unverified, or wrong-head signoff
rejects the final envelope and blocks `AUDIT_SEALED`; it is never converted into an accepted
adjudicated consensus. Bind numeric repository/PR/review and actor IDs, actor logins,
reviewer-registry digest, base/head/merge SHAs, merge actors, independently verified fingerprints, exact
API-record digests, and file hashes in the verified result.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_audit_commit_reveal.py
uv run ruff check src/laconian_eval/benchmark/audit_commit_reveal.py tests/benchmark/test_audit_commit_reveal.py
uv run mypy src/laconian_eval/benchmark/audit_commit_reveal.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/audit_commit_reveal.py tests/benchmark/helpers.py tests/benchmark/test_audit_commit_reveal.py
git commit -m "feat: verify human-audit commit reveal"
~~~

### Task 10: Compute design-weighted audit metrics and model-specific gates

**Files:**

- Create: `src/laconian_eval/benchmark/audit_metrics.py`
- Create: `tests/benchmark/test_audit_metrics.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`

- [ ] **Step 1: Write weight, two-sided Wilson, denominator, and gate tests**

Create tests named:

- `test_design_weights_are_one_for_certainty_and_population_over_sample_for_noncertainty`
- `test_hajek_agreement_false_pass_and_false_fail_use_their_exact_denominators`
- `test_two_sided_design_weighted_wilson_matches_frozen_decimal_endpoints_and_z`
- `test_two_sided_wilson_retains_nonzero_uncertainty_after_zero_errors_or_perfect_agreement`
- `test_reported_false_fail_wilson_upper_is_the_only_u_authorized_for_sensitivity`
- `test_empty_stratum_low_effective_n_zero_denominator_or_unresolved_consensus_is_inconclusive`
- `test_binary_percentile_resampling_is_rejected_for_audit_gate_uncertainty`
- `test_weighted_kappa_reports_complete_confusion_without_an_interval`
- `test_model_gate_uses_primary_arm_point_thresholds_available_intervals_and_critical_coverage`
- `test_model_audit_metric_digest_binds_protocols_weights_intervals_and_all_primary_arm_metrics`

Use `Fraction` assertions for weights and weighted counts. For every Wilson endpoint use fixed
`Decimal` strings at 15 significant digits from an independently frozen hand calculation. The zero-
error fixture asserts `point == lower == 0` and `upper > 0`; the perfect-agreement fixture asserts
`point == upper == 1` and `lower < 1`. Neither test derives its expected endpoint with the production
helper.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_audit_metrics.py
~~~

Expected: collection fails because `laconian_eval.benchmark.audit_metrics` does not exist.

- [ ] **Step 3: Reconstruct exact design weights and weighted confusion tables**

Implement:

~~~python
class WeightedConfusionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pass_pass: RationalV1
    pass_fail: RationalV1
    fail_pass: RationalV1
    fail_fail: RationalV1


class WeightedProportionV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    numerator: RationalV1
    denominator: RationalV1
    point: Decimal | None
    effective_n: Decimal | None
    lower: Decimal | None
    upper: Decimal | None
    available: bool
    confidence_level: Literal["two-sided-0.95"] = "two-sided-0.95"
    z: Decimal
    interval_method: Literal["design-weighted-wilson-score-v1"]
    authorization_use: Literal["audit-gate", "false-fail-sensitivity", "reported-only"]
    unavailable_reasons: tuple[
        Literal[
            "zero_denominator",
            "empty_required_stratum",
            "effective_sample_size_below_one",
            "unresolved_sampled_consensus",
        ],
        ...,
    ]

    @model_validator(mode="after")
    def validate_interval_state(self) -> Self:
        if self.z != Decimal("1.959963984540054"):
            raise ValueError("Wilson z value mismatch")
        numeric = (self.point, self.effective_n, self.lower, self.upper)
        if self.available:
            if any(value is None for value in numeric) or self.unavailable_reasons:
                raise ValueError("available Wilson interval is incomplete")
            assert self.point is not None and self.effective_n is not None
            assert self.lower is not None and self.upper is not None
            if not (Decimal(0) <= self.lower <= self.point <= self.upper <= Decimal(1)):
                raise ValueError("Wilson interval order/range mismatch")
            if self.effective_n < Decimal(1):
                raise ValueError("available Wilson interval requires n_eff >= 1")
        elif any(value is not None for value in numeric) or not self.unavailable_reasons:
            raise ValueError("unavailable Wilson interval state mismatch")
        return self


class ModelAuditMetricsV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    generation_model: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    weights_by_record: Mapping[str, RationalV1]
    judge_consensus_confusion: WeightedConfusionV1
    reviewer_confusion: WeightedConfusionV1
    agreement: WeightedProportionV1
    false_pass: WeightedProportionV1
    false_fail_by_primary_arm: Mapping[Literal["if", "concise"], WeightedProportionV1]
    reviewer_agreement: WeightedProportionV1
    weighted_kappa: Decimal | None
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")


def compute_model_audit_metrics(
    *,
    model: str,
    manifest: AuditSampleManifestV1,
    population: Sequence[AuditPopulationRecordV1],
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    adjudication: AuditAdjudicationV1,
) -> ModelAuditMetricsV1:
    """Join opaque IDs to sealed population only after consensus is immutable, then weight."""
~~~

For a certainty unit use weight 1. For a noncertainty unit in cell h use exact
`w_h = N_h / n_h`, with N_h and n_h excluding certainty units. Compute:

~~~text
agreement = sum(w * I[judge = consensus]) / sum(w)
false_pass = sum(w * I[judge = pass and consensus = fail])
             / sum(w * I[judge = pass])
false_fail = sum(w * I[judge = fail and consensus = pass])
             / sum(w * I[judge = fail])
~~~

False-fail point estimates and intervals remain separate for each `(generation model, primary arm)`.
Human-human agreement and kappa use the full design-weighted reviewer confusion table. Compute weighted kappa as
`(p_observed - p_expected) / (1 - p_expected)` and return null when its denominator is zero; it has
no interval.

Metrics may read consensus only from `adjudication.core.consensus` after
`verify_audit_chain` has independently verified both exact review signoffs and the final envelope.
Neither the unreviewed core alone nor a signoff Boolean is an accepted metrics input. Copy
`protocol_bindings` only from the verified sample/population parent, require its exact singular
`audit_protocol_sha256` and every other field to agree, and compute `model_audit_metric_sha256` with
domain `laconian-model-audit-metric-v1` over every preceding field.

- [ ] **Step 4: Implement the authorizing two-sided design-weighted Wilson interval**

For the records in a proportion's denominator, calculate:

~~~text
sum_w = sum(w)
n_eff = sum(w)^2 / sum(w^2)
p = weighted_numerator / sum_w
z = 1.959963984540054
center = (p + z^2 / (2*n_eff)) / (1 + z^2/n_eff)
half = z/(1 + z^2/n_eff) * sqrt(p*(1-p)/n_eff + z^2/(4*n_eff^2))
interval = [max(0, center-half), min(1, center+half)]
~~~

Use a fixed high-precision local `decimal.Context`; never convert weights through binary floats.
An empty required stratum, `n_eff < 1`, zero denominator, or unresolved consensus makes the affected
measure unavailable with the corresponding closed reason. Every available interval is labeled
`design-weighted-wilson-score-v1`, `two-sided-0.95`, and the exact frozen z value. It is the sole
authorizing audit-uncertainty construction: agreement and false-pass use
`authorization_use="audit-gate"`; each primary-arm false-fail proportion uses
`authorization_use="false-fail-sensitivity"`; reviewer agreement uses `reported-only`.

The confirmatory gate still applies the preregistered point-estimate thresholds, but it cannot pass
unless the corresponding two-sided Wilson intervals are available. For sensitivity, define
`U_{m,a}` as the reported upper endpoint of that same model/arm two-sided Wilson interval. No
alternate interval inversion, familywise adjustment, delete-one/jackknife bound, normal approximation,
or binary percentile resampling may authorize the gate, supply U, set K, prune the sensitivity
search, or alter an outcome. Tests inspect the implementation call graph to prove there is exactly
one audit-interval constructor and that only its stored upper endpoint flows to Task 11.

- [ ] **Step 5: Encode the confirmatory gate per generation model**

~~~python
class ModelAuditGateV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generation_model: str
    agreement_interval_available: bool
    false_pass_interval_available: bool
    agreement_at_least_90_percent: bool
    false_pass_at_most_5_percent: bool
    no_unresolved_disagreement: bool
    critical_primary_coverage_complete: bool
    no_critical_primary_false_pass: bool
    passed: bool
    reasons: tuple[str, ...]


def evaluate_model_audit_gate(
    *,
    metrics: ModelAuditMetricsV1,
    manifest: AuditSampleManifestV1,
    population: Sequence[AuditPopulationRecordV1],
    adjudication: AuditAdjudicationV1,
) -> ModelAuditGateV1:
    """Use only this model's if/concise strata and retain every failed reason."""
~~~

The point-estimate gate is `agreement >= 0.90`, `false_pass <= 0.05`, both authorizing two-sided
Wilson intervals available, no unresolved reviewer
disagreement, 100% coverage of judge-pass primary-arm critical `safety-medical` records, and no
false pass on either preregistered critical warning. Baseline, Caveman, other models, and
campaign-wide aggregates are exploratory and cannot rescue the gate. `passed` is the conjunction of
all seven Boolean fields; retain every false condition as a closed reason.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_audit_metrics.py
uv run ruff check src/laconian_eval/benchmark/audit_metrics.py tests/benchmark/test_audit_metrics.py
uv run mypy src/laconian_eval/benchmark/audit_metrics.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/audit_metrics.py tests/benchmark/test_audit_metrics.py
git commit -m "feat: compute weighted human-audit metrics"
~~~

### Task 11: Enumerate bounded model/arm false-fail assignments exactly

**Files:**

- Create: `src/laconian_eval/benchmark/sensitivity.py`
- Create: `tests/benchmark/test_sensitivity_direct.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write M/D/U/K and direct-enumeration tests**

Create tests named:

- `test_false_fail_limits_use_model_arm_m_d_u_and_closed_k_formula`
- `test_false_fail_limit_uses_authorizing_two_sided_design_weighted_wilson_upper`
- `test_both_primary_arm_limits_require_the_same_model_audit_metric_digest`
- `test_known_false_fails_are_forced_and_every_other_judge_fail_row_is_optional`
- `test_zero_judge_fail_rows_produce_k_zero_without_an_interval`
- `test_unestimable_upper_bound_makes_model_sensitivity_inconclusive`
- `test_assignment_count_matches_literal_product_of_binomial_sums`
- `test_decimal_wilson_upper_at_k_boundary_is_ceiled_without_binary_float_rounding`
- `test_direct_enumeration_matches_literal_four_extrema_and_assignment_hashes`
- `test_each_assignment_recomputes_s_eligibility_and_both_bootstrap_intervals`
- `test_assignment_space_above_4096_refuses_direct_enumeration`
- `test_nonexhausted_sensitivity_result_forbids_an_exhaustion_reason`

The golden direct fixture must make a reclassified `if` row create a newly eligible token pair and
make a reclassified `concise` row change semantic quality in the opposite direction. Freeze all
four expected endpoints and their attaining assignment digests as literals.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_sensitivity_direct.py
~~~

Expected: collection fails because `laconian_eval.benchmark.sensitivity` does not exist.

- [ ] **Step 3: Implement exact per-model/per-arm limits**

~~~python
class FalseFailCandidateV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    response_id: str
    generation_model: str
    arm: Literal["if", "concise"]
    scenario_uid: str
    planned_key: str
    known_false_fail: bool


class FalseFailLimitV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generation_model: str
    arm: Literal["if", "concise"]
    m_all_judge_fail: int = Field(ge=0, le=120)
    d_known_false_fail: int = Field(ge=0, le=120)
    optional_candidates: int = Field(ge=0, le=120)
    upper_false_fail: Decimal | None
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    k_max_reclassified: int = Field(ge=0, le=120)
    estimable: bool


def derive_false_fail_limit(
    *,
    model: str,
    arm: Literal["if", "concise"],
    candidates: Sequence[FalseFailCandidateV1],
    metrics: ModelAuditMetricsV1,
) -> FalseFailLimitV1:
    """Select this arm's authorizing Wilson upper from one metric record and derive M/D/K."""
~~~

Use:

~~~text
M = count(all judge-fail rows for this model and arm)
D = count(audited judge-fail rows whose immutable consensus is pass)
optional_candidates = M - D = count(all remaining judge-fail rows)
if M = 0: K = 0 and estimable = true
if M > 0 and the two-sided design-weighted Wilson interval is unavailable: estimable = false
otherwise: U = metrics.false_fail_by_primary_arm[arm].upper and
           K = min(M, max(D, ceil(U * M)))
~~~

`derive_false_fail_limit` first class-bound revalidates `metrics`, requires its model, selects the
requested arm's `authorization_use="false-fail-sensitivity"` proportion, and copies
`model_audit_metric_sha256` into the limit. Derive both primary-arm limits from the same metrics
object; sensitivity input validation rejects different metric digests even when each limit is
otherwise internally valid. Use `Decimal` ceiling under the same fixed high-precision context as
Task 10 and never round U through binary float.

Every `known_false_fail=True` row is mandatory in every assignment. Every one of the other `M-D`
judge-fail rows is an optional reclassification candidate—including an audited consensus-fail row—
exactly matching the frozen assignment formula below. A sampled unresolved record makes the model inconclusive before candidate
construction. Reject `optional_candidates != M-D`, `K < D`, U outside `[0, 1]`, duplicate or missing candidate rows,
different metric digests, an interval with any other authorization use/method, or any candidate not
backed by an H=1 judge-fail row.

- [ ] **Step 4: Count and enumerate the feasible product space**

Compute exactly for each model:

~~~text
A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})
~~~

Implement that literal product in production and in an independent golden test with Python integers;
do not substitute a count over a differently filtered candidate pool. Direct enumeration is
permitted only when `A_m <= 4096`. For each arm, order its `M-D` optional candidates by UTF-8
response ID, enumerate total reclassified cardinality `j` ascending, and enumerate combinations in
lexicographic index order for `if`, followed by `concise`. Prefix the D forced IDs before the selected
optional IDs. The assignment digest is the domain digest of canonical sorted reclassified IDs, the
forced/optional partition, and both limits.

- [ ] **Step 5: Recompute and retain all four extrema**

~~~python
class SensitivityExtremumV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float
    assignment_sha256: str


SensitivityExhaustionReason = Literal[
    "visited_node_cap",
    "bootstrap_evaluation_cap",
]


class SensitivityResultV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    generation_model: str
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    assignment_count: int = Field(ge=0)
    visited_nodes: int = Field(ge=0)
    evaluated_assignments: int = Field(ge=0)
    semantic_min_lower: SensitivityExtremumV1 | None
    semantic_max_upper: SensitivityExtremumV1 | None
    token_min_lower: SensitivityExtremumV1 | None
    token_max_upper: SensitivityExtremumV1 | None
    search_exhausted: bool
    exhaustion_reason: SensitivityExhaustionReason | None
    certificate_sha256: str | None

    @model_validator(mode="after")
    def validate_exhaustion_state(self) -> Self:
        extrema = (
            self.semantic_min_lower,
            self.semantic_max_upper,
            self.token_min_lower,
            self.token_max_upper,
        )
        if self.search_exhausted:
            if (
                self.exhaustion_reason is None
                or any(extremum is not None for extremum in extrema)
                or self.certificate_sha256 is not None
            ):
                raise ValueError("exhausted search must discard uncertified outputs")
            if (
                self.exhaustion_reason == "visited_node_cap"
                and self.visited_nodes != 1_000_000
            ):
                raise ValueError("visited-node exhaustion counter mismatch")
            if self.exhaustion_reason == "bootstrap_evaluation_cap" and (
                self.evaluated_assignments != 4_096 or self.visited_nodes >= 1_000_000
            ):
                raise ValueError("bootstrap exhaustion counter mismatch")
        elif self.exhaustion_reason is not None:
            raise ValueError("completed search cannot have exhaustion_reason")
        return self


def enumerate_sensitivity_exact(
    *,
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> SensitivityResultV1:
    """Enumerate every feasible assignment when A_m is at most 4096."""
~~~

Both limit entries must be in exact `(if, concise)` order, match the aggregate model, and carry one
identical nonblank `model_audit_metric_sha256`; copy that digest into `SensitivityResultV1`. Direct
enumeration, certified search, certificate verification, analysis loading, and reporting all reject
a mixed-metric pair even when both individual arm limits are otherwise internally valid.

For each assignment set `S=1` on mandatory and selected false-fail rows, leave H unchanged, and
recompute the semantic paired rate-difference interval, semantic eligibility, token-pair
eligibility, and visible-token interval with the same frozen 10,000 vectors. Retain minimum
semantic lower, maximum semantic upper, minimum token lower, and maximum token upper. If a token
interval is unavailable for any feasible assignment, the corresponding directional extremum is
unavailable; do not drop the assignment.

Direct enumeration always returns `search_exhausted=False`, `exhaustion_reason=None`, and
`certificate_sha256=None`; its literal extrema tests must assert all three fields as well as the
four endpoint values.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_sensitivity_direct.py
uv run ruff check src/laconian_eval/benchmark/sensitivity.py tests/benchmark/test_sensitivity_direct.py
uv run mypy src/laconian_eval/benchmark/sensitivity.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/sensitivity.py tests/benchmark/helpers.py tests/benchmark/test_sensitivity_direct.py
git commit -m "feat: enumerate exact false-fail sensitivity"
~~~

### Task 12: Add verifier-checked exact branch-and-bound certificates

**Files:**

- Modify: `src/laconian_eval/benchmark/sensitivity.py`
- Create: `tests/benchmark/test_sensitivity_certificate.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write proof-partition, soundness, and deterministic-cap tests**

Create tests named:

- `test_certificate_verifies_cardinality_pruned_subtrees_and_every_feasible_leaf`
- `test_certificate_rejects_missing_overlapping_or_wrong_cardinality_subtree`
- `test_v1_schema_rejects_semantic_or_token_dominance_pruning`
- `test_certificate_rejects_wrong_leaf_extremum_or_bootstrap_vector_digest`
- `test_certificate_digest_precedes_result_reference_without_a_hash_cycle`
- `test_direct_and_certified_search_return_identical_extrema_on_overlap_space`
- `test_m_equals_k_120_exhausts_at_exact_caps_and_discards_partial_extrema`
- `test_each_search_cap_emits_its_closed_reason_and_no_certificate`
- `test_sensitivity_result_rejects_unknown_or_inconsistent_exhaustion_reason`

The cap fixtures use `M=K=120` and `D=0` for both arms, so each literal optional pool has `M-D=120`
and the independent formula oracle yields `A_m = 2^240`; they set the operation caps to the normative values and
exercise each guard independently. Assert exactly 1,000,000 visited nodes with
`exhaustion_reason="visited_node_cap"` or exactly 4,096 evaluated leaves with
`exhaustion_reason="bootstrap_evaluation_cap"`, `search_exhausted=True`, a null certificate, and
all four published extrema null even when an incumbent was found earlier. Unknown reasons, a reason
when `search_exhausted=False`, a reason inconsistent with its exact cap counter, or any
extremum/certificate on an exhausted result must fail model validation.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_sensitivity_certificate.py
~~~

Expected: tests fail because the certificate schemas and branch-and-bound entry point are absent.

- [ ] **Step 3: Implement the frozen traversal, counters, and certificate schemas**

~~~python
MAX_VISITED_NODES = 1_000_000
MAX_BOOTSTRAP_LEAVES = 4_096


class PrunedSubtreeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prefix_bits: str = Field(pattern="^[01]*$")
    selected_by_arm: Mapping[Literal["if", "concise"], int]
    remaining_by_arm: Mapping[Literal["if", "concise"], int]
    assignment_count: int = Field(gt=0)
    reason: Literal["cardinality-infeasible"]


class EvaluatedLeafV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    assignment_sha256: str
    selected_response_ids: tuple[str, ...]
    semantic_lower: float | None
    semantic_upper: float | None
    token_lower: float | None
    token_upper: float | None


class SensitivityCertificateV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["sensitivity-certificate-v1"]
    generation_model: str
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    candidate_order: tuple[str, ...]
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1]
    bootstrap_vectors_sha256: str
    visited_nodes: int = Field(ge=0, le=1_000_000)
    evaluated_leaves: tuple[EvaluatedLeafV1, ...]
    pruned_subtrees: tuple[PrunedSubtreeV1, ...]
    semantic_min_lower: SensitivityExtremumV1 | None
    semantic_max_upper: SensitivityExtremumV1 | None
    token_min_lower: SensitivityExtremumV1 | None
    token_max_upper: SensitivityExtremumV1 | None
    certificate_sha256: str
~~~

Traverse optional candidates in UTF-8 response-ID order with a deterministic depth-first tree,
exclude child before include child. Count the root and every entered prefix as one visited node;
count a complete feasible assignment immediately before running its 10,000-vector evaluation.
Cardinality-infeasible nodes do not consume a leaf evaluation.

On a complete partition, compute the four certificate extrema first and hash the certificate with
domain `laconian-sensitivity-certificate-v1`, excluding only `certificate_sha256`. Only then build
`SensitivityResultV1` with those same four extrema and the resulting certificate digest. The
certificate never embeds a result that points back to it, so there is no circular preimage.
Before traversal, require both ordered limits to carry the same model-audit metric digest and copy it
to the certificate; the verifier independently repeats this comparison and requires the returned
result to carry that same digest.

- [ ] **Step 4: Implement only mechanically exact cardinality pruning in v1**

For each prefix over the UTF-8-ordered `M-D` optional rows, first prune when an arm already has more
than `K-D` optional selections or cannot complete a cardinality in `0..K-D`. Its subtree assignment
count must use the residual form of the same literal identity
`A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})`; the certificate
verifier independently recomputes that integer and proves the disjoint evaluated-leaf plus pruned-
subtree counts sum to it exactly.

Do not implement semantic-bound, token-bound, incumbent, or dominance pruning in v1. The interaction
among reclassification, matched-pair eligibility, medians, missing token intervals, and type-7
bootstrap endpoints makes a locally plausible token bound insufficient. Every cardinality-feasible
leaf must receive the full 10,000-vector evaluation. `PrunedSubtreeV1` deliberately has no objective
bounds and rejects any reason other than `cardinality-infeasible`; producer and verifier tests must
also reject extra “witness” fields. A future schema version may add dominance only with an exact,
independently replayable witness proving the full endpoint bound and matched-record coupling. Until
then, a space with more than 4,096 feasible leaves necessarily exhausts the bootstrap-evaluation cap
and is inconclusive, which is preferable to an unsound certified extremum.

- [ ] **Step 5: Implement an independent exact certificate verifier**

~~~python
def search_sensitivity_exact(
    *,
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> tuple[SensitivityResultV1, SensitivityCertificateV1 | None]:
    """Run deterministic certified search when A_m exceeds 4096."""


def verify_sensitivity_certificate(
    certificate: SensitivityCertificateV1,
    *,
    aggregate: AggregatedModelV1,
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> SensitivityResultV1:
    """Reconstruct the full tree partition and independently verify every proof and leaf."""
~~~

The verifier recomputes candidate order, forced/optional partitions, limits, vector digest,
cardinality-infeasible subtree counts, every feasible leaf result, disjointness, and exhaustive
coverage of the assignment space. It recomputes extrema solely from verified leaves and compares
canonical bytes. It must not trust counters, accept an objective bound, omit a forced D row, or
permit a selected row outside the exact `M-D` optional pool.

If either normative cap is reached before an exhaustive verified partition exists, return
`search_exhausted=True`, publish both counters and the closed reason for the guard that prevented
the next logical operation, return no `SensitivityCertificateV1`, and set all four extrema and the
certificate digest to null. Check the visited-node guard before the leaf-evaluation guard so a tie
deterministically reports `visited_node_cap`. Partial incumbents must not enter outcome
classification. A completed certified search returns `exhaustion_reason=None` and a nonnull
certificate whose digest equals the result field.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_sensitivity_direct.py tests/benchmark/test_sensitivity_certificate.py
uv run ruff check src/laconian_eval/benchmark/sensitivity.py tests/benchmark/test_sensitivity_direct.py tests/benchmark/test_sensitivity_certificate.py
uv run mypy src/laconian_eval/benchmark/sensitivity.py
~~~

Expected: all commands pass, including the exact-cap fixture.

~~~bash
git add src/laconian_eval/benchmark/sensitivity.py tests/benchmark/helpers.py tests/benchmark/test_sensitivity_certificate.py
git commit -m "feat: certify bounded false-fail sensitivity"
~~~

### Task 13: Seal audit and machine-analysis roots, verified loaders, and the public report

**Files:**

- Create: `src/laconian_eval/benchmark/reporting.py`
- Create: `tests/benchmark/test_reporting.py`
- Modify: `src/laconian_eval/benchmark/__init__.py`
- Modify: `tests/benchmark/helpers.py`

- [ ] **Step 1: Write model-analysis, artifact, loader, and rendering tests**

Create tests named:

- `test_report_places_intervals_denominators_missingness_and_direction_adjacent`
- `test_report_labels_bootstrap_target_and_nominal_approximate_twelve_cluster_coverage`
- `test_visible_tokens_are_never_labelled_billed_output_or_cost_savings`
- `test_report_keeps_cache_reads_writes_uncached_input_and_cost_availability_separate`
- `test_report_surfaces_missing_or_forbidden_cache_write_integrity_limitations`
- `test_usage_status_maps_are_closed_complete_and_sum_to_120_per_arm`
- `test_report_discloses_audit_weights_confusion_intervals_and_search_caps`
- `test_report_uses_two_sided_design_weighted_wilson_for_gate_and_false_fail_u`
- `test_report_never_renders_candidate_or_judge_text_as_markdown`
- `test_analysis_writers_are_canonical_failure_atomic_and_no_replace`
- `test_audit_evidence_writer_is_canonical_failure_atomic_no_replace_and_fresh_reloads`
- `test_audit_evidence_writer_emits_exact_allowlist_and_copies_sample_bytes_unchanged`
- `test_analysis_writer_copies_verified_audit_parent_into_combined_result_root`
- `test_verified_audit_loader_recomputes_every_component_and_root_digest`
- `test_verified_audit_loader_recomputes_canonical_github_review_records_offline`
- `test_verified_audit_loader_rejects_missing_extra_or_mismatched_review_record`
- `test_verified_audit_loader_rejects_reviewer_chain_proof_or_account_identity_substitution`
- `test_audit_attachment_directly_binds_all_four_layer_vectors_and_judge_attempt_vector`
- `test_verified_audit_loader_rejects_provider_projection_or_any_of_36_judge_parent_substitutions`
- `test_verified_analysis_loader_rejects_report_bootstrap_or_attachment_substitution`
- `test_verified_analysis_loader_rejects_analysis_only_root_without_bound_audit_tree`
- `test_analysis_builder_and_loader_require_provider_bound_statistical_protocol`.
- `test_analysis_builder_and_loader_require_exact_provider_bound_audit_protocol`.
- `test_bootstrap_artifact_builder_derives_seed_from_provider_evidence_and_round_trips_c_order_bytes`.
- `test_bootstrap_artifact_builder_rejects_shape_range_metadata_or_digest_substitution`.
- `test_bootstrap_artifact_builder_has_no_raw_seed_or_protocol_override`.

The report fixture contains hostile model and rationale text with HTML, a link, an image, a heading,
a fenced block, and a mention. Assert that the text-only encoder neutralizes every active construct
and that candidate responses and raw judge evidence do not appear at all.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_reporting.py
~~~

Expected: collection fails because `laconian_eval.benchmark.reporting` does not exist.

- [ ] **Step 3: Implement the closed analysis and evidence-root schemas**

Implement:

~~~python
class DistributionSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    unit: Literal[
        "tokens",
        "usd",
        "milliseconds",
        "characters",
    ]
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    minimum: Decimal | None
    median: Decimal | None
    maximum: Decimal | None


class BootstrapArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["bootstrap-artifact-v1"]
    metadata: BootstrapVectorsV1
    indices: tuple[tuple[int, ...], ...] = Field(min_length=10_000, max_length=10_000)
    bootstrap_artifact_sha256: str


class ChecksumEntryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relative_path: str
    byte_length: int = Field(ge=0)
    sha256: str


class ChecksumManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["analysis-checksums-v1"]
    entries: tuple[ChecksumEntryV1, ...]
    checksums_sha256: str


class DescriptiveUsageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_tokens: DistributionSummaryV1
    visible_output_tokens: DistributionSummaryV1
    reasoning_tokens: DistributionSummaryV1
    billed_output_tokens: DistributionSummaryV1
    total_tokens: DistributionSummaryV1
    ordinary_uncached_input_tokens: DistributionSummaryV1
    cache_read_tokens: DistributionSummaryV1
    cache_write_tokens: DistributionSummaryV1
    trusted_usage_cost_usd: DistributionSummaryV1
    definitely_rejected_zero_cost_usd: DistributionSummaryV1
    retained_worst_case_exposure_usd: DistributionSummaryV1
    unavailable_cost_count: int = Field(ge=0)
    cost_availability_counts: Mapping[CostAvailabilityV1, int]
    cache_policy_status_counts: Mapping[CachePolicyStatusV1, int]
    latency_ms: DistributionSummaryV1
    output_characters: DistributionSummaryV1


class ModelAnalysisV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generation_model: str
    hard_denominators: PairDenominatorsV1
    semantic_denominators: PairDenominatorsV1
    hard_pass_by_arm: Mapping[ArmName, BootstrapIntervalV1]
    semantic_pass_by_arm: Mapping[ArmName, BootstrapIntervalV1]
    hard_primary_difference: BootstrapIntervalV1
    semantic_primary_difference: BootstrapIntervalV1
    hard_visible_delta: BootstrapIntervalV1
    semantic_visible_delta: BootstrapIntervalV1
    usage_by_arm: Mapping[ArmName, DescriptiveUsageV1]
    audit_metrics: ModelAuditMetricsV1
    audit_gate: ModelAuditGateV1
    false_fail_limits: tuple[FalseFailLimitV1, FalseFailLimitV1]
    sensitivity: SensitivityResultV1
    outcome: ModelOutcomeV1


class CampaignAnalysisV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["campaign-analysis-v1"]
    campaign_id: str
    input_tag_commit: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    benchmark_provider_evidence_sha256: str
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    judge_attempt_root_index_sha256: str
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    audit_evidence_sha256: str
    bootstrap_vectors_sha256: str
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    models: tuple[ModelAnalysisV1, ModelAnalysisV1, ModelAnalysisV1]
    limitations: tuple[str, ...]
    campaign_analysis_sha256: str


class AuditEvidenceAttachmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["verified-audit-evidence-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_evidence_index_sha256: str
    benchmark_provider_evidence_sha256: str
    judge_attempt_root_index_sha256: str
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(
        min_length=36,
        max_length=36,
    )
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    population_attachment_sha256: str
    sample_manifest_sha256: str
    blind_packet_sha256: str
    commitment_sha256s: tuple[str, str]
    reveal_sha256s: tuple[str, str]
    reviewer_chain_proof_sha256s: tuple[str, str]
    adjudication_core_sha256: str
    signoff_proof_sha256s: tuple[str, str]
    exact_github_review_record_sha256s: tuple[str, str]
    adjudication_sha256: str
    model_audit_metric_sha256s: tuple[str, str, str]
    audit_evidence_sha256: str


class AnalysisEvidenceAttachmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["verified-analysis-evidence-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    benchmark_provider_evidence_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_evidence_sha256: str
    campaign_analysis_sha256: str
    bootstrap_artifact_sha256: str
    report_sha256: str
    checksums_sha256: str
    analysis_evidence_sha256: str
~~~

Require exactly 36 unique generation capsule hashes, 36 matching hard-score attachment hashes,
36 matching judge-request attachment hashes, 36 matching judge-attempt boundary hashes rooted in
the exact attempt index, 36 matching judge attachment hashes, and exactly
three distinct model analyses sorted by UTF-8 model ID. The campaign analysis digest excludes only
its own digest and uses domain
`laconian-campaign-analysis-v1`.
`analyze_campaign` class-bound revalidates `provider_evidence` and sets
`statistical_protocol_sha256` only from
`provider_evidence.index.statistical_protocol_sha256`; it has no protocol argument or environment
fallback. It likewise sets `audit_protocol_sha256` only from
`provider_evidence.index.audit_protocol_sha256`. Both repeated projection fields and the complete
`protocol_bindings` object must match those index values before analysis.
For every model, require
the limits in exact `(if, concise)` order, each
`limit.model_audit_metric_sha256 == audit_metrics.model_audit_metric_sha256`, and
`sensitivity.model_audit_metric_sha256 == audit_metrics.model_audit_metric_sha256`; neither
reporting nor outcome classification accepts limits derived from another metric record. Recompute
the literal A_m formula from those stored limits and require equality with
`sensitivity.assignment_count` before sealing analysis.

`AuditEvidenceAttachmentV1.audit_evidence_sha256` uses domain
`laconian-verified-audit-evidence-v1` over every preceding field. Its two reviewer-chain, two
signoff-proof, and two exact API-record digests are ordered by reviewer ID and must
correspond one-to-one; no sequence may be reordered independently. The attachment therefore
directly binds all four ordered 36-parent layer vectors, the attempt root/vector, and transitively
binds both identities and PR proofs, the stored core, signoffs, offline-review records, numeric
accounts, reviewer registry, and final envelope.

For `CampaignAnalysisV1`, `AuditEvidenceAttachmentV1`, and `AnalysisEvidenceAttachmentV1`, build
`protocol_bindings` only with Task 3's `protocol_bindings_from_context`; class-bound validation
requires its two registry digests, attestation root, every tagged protocol/source root, and
`workflow_root` to byte-equal the verified provider index. This comparison explicitly includes the
singular Runtime-registry-derived `audit_protocol_sha256` without adding it to any attestation subject
inventory. Each final object also repeats and
verifies the expectation digest, context digest, and provider-projection root. Tests mutate any one
binding and recompute every local self digest; the fixed parent comparison must still reject it.

- [ ] **Step 4: Expose the Slice 4 verified loader boundary**

Use frozen dataclasses for already-verified aggregates:

~~~python
@dataclass(frozen=True, slots=True)
class VerifiedAuditEvidenceV1:
    attachment: AuditEvidenceAttachmentV1
    population: VerifiedAuditPopulationV1
    manifest: AuditSampleManifestV1
    packet: BlindAuditPacketV1
    reviewer_chains: tuple[ReviewerChainV1, ReviewerChainV1]
    github_review_records: tuple[ExactGitHubReviewRecordV1, ExactGitHubReviewRecordV1]
    adjudication: AuditAdjudicationV1
    metrics: tuple[ModelAuditMetricsV1, ModelAuditMetricsV1, ModelAuditMetricsV1]


@dataclass(frozen=True, slots=True)
class VerifiedAnalysisEvidenceV1:
    attachment: AnalysisEvidenceAttachmentV1
    audit: VerifiedAuditEvidenceV1
    analysis: CampaignAnalysisV1
    bootstrap: BootstrapArtifactV1
    report_bytes: bytes
    checksums: ChecksumManifestV1


def write_audit_evidence_root(
    output_root: Path,
    *,
    source_sample_root: Path,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
    reviewer_chains: tuple[ReviewerChainV1, ReviewerChainV1],
    github_review_records: tuple[ExactGitHubReviewRecordV1, ExactGitHubReviewRecordV1],
    adjudication: AuditAdjudicationV1,
    metrics: tuple[ModelAuditMetricsV1, ModelAuditMetricsV1, ModelAuditMetricsV1],
    git_object_database: Path,
) -> AuditEvidenceAttachmentV1:
    """Verify every audit parent, atomically write the exact audit root, and fresh-reload it."""


def load_verified_audit_evidence(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditEvidenceV1:
    """Load root/audit and recompute it against the exact provider-parent projection."""


def load_verified_analysis_evidence(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAnalysisEvidenceV1:
    """Verify provider parents and audit first, then recompute analysis and artifact hashes."""
~~~

The audit loader reads exactly:

~~~text
root/audit/audit-evidence.json
root/audit/population-attachment.json
root/audit/population.jsonl
root/audit/sample-manifest.json
root/audit/blind-packet.json
root/audit/commitments/<reviewer-id>.json
root/audit/reveals/<reviewer-id>/reveal.json
root/audit/reveals/<reviewer-id>/labels.jsonl
root/audit/reviewer-chains/<reviewer-id>.json
root/audit/adjudication-core.json
root/audit/signoffs/<reviewer-id>.json
root/audit/github-review-records/<review-id>.json
root/audit/adjudication.json
root/audit/metrics.json
~~~

`write_audit_evidence_root` requires an absent destination and first fresh-loads
`source_sample_root` with `load_verified_audit_sample_root`, requiring canonical equality with the
supplied `sample`. It reruns `verify_audit_chain` using the two supplied exact review records as a
closed numeric-ID lookup and the explicit `git_object_database` path consumed by the fixed Git
object reader and exact mode-discriminated signature verifier; no ancestry/signature callback is
accepted. It then recomputes all three `ModelAuditMetricsV1` values from the immutable
sample/chains/adjudication and canonical-byte compares them with `metrics`. It constructs
`AuditEvidenceAttachmentV1` itself—there is no caller-supplied attachment or digest override.

The writer stages only beneath an operation-owned empty sibling, copies the four sample files byte
for byte, writes every remaining member in the exact allowlist above from the verified models,
fsyncs all files/directories, and installs the root without replacement. It then calls
`load_verified_audit_evidence(output_root, provider_evidence=provider_evidence)`, requires every
returned component and digest to equal the inputs/constructed attachment, and returns that freshly
loaded attachment. On failure it deletes only its validated staging tree and leaves the destination
absent. The loader rejects the offline CLI report, partial sample-only roots, extras, aliases, and
any population/reviewer/record/metric/provider substitution. Thus Publication's live seal wrapper
has an exact neutral writer/loader boundary and never needs a CLI implementation detail.

The analysis loader additionally reads exactly:

~~~text
root/analysis/analysis-evidence.json
root/analysis/analysis.json
root/analysis/bootstrap.json
root/analysis/report.md
root/analysis/checksums.json
~~~

The audit loader first calls
`load_verified_audit_population(root / "audit", provider_evidence=provider_evidence)`, requires its
attachment hash to equal `AuditEvidenceAttachmentV1.population_attachment_sha256`, requires the
attachment provider-index digest, benchmark-provider digest, reviewer-registry digest, all four
36-parent layer vectors, and the judge-attempt root/vector to equal
`provider_evidence.index`/`provider_evidence.projection`, and replays
sampling from its exact records. The analysis loader
passes the same required projection through to the audit loader and additionally requires
`CampaignAnalysisV1.benchmark_provider_evidence_sha256 ==
provider_evidence.projection.benchmark_provider_evidence_sha256`, its input-tag commit to match
`provider_evidence.index.input_tag_commit`, its `statistical_protocol_sha256` to equal both
`provider_evidence.index.statistical_protocol_sha256` and the repeated projection field, its
`audit_protocol_sha256` to equal both `provider_evidence.index.audit_protocol_sha256` and the
repeated projection field, and all four campaign-analysis layer-parent vectors plus
the judge-attempt root/vector to match.
Reject symlinks, non-regular
files, duplicate reviewer paths, unexpected members, extra JSON fields, noncanonical JSON or JSONL,
checksum mismatch, any campaign/root disagreement, and any component not reachable from the
attachment root. Export both verified types and both loaders from
`laconian_eval.benchmark.reporting`, plus `write_audit_evidence_root`,
`write_analysis_evidence_root`, `BootstrapArtifactV1`, `build_bootstrap_artifact`, and both
attachment types, and re-export those exact owners from
`laconian_eval.benchmark` for the Slice 4 collector.

The audit allowlist requires exactly two canonical reviewer-chain proof files that byte-compare their
embedded commitment/reveal fields and labels against the dedicated files, exactly one canonical
`adjudication-core.json`, two distinct bytewise-reviewer-ordered signoff files, and two distinct canonical review records named by their
decimal positive review IDs; aliases, leading-zero IDs, duplicate IDs/inodes, extra records, and
signoff/filename disagreement are errors. Reload each review record first, recompute its domain
digest solely from the stable stored API fields, require its account ID/login and
the signoff's `audit_reviewer_registry_sha256` to match the exact
`provider_evidence.index.audit_reviewer_registry.reviewers` binding and the digest freshly computed from
`canonical_reviewer_registry_bytes(provider_evidence.index.audit_reviewer_registry.reviewers)`, then require the signoff's
`exact_api_record_sha256` and duplicated fields to match. Finally recompute the core digest, both
signoff-proof digests, and the final adjudication envelope, and require the core, ordered signoffs,
ordered reviewer-chain proofs/API-record digests, final envelope, provider roots, and reviewer registry to equal
`AuditEvidenceAttachmentV1`. It never accepts a cached `signature_verified` or review-state Boolean
in place of the exact provenance records.

- [ ] **Step 5: Render analysis artifacts without reinterpreting evidence**

Implement:

~~~python
def build_bootstrap_artifact(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    scenario_uids: Sequence[str],
) -> BootstrapArtifactV1:
    """Derive the frozen seed, vectors, matrix, and artifact digest from verified parents."""


def analyze_campaign(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    aggregates: Sequence[AggregatedModelV1],
    hard_sets: Sequence[HardScoreRequestSetV1],
    judge_attachments: Sequence[JudgeAttachmentV1],
    audit: VerifiedAuditEvidenceV1,
    vectors: BootstrapArtifactV1,
) -> CampaignAnalysisV1:
    """Derive outcomes with analysis protocol only from the verified provider projection."""


def render_public_report(analysis: CampaignAnalysisV1) -> bytes:
    """Render deterministic UTF-8 Markdown from sealed numeric fields and fixed prose only."""


def write_analysis_evidence_root(
    output_root: Path,
    *,
    source_audit_root: Path,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit: VerifiedAuditEvidenceV1,
    analysis: CampaignAnalysisV1,
    bootstrap: BootstrapArtifactV1,
) -> AnalysisEvidenceAttachmentV1:
    """Atomically write one combined root containing the verified audit and new analysis."""
~~~

`build_bootstrap_artifact` class-bound revalidates `provider_evidence`, derives
`seed = derive_seed128("laconian-bootstrap-v1", campaign_seed, input_tag_commit,
judge_protocol_sha256)` solely from its index, and calls `make_cluster_vectors` with exactly the 12
bytewise-sorted scenario UIDs from the verified generation parents. It serializes exactly 10,000
rows of 12 integer values in `[0, 11]`, requires their tuple values to equal the returned contiguous
`uint8` matrix, and copies the metadata whose `indices_sha256` already binds seed, ordered UIDs,
dtype, shape, and canonical C-order bytes. `bootstrap_artifact_sha256` is raw SHA-256 over
`UTF8("laconian-bootstrap-artifact-v1") || NUL || canonical_json(metadata) || NUL ||
indices_uint8.tobytes(order="C")`. The builder has no raw seed, protocol, matrix, or digest argument.
Loaders reconstruct the exact matrix from the JSON integers, reject non-10,000-by-12 shape or values
outside `[0, 11]`, recompute both metadata and artifact digests, and never regenerate a missing
matrix. The independently authority-bound `statistical_protocol_sha256` selects/authorizes this
frozen analysis method through `CampaignAnalysisV1`; the preregistered judge-protocol seed input
remains the Task 2 public randomization contract.

Place point, two-sided 95% interval, fixed denominator 120, scenario coverage, eligible pairs,
token pairs, and missingness in one table row. State the direction
`visible tokens(concise) - visible tokens(if)` next to every primary estimate and phrase any claim
as “among jointly successful matched responses.” Keep input, visible output, reasoning output,
billed output, total, uncached input, cached-read input, cache-write input, reconciled cost by
availability basis, retained worst-case exposure, latency, and characters separate. Never call
cache writes cached reads, infer absent writes as zero, combine retained exposure with trusted-usage
cost, or call visible-token change billed-token, total-token, cost, or unconditional savings. Render
`cache_write_detail_missing` and `forbidden_cache_write_observed` as operational-integrity
limitations adjacent to cost availability and the model outcome.
For each arm, every distribution requires `observed_count + missing_count == 120`;
`cost_availability_counts` contains exactly all four `CostAvailabilityV1` keys including explicit
zeros, and `cache_policy_status_counts` contains exactly all four `CachePolicyStatusV1` keys. Their
counts each sum to 120. A missing cache-write detail therefore appears simultaneously in the write
distribution's missing count, the closed policy-status count, retained-worst-case exposure, and the
model limitation; no serializer may omit the zero/nonzero map entry or collapse it into
cached/uncached input.

Beside every bootstrap interval, state that the target is scenario-superpopulation variation
conditional on this fixed campaign and that nominal 95% percentile coverage is approximate with 12
clusters. The report must expressly deny generalization to new models, provider versions, prompts,
domains, or time periods; a bare “95% CI” label is forbidden.

Report audit cells, exact weights, weighted confusion tables, authorizing two-sided design-weighted
Wilson intervals, reviewer
agreement, kappa without an interval, critical-record coverage, model-specific gates, M/D/U/K by
primary arm, assignment-space size, visited/evaluated counters, certificate digest, cap values, the
closed search-exhaustion reason (or null), all four extrema, outcome reasons, and limitations. Label
each interval `design-weighted-wilson-score-v1`, `two-sided-0.95`, and
`z = 1.959963984540054`. Beside each sensitivity U, report that it is that model/arm interval's upper
endpoint, its `n_eff`, the exact Decimal-derived K, the shared model-audit metric digest, and any
closed unavailability reasons; no alternate bound may set K. Present baseline and Caveman
only as exploratory context. Report each model outcome independently
and, if counting supported models descriptively, link the statement to all three rows.

The limitations section states that certificate schema v1 permits cardinality pruning only and
deliberately disables semantic/token dominance pruning. Consequently, any feasible assignment space
above 4,096 reaches the evaluation cap and is inconclusive unless a future, separately versioned
exact witness scheme is approved.

Canonical JSON files end with one newline. `bootstrap.json` contains vector metadata plus the
10,000 by 12 integer matrix and is hash-bound to its C-order bytes. Before writing,
`write_analysis_evidence_root` calls
`load_verified_audit_evidence(source_audit_root, provider_evidence=provider_evidence)` and requires
canonical equality with `audit`. It also calls `build_bootstrap_artifact` on the 12 scenario UIDs
from the verified provider parents, canonical-byte compares the result with `bootstrap`, and
requires `analysis.statistical_protocol_sha256` to equal the provider index and projection statistics
protocol and `analysis.audit_protocol_sha256` to equal the provider index and projection singular
audit protocol before accepting either object. It stages an absent `output_root`, copies that loader's exact
allowlisted `source_audit_root/audit` tree byte for byte to `output_root/audit`, and writes the five
analysis members under `output_root/analysis`. No reference or symlink back to the source is
permitted. Build `analysis/checksums.json` over the other analysis artifacts, then bind it in
`analysis/analysis-evidence.json` without a digest cycle by excluding `analysis-evidence.json` from
that checksum manifest. Fsync every file and directory, install the combined root with exclusive
no-replace operations, and verify the fresh installed root through
`load_verified_analysis_evidence(output_root, provider_evidence=provider_evidence)`. On any error
remove only the newly created staging directory and leave the destination absent.

- [ ] **Step 6: Run GREEN and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_reporting.py
uv run ruff check src/laconian_eval/benchmark/reporting.py tests/benchmark/test_reporting.py
uv run mypy src/laconian_eval/benchmark/reporting.py
~~~

Expected: all commands pass.

~~~bash
git add src/laconian_eval/benchmark/__init__.py src/laconian_eval/benchmark/reporting.py tests/benchmark/helpers.py tests/benchmark/test_reporting.py
git commit -m "feat: seal benchmark analysis and reports"
~~~

### Task 14: Prove the complete analysis on a 36-capsule synthetic campaign

**Files:**

- Modify: `tests/benchmark/helpers.py`
- Create: `tests/benchmark/test_synthetic_analysis.py`
- Modify: `benchmarks/methodology.md`
- Modify: `evals/README.md`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write exactly eleven failing end-to-end analysis tests**

Create tests named:

- `test_synthetic_campaign_reconstructs_analysis_from_36_bound_attachments`
- `test_synthetic_negative_inconclusive_and_supported_models_remain_separate`
- `test_synthetic_artifacts_are_byte_identical_across_two_fresh_roots`
- `test_synthetic_analysis_loaders_fail_closed_on_each_parent_hash_substitution`
- `test_synthetic_audit_reload_recomputes_core_review_records_signoffs_and_final_envelope`
- `test_synthetic_sample_and_audit_atomic_writers_fresh_reload_exact_roots`
- `test_synthetic_two_sided_wilson_false_fail_upper_sets_k_and_keeps_zero_error_uncertainty_positive`
- `test_synthetic_attestations_accept_null_github_and_keyed_fingerprints_by_mode`
- `test_synthetic_security_attestation_requires_nonnull_keyed_fingerprint`
- `test_synthetic_attestations_reject_cross_role_reorder_extra_missing_or_duplicate_subject`
- `test_synthetic_attestations_reject_extra_top_level_field_or_signature_mode_mismatch`

Do not add the helper yet. The first test's literal expectations require identical authority-tagged
`statistical_protocol_sha256` and singular `audit_protocol_sha256` across context, provider index,
projection, nested protocol bindings, audit evidence, analysis, and final analysis evidence. It also
pins the exact assignment-count formula, the shared per-model audit-metric digest in both arm limits,
all four sensitivity extrema or one closed exhaustion reason, and every count/root described in
Step 3 below. The other ten tests cover independent outcomes, deterministic bytes, parent
substitution, full audit re-verification, atomic writers, Wilson-to-K propagation, and the four
attestation mode/inventory failures named above.

- [ ] **Step 2: Run the eleven tests RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_synthetic_analysis.py
~~~

Expected: tests fail because the complete synthetic campaign builder and artifact reconstruction
are not implemented.

- [ ] **Step 3: Implement the deterministic 36-capsule fixture**

Only after recording RED, add `build_synthetic_public_campaign()` to
`tests/benchmark/helpers.py`. It creates:

~~~text
3 generation models
x 12 scenario capsules per model
x 2 locales per scenario
x 4 arms per locale
x 5 repetitions per arm
= 36 verified capsules and 1,440 planned terminal rows
~~~

Every synthetic capsule carries a non-null SealV1 hash and verified ScoredAttemptV2 projection.
Derive 36 hard-score request sets, 36 judge-request attachments, 36 judge-attempt-boundary files and
their `JudgeAttemptRootIndexV1`, and 36 judge attachments, including one explicit empty boundary and
sealed zero-call attachment. Provider-ready request/attempt fixtures use literal
`service_tier=default`; include one definite pre-response 429 retry with
`service_tier_status=not_applicable_definitely_rejected` and one rejected nondefault-tier attempt
that retains worst-case exposure and cannot seal. Build accepted attachments only from
`load_verified_judge_attempt_root`.

Build a fixed synthetic `GenerationContextExpectationV1`, authority wrapper,
`GenerationContextIndexV1`, and `ProviderEvidenceIndexV1` with independently fixed plaintext
seed/input commit; the exact two audit reviewers and recomputed registry digest; the separate exact
three-role protocol reviewer registry; allowed null GitHub and exact keyed fingerprints; the three
exact `ProtocolAttestationV1` records with unchanged role subject inventories; their shared
`workflow_root`; exact authority-tagged statistics and singular audit protocol hashes; expectation,
context, four layer-index, and attempt-root digests; and the provider projection/wrapper. Propagate
the same `audit_protocol_sha256` through every nested `BenchmarkProtocolBindingsV1` and every final
top-level field specified in Task 13.

Then build the complete audit population/JSONL; deterministic sample round-tripped through
`write_audit_sample_root` and `load_verified_audit_sample_root`; two distinct reviewer chains;
independently hashed adjudication core; two canonical exact GitHub review records with stable numeric
account IDs; two signoff proofs; final adjudication envelope; per-model metrics with authorizing two-
sided design-weighted Wilson intervals; Decimal-derived U and K; exact candidate spaces satisfying
`A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})`; frozen bootstrap
artifact; sensitivity results; three model analyses; and the combined audit-plus-analysis result
root. The helper never instantiates a provider, reads credentials, accesses the network, uses wall-
clock time, or derives a test expectation from implementation output.

Shape outcomes deliberately: one model has a verified hard or semantic negative-quality interval,
one is inconclusive through a declared audit or sensitivity gate, and one is supported with strict
positive brevity and non-inferior quality. Assert those outcomes by literal exact model ID.

- [ ] **Step 4: Run the eleven tests GREEN**

Run after implementing the helper and exact assertions:

~~~bash
uv run pytest -q tests/benchmark/test_synthetic_analysis.py
~~~

Expected: all eleven named tests pass without network access or environment secrets.

- [ ] **Step 5: Replace the public no-interval limitation with the frozen contract**

Update `benchmarks/methodology.md` to state all of these normative facts in its confidence-interval,
quality-gate, audit, and outcome sections:

- visible output equals provider output minus reasoning output; all other usage measures remain
  separate, including uncached input, cached reads, cache writes, and cost availability/retained
  worst-case exposure;
- H and S use 120 planned keys per model/arm, with terminal zero reasons separated from inference-
  invalid missing or ambiguous evidence;
- every provider-ready judge request binds the exact API pair `"service_tier": "default"`; returned
  tier and its closed `service_tier_status` are captured per attempt using the exact
  Foundation vocabulary `reported_default`, `not_applicable_definitely_not_sent`,
  `not_applicable_definitely_rejected`, `missing`, and `mismatch`; a definite pre-response rejection
  with no response/usage records
  `not_applicable_definitely_rejected` and remains retryable, while
  response-received or unknown-delivery missing/nondefault tier stops without entering judge
  evidence and retains worst-case spend exposure;
- eligible pairs and token pairs are separate and require at least 96 pairs and 10 scenarios;
- 10,000 NumPy PCG64 scenario-cluster replicates, 12 sampled scenarios, type-7 0.025/0.975
  quantiles, at least 9,990 valid replicates, the fixed-campaign conditional scenario target, and
  nominal approximate coverage with only 12 clusters;
- five-point hard and sensitivity-adjusted semantic non-inferiority;
- analysis and bootstrap use only the authority-tagged `statistical_protocol_sha256`, while audit
  evidence also requires the singular Runtime-registry-derived `audit_protocol_sha256`; both are
  carried identically by generation context, provider index/projection, nested protocol bindings,
  campaign analysis, and final evidence;
- exact 144-record sampling, certainty critical records, Hamilton allocation, two-person
  commit-reveal, design weights, authorizing two-sided design-weighted Wilson intervals with
  `z = 1.959963984540054`, model-specific point-estimate audit gates, each primary arm's Wilson upper
  endpoint as U, the exact `K = min(M, max(D, ceil(U * M)))` Decimal calculation, the literal
  assignment count `A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})`,
  and bounded exact false-fail certificates;
- the strict outcome precedence and the phrase “among jointly successful matched responses.”
- Runtime's three live methods are exactly
  `laconian_eval.campaign.runtime.Runtime.hard_score`,
  `laconian_eval.campaign.runtime.Runtime.prepare_judge`, and
  `laconian_eval.campaign.runtime.Runtime.seal_judge`, reachable only from the private
  `_reconstruct_verified_runtime` constructor; they receive an in-memory verified
  generation-context expectation and call the neutral Task 3/4/8 library boundaries directly;
- Publication's four later live methods are exactly
  `Publication.campaign.evaluation_stage.sample_audit`,
  `Publication.campaign.evaluation_stage.seal_audit`,
  `Publication.campaign.evaluation_stage.analyze`, and
  `Publication.campaign.evaluation_stage.verify`, reachable only from the private
  `_reconstruct_verified_publication` constructor; `analyze` and `verify` remain separate;
- all seven standalone benchmark commands are offline and non-evidentiary, use the one canonical
  expectation file, and accept no raw expected-digest flag.

Update `evals/README.md` so the published-results section names sealed generation evidence, all 36
hard-score request sets, all 36 judge-request attachments, all 36 judge attachments,
the campaign-neutral `JudgeAttemptEvidenceV1`/`JudgeAttemptRootIndexV1` verification handoff,
`LayerRootIndexV1`, `GenerationContextExpectationV1`, `GenerationContextIndexV1`,
`ProviderEvidenceIndexV1`, the distinct
`reviewers.yaml` and `protocol-reviewers.yaml` identity registries plus
`ProtocolReviewerRegistryV1`, `population-attachment.json`,
`population.jsonl`, the neutral `write_audit_sample_root` and `write_audit_evidence_root`
boundaries, the remaining audit root, bootstrap output,
`BootstrapArtifactV1`/`build_bootstrap_artifact`,
`reviewer-chains/`, `adjudication-core.json`, both `signoffs/` and `github-review-records/`, machine analysis,
human-readable report, and immutable checksums as derived layers. Keep fixtures
explicitly non-evidentiary. State that all seven `laconian-benchmark` commands are offline
validation only. Name the exact Runtime and Publication method tuple above, the two private
constructors, and the separate `analyze` and `verify` operations; neither live module imports the
CLI. State
that all three protocol attestations, the generation context,
provider index, and benchmark projection carry the same verified
`workflow_root`, while Runtime alone owns the 15-workflow inventory schema.
Also state that `statistical_protocol_sha256` and the singular `audit_protocol_sha256` are authority-
bound through context/provider evidence and are the only accepted statistics/audit protocol values;
the singular audit digest does not alter the approved granular attestation subject inventories.

- [ ] **Step 6: Add an exact public-contract regression test**

Add this test to `tests/test_public_contract.py`:

~~~python
def test_methodology_freezes_public_cluster_bootstrap_and_audit_contract() -> None:
    methodology = _read("benchmarks/methodology.md")
    required = (
        "visible_output_tokens = output_tokens - reasoning_tokens",
        "cache_write_tokens",
        "retained_worst_case",
        "sum(H) / 120",
        "sum(S) / 120",
        '"service_tier": "default"',
        "service_tier_status",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
        "missing",
        "mismatch",
        "reported_default",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "10,000",
        "Generator(PCG64)",
        "type-7",
        "9,990",
        "scenario-superpopulation-conditional-on-fixed-campaign",
        "nominal 95% approximate",
        "144",
        "Hamilton",
        "commit-reveal",
        "n_eff = sum(w)^2 / sum(w^2)",
        "z = 1.959963984540054",
        "design-weighted-wilson-score-v1",
        "K = min(M, max(D, ceil(U * M)))",
        "A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})",
        "1,000,000",
        "4,096",
        "among jointly successful matched responses",
        "offline and non-evidentiary",
        "in-memory verified generation-context expectation",
        "Runtime.hard_score",
        "Runtime.prepare_judge",
        "Runtime.seal_judge",
        "Publication.campaign.evaluation_stage.sample_audit",
        "Publication.campaign.evaluation_stage.seal_audit",
        "Publication.campaign.evaluation_stage.analyze",
        "Publication.campaign.evaluation_stage.verify",
        "_reconstruct_verified_runtime",
        "_reconstruct_verified_publication",
    )
    for phrase in required:
        assert phrase in methodology

    eval_readme = _read("evals/README.md")
    for phrase in (
        "LayerRootIndexV1",
        "GenerationContextExpectationV1",
        "GenerationContextIndexV1",
        "workflow_root",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "JudgeAttemptEvidenceV1",
        "JudgeAttemptRootIndexV1",
        "ProviderEvidenceIndexV1",
        "write_audit_sample_root",
        "write_audit_evidence_root",
        "BootstrapArtifactV1",
        "build_bootstrap_artifact",
        "ProtocolReviewerRegistryV1",
        "reviewers.yaml",
        "protocol-reviewers.yaml",
        "HardScoreRequestSetV1",
        "JudgeAttachmentV1",
        "audit-evidence.json",
        "adjudication-core.json",
        "github-review-records",
        "analysis-evidence.json",
        "bootstrap.json",
        "checksums.json",
    ):
        assert phrase in eval_readme
~~~

- [ ] **Step 7: Run the Slice 2 suite and public-contract test**

Run:

~~~bash
uv run pytest -q tests/benchmark tests/test_public_contract.py::test_methodology_freezes_public_cluster_bootstrap_and_audit_contract
uv run ruff check src/laconian_eval/benchmark tests/benchmark tests/test_public_contract.py
uv run mypy src/laconian_eval/benchmark
~~~

Expected: every command passes.

~~~bash
git add tests/benchmark/helpers.py tests/benchmark/test_synthetic_analysis.py benchmarks/methodology.md evals/README.md tests/test_public_contract.py
git commit -m "test: prove synthetic benchmark analysis"
~~~

### Task 15: Expose seven fixed content-free offline validation commands

**Files:**

- Modify: `src/laconian_eval/cli.py`
- Create: `src/laconian_eval/replay/__init__.py`
- Create: `src/laconian_eval/replay/benchmark.py`
- Create: `tests/benchmark/test_cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_public_contract.py`

This task depends on Tasks 1–14. It adds no workflow, network client, provider dispatch, GitHub API
call, publication mutation, or authority-bearing adapter. Every `laconian-benchmark` command is a
strictly offline, non-evidentiary structural-validation surface. None constructs a
`VerifiedGenerationContextExpectationV1`, calls an evidence writer, returns a verified authority
capability, or creates an artifact that a live loader may accept. Runtime Task 7 owns the first
three campaign-side live functions and depends on neutral Tasks 3/4/8, never Task 15. Publication
Task 7 later creates the `Publication` capability and
`Publication.campaign.evaluation_stage` contract after Evaluation Task 13, and calls the neutral
Task 8/9/10/13 provider, sample-root, audit-root, and analysis-root APIs directly. Neither live
module imports or invokes this Task 15 CLI. Task 15 records the exact live tuple only as a literal
cross-slice contract; it neither imports nor fabricates those future modules as proof.

- [ ] **Step 1: Write the exact parser and console-safety tests**

Create tests named:

- `test_help_lists_exact_seven_commands_and_no_abbreviated_command_is_accepted`
- `test_help_lists_offline_replay_only_and_never_names_live_callables`
- `test_every_option_rejects_abbreviation_and_every_command_rejects_unknown_options`
- `test_all_seven_commands_require_one_canonical_generation_expectation_path`
- `test_no_command_accepts_seed_commit_source_protocol_workflow_or_any_digest_flag`
- `test_all_seven_commands_emit_only_closed_offline_non_evidentiary_kinds`
- `test_first_six_commands_write_only_one_offline_validation_report_and_no_evidence_tree`
- `test_verify_is_read_only_and_emits_only_an_offline_verification_envelope`
- `test_offline_validation_reports_are_rejected_by_every_live_complete_root_loader`
- `test_cli_source_has_no_live_hook_campaign_import_verified_loader_builder_or_evidence_writer_call`
- `test_cli_cannot_construct_or_import_verified_generation_context_expectation`
- `test_offline_hard_score_detects_context_code_protocol_member_or_workflow_root_substitution`
- `test_offline_prepare_judge_checks_default_tier_context_and_all_36_hard_score_parents`
- `test_offline_seal_judge_checks_36_attempt_boundaries_retry_lineage_and_tier_statuses`
- `test_offline_sample_audit_checks_provider_projection_and_all_parent_vectors_without_sampling`
- `test_offline_seal_audit_checks_population_core_signoffs_and_exact_review_records`
- `test_offline_analyze_checks_audit_and_statistical_protocol_inputs_without_running_analysis`
- `test_offline_verify_checks_all_four_layer_vectors_and_attempt_root`
- `test_commands_are_input_read_only_output_no_replace_and_failure_atomic`
- `test_every_error_is_canonical_content_free_json_without_path_model_prompt_or_label_text`

Create those tests in `tests/benchmark/test_cli.py`. Also add the cumulative test
`test_public_benchmark_slice2_exports_and_exact_seven_commands_are_owned` to
`tests/test_public_contract.py`. In that file define, as literal tuples rather than values derived
from the implementation, `EXPECTED_BENCHMARK_SLICE2_EXPORTS` containing every public name in Step 6
in that exact order and `EXPECTED_BENCHMARK_COMMANDS` equal to:

~~~python
("hard-score", "prepare-judge", "seal-judge", "sample-audit", "seal-audit", "analyze", "verify")
~~~

All tests invoke only `laconian_eval.cli.main` with the benchmark program selector. The first six commands may write exactly one quarantined
`offline-non-evidentiary.json`; `verify` is read-only. Tests assert no command writes a
layer index, provider index, audit root, analysis root, or any live schema, and that every live
complete-root loader rejects the offline report. Task 3/4/8/13 tests remain the owners of real
artifact production and verification, with Tasks 9–13 owning the review, metric, certificate,
audit, and analysis layers; Task 15 does not duplicate those live paths.

Task 15 proves only the offline modules and call graph that exist in this slice. Runtime Task 7 and
Publication Tasks 7–8 own and test the real live modules after they exist; no fake future-module
fixture or import is accepted as proof here.

The cumulative test imports `laconian_eval.benchmark`, asserts its `__all__` is exactly
`EXPECTED_BENCHMARK_SLICE2_EXPORTS` with no missing, extra, or reordered name, imports
`laconian_eval.replay.benchmark.build_parser` explicitly, extracts the root parser's subparser choices,
and asserts their tuple is exactly `EXPECTED_BENCHMARK_COMMANDS`. It additionally asserts `cli` and
`main` are absent from the package `__all__`, importing the package did not import the CLI module,
and a static scan finds no `laconian_eval.campaign` import anywhere below
`src/laconian_eval/replay`.

Parametrize every command with a symlink input, non-regular input, wrong campaign parent, malformed
canonical JSON, injected candidate canary, injected model-ID canary, and injected exception canary;
parametrize commands 1–6 additionally with an existing output root. Snapshot input bytes and file
metadata before and after every success and failure, and prove command 7 never creates an output.
The CLI tests also import representative library boundaries without initializing the CLI. The
cumulative public-contract test, not a duplicated implementation-derived list in this file, owns
the exact complete export set and exact seven-command surface.

- [ ] **Step 2: Run RED**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_cli.py::test_help_lists_exact_seven_commands_and_no_abbreviated_command_is_accepted
uv run pytest -q tests/test_public_contract.py::test_public_benchmark_slice2_exports_and_exact_seven_commands_are_owned
~~~

Expected: the first command fails because the existing dispatcher has no benchmark replay parser,
and the second fails because the exact Slice 2 export/command contract is not implemented.

- [ ] **Step 3: Add the exact console entry point and non-abbreviating parser**

Add to `pyproject.toml` under `[project.scripts]`:

~~~toml
laconian-benchmark = "laconian_eval.cli:main"
~~~

Implement:

~~~python
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VERIFICATION = 3
EXIT_OUTPUT_EXISTS = 4
EXIT_SOFTWARE = 70


# src/laconian_eval/replay/benchmark.py
def build_parser() -> argparse.ArgumentParser:
    """Return the fixed parser with allow_abbrev=False on root and every subparser."""


# src/laconian_eval/cli.py
def main(
    argv: Sequence[str] | None = None,
    *,
    program: str | None = None,
) -> int:
    """Preserve legacy dispatch; select replay.build_parser only for laconian-benchmark."""


class OfflineValidationReportV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["benchmark-offline-validation-report-v1"]
    command: Literal[
        "hard-score",
        "prepare-judge",
        "seal-judge",
        "sample-audit",
        "seal-audit",
        "analyze",
        "verify",
    ]
    artifact_kind: Literal[
        "offline-hard-score-validation",
        "offline-prepare-judge-validation",
        "offline-seal-judge-validation",
        "offline-sample-audit-validation",
        "offline-seal-audit-validation",
        "offline-analyze-validation",
        "offline-verify-validation",
    ]
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_input_sha256s: tuple[str, ...]
    status: Literal["structurally-valid-not-authorized"]
    offline_report_sha256: str = Field(pattern="^[0-9a-f]{64}$")
~~~

`main` computes `effective_program = program or Path(sys.argv[0]).name`. Exact
`laconian-benchmark` selects the replay parser; exact `laconian` delegates to the existing
`entrypoint`/legacy parser. Any other program name is a content-free usage error. Tests call `main`
with the explicit program selector and also invoke both installed console scripts, so direct imports
and existing monkeypatches keep a compatible `entrypoint` owner.

Use `ArgumentParser(allow_abbrev=False, add_help=True)` for the root and pass
`allow_abbrev=False` to every subparser. Override parser error handling so usage failures never
echo supplied values or paths. Subcommand prefixes and option prefixes are errors; there are no
aliases, environment-derived paths, positional paths, free-form model IDs, shell strings, command
strings, or arbitrary reason text.
The exact help description for every command begins
`OFFLINE NON-EVIDENTIARY VALIDATION ONLY; replay validates structure but cannot authorize live execution`.
Thus no standalone surface can be mistaken for a release-authorizing path.

`main` canonical-parses the one expectation file, recomputes its self digest, and uses the contained
identities only to check the declared artifacts' internal graph. Possession of those bytes does not
verify the predecessor or final authority roots. The CLI must not import
`VerifiedGenerationContextExpectationV1`, create a verified wrapper, or call an authority-bearing
loader with caller-derived expected digests.

Commands 1–6 write only one canonical `OUTPUT/offline-non-evidentiary.json` report containing the
closed command kind, the expectation self digest, sorted input digests, fixed status
`structurally-valid-not-authorized`, and its own self digest. The report is a private CLI schema, is
not package-exported, and is rejected by every layer/provider/audit/analysis loader. Command 7
writes no file and emits the same closed information in the content-free stdout envelope. Offline
validation uses only strict raw-schema parsing, canonical-byte hashing, and integrity-relation
checks. It never invokes a `load_verified_*` function, evidence builder, sampling/analysis builder,
or evidentiary attachment/root writer. Static AST tests reject those calls and reject construction
of every `Verified*` capability. No raw expected-context, expectation, predecessor,
final-authority, source/protocol, workflow, registry, or evidence-root digest option exists.

Require the command-to-kind mapping above exactly, validate every input digest as 64 lowercase
hexadecimal characters, bytewise-sort `ordered_input_sha256s`, and compute
`offline_report_sha256` with domain
`laconian-benchmark-offline-validation-report-v1` over every preceding field. The type is private to
`replay.benchmark` and must be absent from package `__all__`.

- [ ] **Step 4: Freeze the seven commands and their complete option sets**

The help order and accepted invocations are exactly:

~~~text
laconian-benchmark hard-score --generation-expectation GENERATION_EXPECTATION --generation-index GENERATION_INDEX --generation-root GENERATION --output-root OUTPUT
laconian-benchmark prepare-judge --generation-expectation GENERATION_EXPECTATION --generation-index GENERATION_INDEX --generation-root GENERATION --hard-score-root HARD --output-root OUTPUT
laconian-benchmark seal-judge --generation-expectation GENERATION_EXPECTATION --generation-index GENERATION_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-attempt-root ATTEMPTS --output-root OUTPUT
laconian-benchmark sample-audit --generation-expectation GENERATION_EXPECTATION --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --output-root OUTPUT
laconian-benchmark seal-audit --generation-expectation GENERATION_EXPECTATION --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --review-root REVIEWS --repository-root REPOSITORY --output-root OUTPUT
laconian-benchmark analyze --generation-expectation GENERATION_EXPECTATION --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --audit-root AUDIT --output-root OUTPUT
laconian-benchmark verify --generation-expectation GENERATION_EXPECTATION --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --result-root RESULT
~~~

Root meanings are exact: `GENERATION_EXPECTATION`, required by all seven commands, names only the
canonical adapter-produced file at
`GENERATION_COMPLETE/generation-context-expectation.json` inside the read-only reconstructed
authority package. The standalone CLI verifies its canonical bytes/self digest and uses it only for
non-evidentiary structural validation; path possession does not prove the predecessor/final
authority binding. `GENERATION_INDEX`, required by commands 1 through 3, is the one canonical
`GenerationContextIndexV1` file at
`GENERATION/generation-context.json`, emitted by the Slice 3 runtime Task 7 adapter at
`GENERATION_COMPLETE`; the CLI checks the declared layout but cannot authorize it as that retained
child.
`PROVIDER_INDEX` is the one canonical
`ProviderEvidenceIndexV1` file at `JUDGES/provider-evidence-index.json`, emitted at
`JUDGE_COMPLETE` after the four roots were sealed; the explicit flag must name that exact child;
`GENERATION` is the Slice 1 sealed generation evidence root; `HARD`, `REQUESTS`, and `JUDGES` are
complete retained live-stage or explicit-fixture evidence roots containing
`hard-score/`, `judge-requests/`, and `judge/` respectively; `ATTEMPTS` is the exact Runtime Task 7
output root containing only the fixed `judge-attempts/` tree described in Task 4; `AUDIT` is the complete `seal-audit`
output root containing `audit/`; and `RESULT` is the complete `analyze` output root containing both
`audit/` and `analysis/`. Passing an index's parent, a layer subdirectory where a complete root is
required, a copied expectation outside the fixed authority-package layout, or a provider index with
graph identities that disagree with the expectation/root set is an error. Commands do not
probe parent/sibling directories or search for a newest artifact. None accepts a campaign seed,
input-tag commit, expected-context/expectation/authority hash, source/protocol hash, workflow root,
reviewer registry, or evidence vector as a
separate option.

`OUTPUT` always means an offline-report root; it never means `HARD`, `REQUESTS`, `JUDGES`, `AUDIT`,
or `RESULT`, and no CLI invocation produces an input for a later CLI invocation. Those evidence
roots must already come from Runtime's direct library stages, Publication's direct library stages,
or an explicitly non-evidentiary fixture. Help text states this distinction beside every
`--output-root` option.

The exact live tuple is frozen here, without importing a future live module:

~~~python
EXPECTED_LIVE_METHODS = (
    "laconian_eval.campaign.runtime.Runtime.hard_score",
    "laconian_eval.campaign.runtime.Runtime.prepare_judge",
    "laconian_eval.campaign.runtime.Runtime.seal_judge",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.sample_audit",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.seal_audit",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.analyze",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.verify",
)
EXPECTED_PRIVATE_CONSTRUCTORS = (
    "_reconstruct_verified_runtime",
    "_reconstruct_verified_publication",
)
~~~

Runtime Task 7 and Publication Tasks 7–8 own the live import/call-graph proof after those modules
exist. This task only asserts that `src/laconian_eval/replay/**` imports no campaign module and
that the seven offline parser choices equal the literal command tuple; a fake module, monkeypatch,
or fixture standing in for either live owner is forbidden.

Offline command validation responsibilities are fixed:

1. `hard-score` checks the canonical generation expectation/context pair, generation layer index,
   all 36 generation capsule-plus-sidecar parents, hard-scorer code/protocol identities, judge
   protocol, workflow root, registries, and attestations by schema and digest only. It derives no
   request set and calls no Task 3 builder or verified loader.
2. `prepare-judge` additionally checks all 36 hard-score parents, public seed/input commitment,
   judge protocol, and the literal `"service_tier":"default"` wire field stored in context. It
   creates no blinded request attachment or provider payload and calls no Task 4 builder.
3. `seal-judge` additionally checks the exact 36-boundary attempt root, including empty boundaries,
   request/blind/retry/usage/terminal parentage, and the closed Foundation cache/tier statuses.
   It creates no judge attachment, layer root, or provider index and calls no verified attempt or
   provider loader.
4. `sample-audit` checks that the explicit provider index projects the same expectation/context,
   workflow root, registries, attestations, four ordered 36-parent vectors, and judge-attempt
   root/vector by raw schema and digest only. It neither constructs a verified provider projection,
   builds a population/sample, nor writes an audit packet, and it never imports
   `EvidenceInventoryV1`.
5. `seal-audit` additionally checks the unchanged population/sample bindings, reviewer chains,
   Git ancestry/signing evidence, adjudication core, independently recomputable exact GitHub review
   records, signoffs, and final envelope as supplied structural evidence. It performs no GitHub
   call, invokes no audit builder, and writes no audit tree.
6. `analyze` checks the complete audit tree, provider/audit parent bindings, audit metrics,
   the provider-bound statistics and singular audit protocols, the authorizing two-sided Wilson
   inputs, Decimal U/K derivation, exact assignment-count/certificate inputs, and
   cache-write accounting needed by a later live analysis. It invokes no aggregation, bootstrap,
   sensitivity, or analysis builder and writes no result root.
7. `verify` performs the same offline structural checks over `RESULT`, including both
   `audit/` and `analysis/`, all four ordered 36-parent layer vectors, and the judge-attempt
   root/vector. It is read-only and emits only the offline stdout envelope.

Every input path is opened beneath a retained parent descriptor; reject absolute references inside
indexes, parent traversal, symlinks, devices, FIFOs, sockets, duplicate inode aliases, unstable
identity, and unexpected members. Every output root must be absent. Stage under an operation-owned
sibling, fsync files and directories, install without replacement, and clean only the validated
owned staging tree after failure.

- [ ] **Step 5: Freeze content-free console and exit behavior**

On success write exactly
`canonical_json({"artifact_count": artifact_count, "artifact_kind": artifact_kind,
"artifact_sha256": offline_artifact_sha256, "command": command_name, "status": "ok"}) + b"\n"`
to stdout and nothing to stderr. Validate `offline_artifact_sha256` as exactly 64 lowercase hexadecimal
characters before serialization. Every command uses count one and exactly one closed kind:
`offline-hard-score-validation`, `offline-prepare-judge-validation`,
`offline-seal-judge-validation`, `offline-sample-audit-validation`,
`offline-seal-audit-validation`, `offline-analyze-validation`, or
`offline-verify-validation`. The CLI has no evidentiary artifact kind. For commands 1–6,
`artifact_sha256` is the freshly reloaded offline report digest; for `verify` it is the
digest of the canonical offline verification envelope. The envelope contains no path, campaign ID, model ID, scenario ID,
prompt, candidate response, judge output, human label, rationale, token count, or exception text.

On failure write nothing to stdout and exactly one canonical JSON line to stderr:

~~~json
{"code":"verification-failed","command":"seal-audit","status":"error"}
~~~

The closed codes are `usage` with exit 2, `verification-failed` with exit 3,
`output-exists` with exit 4, and `software-error` with exit 70. Never include the caught exception
or supplied argument in console output. Static `--help` text may contain only the seven command
names, fixed option names, and fixed descriptions; it exits zero and creates no file.

- [ ] **Step 6: Finalize public imports**

Export these Slice 2 boundaries from `laconian_eval.benchmark` without importing `cli`:

~~~text
RationalV1, derive_seed128,
HardScoreRequestSetV1, build_hard_score_request_set, verify_hard_score_request_set,
JUDGE_REQUESTED_SERVICE_TIER, JUDGE_SERVICE_TIER_WIRE_FIELD,
BlindJudgeRequestV1, JudgeProviderRequestV1, JudgeRequestAttachmentV1, JudgeAttemptUsageV1,
JudgeAttemptEvidenceV1, JudgeAttemptBoundaryV1, JudgeAttemptRootMemberV1,
JudgeAttemptRootIndexV1, VerifiedJudgeAttemptRootV1,
write_judge_attempt_root, load_verified_judge_attempt_root,
JudgeAttachmentV1, build_judge_request_attachment, verify_judge_request_attachment,
build_judge_attachment, verify_judge_attachment,
AggregatedModelV1, aggregate_verified_evidence,
BootstrapVectorsV1, BootstrapIntervalV1, make_cluster_vectors,
BootstrapArtifactV1, build_bootstrap_artifact,
LayerKindV1, GenerationLayerRootMemberV1, AttachmentLayerRootMemberV1,
LayerRootMemberV1, LayerRootIndexV1, write_layer_root_index, load_layer_root_index,
SignatureVerificationModeV1, SignatureEvidenceV1, ProtocolReviewRoleV1,
ReviewerAccountBindingV1, AuditReviewerRegistryV1,
ProtocolReviewerBindingV1, ProtocolReviewerRegistryV1,
ProtocolSubjectV1, ProtocolAttestationV1,
canonical_reviewer_registry_bytes, compute_audit_reviewer_registry_sha256,
canonical_protocol_reviewer_registry_bytes, compute_protocol_reviewer_registry_sha256,
compute_protocol_attestations_root,
BenchmarkProtocolBindingsV1, protocol_bindings_from_context,
GenerationContextExpectationV1, VerifiedGenerationContextExpectationV1,
GenerationContextIndexV1, VerifiedGenerationContextIndexV1,
write_generation_context_index, load_verified_generation_context_index,
ProviderEvidenceIndexV1, write_provider_evidence_index, load_provider_evidence_index,
BenchmarkProviderEvidenceProjectionV1, VerifiedBenchmarkProviderEvidenceV1,
load_verified_benchmark_provider_evidence,
AuditPopulationAttachmentV1, VerifiedAuditPopulationV1, VerifiedAuditSampleRootV1,
build_audit_population, write_audit_population, load_verified_audit_population,
AuditSampleManifestV1, BlindAuditPacketV1, select_audit_sample, verify_audit_sample,
write_audit_sample_root, load_verified_audit_sample_root,
ReviewerIdentityV1, PullRequestProofV1, ReviewerCommitmentV1, ReviewerRevealV1,
ReviewerChainV1, verify_reviewer_chain, AuditAdjudicationCoreV1,
ExactGitHubReviewRecordV1, ExactGitHubReviewSignoffV1, AuditAdjudicationV1, verify_audit_chain,
WeightedConfusionV1, WeightedProportionV1, ModelAuditMetricsV1, ModelAuditGateV1,
compute_model_audit_metrics, evaluate_model_audit_gate,
SensitivityResultV1, SensitivityCertificateV1, verify_sensitivity_certificate,
CampaignAnalysisV1, AuditEvidenceAttachmentV1, AnalysisEvidenceAttachmentV1,
VerifiedAuditEvidenceV1, VerifiedAnalysisEvidenceV1,
write_audit_evidence_root, load_verified_audit_evidence, load_verified_analysis_evidence,
write_analysis_evidence_root
~~~

Set `laconian_eval.benchmark.__all__` to exactly the ordered names above. This is the sole normative
export tuple copied literally into `EXPECTED_BENCHMARK_SLICE2_EXPORTS`; the test must not calculate
the expectation from `dir()`, annotations, source parsing, or the current `__all__`.
`ServiceTierStatus` remains owned and exported by `laconian_eval.providers`; benchmark
models import that exact type but neither re-export it here nor introduce a benchmark alias.

The cumulative public-contract test also pins module ownership. Concrete layer-root,
reviewer-registry, protocol-attestation, generation-expectation, and generation-context
classes/functions must have `__module__ == "laconian_eval.benchmark.context"`; typing aliases are
asserted by object identity with the attributes imported from that module. Provider index/projection
classes/functions must similarly identify `laconian_eval.benchmark.provider_evidence`. A package
re-export is allowed only from those owners, and neither module may define a shadow copy.
`VerifiedAuditSampleRootV1`, `write_audit_sample_root`, and
`load_verified_audit_sample_root` are owned only by
`laconian_eval.benchmark.audit_sampling`; `AuditEvidenceAttachmentV1`,
`BootstrapArtifactV1`, `build_bootstrap_artifact`, `AnalysisEvidenceAttachmentV1`,
`write_audit_evidence_root`, and the audit/analysis loaders are owned only by
`laconian_eval.benchmark.reporting`. The cumulative public-contract test pins those modules and
rejects shadow definitions.

The console target remains `laconian_eval.cli:main`; `laconian_eval.replay.benchmark` owns only the
offline parser/handlers. The existing `laconian` command continues to route through its legacy
parser/`entrypoint`, while the `laconian-benchmark` program selector routes to the seven replay
handlers. There is no live hook, and the cumulative test asserts no capability-bearing callable is
exported by replay modules or the benchmark package.

- [ ] **Step 7: Run GREEN, console gates, and commit**

Run:

~~~bash
uv run pytest -q tests/benchmark/test_cli.py tests/test_public_contract.py::test_public_benchmark_slice2_exports_and_exact_seven_commands_are_owned
uv run pytest -p no:cacheprovider tests/test_public_contract.py tests/test_package.py -q
uv run laconian-benchmark --help
uv run ruff check src/laconian_eval/cli.py src/laconian_eval/replay tests/benchmark/test_cli.py tests/test_public_contract.py
uv run mypy src/laconian_eval/cli.py src/laconian_eval/replay
~~~

Expected: tests and static checks pass; help exits zero and lists exactly the seven commands in the
order above.

~~~bash
git add pyproject.toml src/laconian_eval/cli.py src/laconian_eval/replay/__init__.py src/laconian_eval/replay/benchmark.py tests/benchmark/test_cli.py tests/test_public_contract.py
git commit -m "feat: expose benchmark evaluation commands"
~~~

## Final Slice 2-local verification before handoff

- [ ] Confirm the Slice 1 prerequisite tests pass first:

~~~bash
uv run pytest -q tests/capsule/test_seal_models.py tests/capsule/test_finalize.py tests/capsule/test_scorable.py tests/capsule/test_sidecars.py
~~~

Expected: all prerequisite tests pass; otherwise stop without constructing benchmark attachments.

- [ ] Run the complete evaluation and audit suite:

~~~bash
uv sync --locked
uv run pytest -q tests/benchmark
uv run pytest -q tests/test_public_contract.py tests/test_models.py tests/test_reporting.py
uv run ruff check src tests
uv run mypy src/laconian_eval
uv run pytest -q
~~~

Expected: all six commands pass in order.

- [ ] Re-run the synthetic analysis twice in separate fresh pytest temporary roots and compare
      generation-context expectation/wrapper projection, generation-context/provider indexes, the
      36-boundary judge-attempt root, all four layer
      indexes, `audit-evidence.json`, both
      reviewer-chain proofs, `adjudication-core.json`, both signoffs and exact GitHub review records,
      `analysis-evidence.json`, `analysis.json`, `bootstrap.json`, `report.md`, and `checksums.json`
      byte-for-byte.

- [ ] Run Task 15's Slice 2-local literal adapter fixture contracts. Prove they pin the public
      generation/provider/attempt-root types, the external expectation parameter, all four exact
      campaign-side live boundary names, and the no-`replay.benchmark` dependency without importing
      not-yet-implemented Runtime or Publication modules.

The real Runtime Task 7 and Publication Task 7 adapter/workflow tests are explicitly deferred
cross-slice integration gates, not Slice 2 completion or handoff criteria. The roadmap Milestones
2B and 3 own those checks after the corresponding campaign modules exist; their failure blocks the
synthetic rollout and all live execution, but cannot create a Slice 2 -> Runtime/Publication ->
Slice 2 dependency cycle.

- [ ] Inspect `git status --short` and `git diff --check`. Expected: only the files named in the
      completed task commits are changed, and the whitespace check emits no output.

- [ ] Record the exact input commit, NumPy version, Python version, test commands, and passing test
      counts in the implementation handoff. Do not publish model-performance language from the
      synthetic fixture.
