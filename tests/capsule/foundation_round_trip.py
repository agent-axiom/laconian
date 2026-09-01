"""One exact offline round trip through the public benchmark foundations."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml
from capsule_helpers import source_manifest_v2_payload

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.prepare as prepare_module
from laconian_eval.capsule.attempts import (
    AttemptUsageV2,
    PublicBenchmarkProviderOutcomeV1,
    PublicBenchmarkRawResponseSourceEntryV1,
    PublicBenchmarkRawResponseSourceV1,
    PublicBenchmarkResponseEvidenceV1,
    public_benchmark_raw_response_sha256,
    visible_output_tokens,
)
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_jsonl, sha256_bytes
from laconian_eval.capsule.capture import capture_authored_inputs, load_source_manifest_capture
from laconian_eval.capsule.checkpoint import (
    CheckpointExpectedBindingsV1,
    CheckpointProtocolBindingV1,
    CheckpointProvenanceV1,
    checkpoint_archive_name,
    pack_checkpoint,
    restore_checkpoint,
)
from laconian_eval.capsule.execution import (
    ProviderFactory,
    _ExecutionSeams,
    _PrivateProviderBinding,
    _resume_capsule,
)
from laconian_eval.capsule.finalize import finalize_capsule
from laconian_eval.capsule.import_policy import build_import_policy
from laconian_eval.capsule.planning import (
    materialize_case_index,
    materialize_parent_plan,
    validate_parent_plan,
)
from laconian_eval.capsule.prepare import PrepareRequest, PrepareShardRequest, prepare_shard_capsule
from laconian_eval.capsule.provenance import capture_installed_provenance
from laconian_eval.capsule.record_models import CapsuleV1
from laconian_eval.capsule.sharding import (
    materialize_shard_projection,
    project_shard_plans,
    shard_plan_file_bytes,
    validate_public_generation_partition,
)
from laconian_eval.capsule.sidecars import (
    ScoredCapsuleSidecarV2,
    load_verified_scored_capsule,
    write_scored_sidecar,
)
from laconian_eval.capsule.verify import VerificationMode, verify_capsule
from laconian_eval.providers.base import PublicBenchmarkRequestV1
from laconian_eval.providers.openai import OpenAIProvider
from tests.capsule.test_import_policy import _module_runtime


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

    repository_root = Path(__file__).parents[2]
    model_ids = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    campaign_id = "public-foundations-v1"
    captured_inputs = []
    manifest_paths = []
    case_indexes = []

    for model_id in model_ids:
        source_root = tmp_path / "sources" / model_id
        case_root = source_root / "cases"
        protocol_root = source_root / "protocols"
        case_root.mkdir(parents=True)
        protocol_root.mkdir()
        for file_ordinal, scenario_ordinals in enumerate((range(6), range(6, 12))):
            cases = []
            for scenario_ordinal in scenario_ordinals:
                scenario_id = f"scenario-{scenario_ordinal:02d}"
                cases.extend(
                    (
                        {
                            "id": f"{scenario_id}-en",
                            "scenario_id": scenario_id,
                            "locale": "en",
                            "category": "direct",
                            "prompt": f"Return the offline response for {scenario_id}.",
                        },
                        {
                            "id": f"{scenario_id}-ru",
                            "scenario_id": scenario_id,
                            "locale": "ru",
                            "category": "direct",
                            "prompt": f"Верните офлайн-ответ для {scenario_id}.",
                        },
                    )
                )
            case_name = ("response-en.yaml", "response-ru.yaml")[file_ordinal]
            (case_root / case_name).write_bytes(
                yaml.safe_dump(
                    {
                        "schema_version": "1",
                        "kind": "response",
                        "cases": cases,
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ).encode("utf-8")
            )
        (protocol_root / "rubric.json").write_bytes(
            b'{"kind":"offline-foundation-rubric","schema_version":"1"}\n'
        )

        payload = source_manifest_v2_payload()
        payload["run_name"] = "public-foundations-v1"
        payload["provider"] = {
            "kind": "openai",
            "model": model_id,
            "api_key_env": "OPENAI_API_KEY",
            "replay_file": None,
        }
        payload["arms"] = ["baseline", "concise", "caveman", "if"]
        payload["repetitions"] = 5
        payload["generation"] = {
            "max_output_tokens": 1024,
            "temperature": None,
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        }
        manifest_path = source_root / "manifest.yaml"
        manifest_path.write_bytes(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
        )
        source = load_source_manifest_capture(
            manifest_path,
            input_root=None,
            invocation_cwd=tmp_path,
        )
        captured = capture_authored_inputs(source, source_root=repository_root)
        captured_inputs.append(captured)
        manifest_paths.append(manifest_path)
        case_indexes.append(materialize_case_index(captured, captured.resolved_manifest))

    parent_plans = []
    shard_groups = []
    for captured, case_index in zip(captured_inputs, case_indexes, strict=True):
        parent_plan = materialize_parent_plan(
            parent_manifest_sha256=captured.manifest_sha256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        )
        validate_parent_plan(
            parent_plan,
            parent_manifest_sha256=captured.manifest_sha256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        )
        parent_plans.append(parent_plan)
        shard_groups.append(
            project_shard_plans(
                campaign_id=campaign_id,
                resolved_manifest=captured.resolved_manifest,
                parent_manifest_sha256=captured.manifest_sha256,
                parent_plan=parent_plan,
                case_index=case_index,
                captured_arms=captured.arms,
            )
        )

    all_shards = tuple(shard for group in shard_groups for shard in group)
    validate_public_generation_partition(
        campaign_id=campaign_id,
        resolved_manifests=tuple(captured.resolved_manifest for captured in captured_inputs),
        parent_manifest_sha256s=tuple(captured.manifest_sha256 for captured in captured_inputs),
        case_indexes=tuple(case_indexes),
        captured_arms_by_parent=tuple(captured.arms for captured in captured_inputs),
        parent_plans=tuple(parent_plans),
        shard_plans=all_shards,
    )
    shard_projections = tuple(
        materialize_shard_projection(shard, parent_plans[model_ordinal])
        for model_ordinal, group in enumerate(shard_groups)
        for shard in group
    )
    assert len(all_shards) == len(shard_projections) == 36
    assert all(len(projection) == 40 for projection in shard_projections)

    selected_shard = all_shards[0]
    selected_projection = shard_projections[0]
    parent_plan_bytes = canonical_jsonl(
        row.model_dump(mode="json", round_trip=True, warnings=False) for row in parent_plans[0]
    )
    planning_root = tmp_path / "planning"
    planning_root.mkdir()
    parent_plan_path = planning_root / "parent-plan.jsonl"
    shard_plan_path = planning_root / "shard-plan.json"
    parent_plan_path.write_bytes(parent_plan_bytes)
    shard_plan_path.write_bytes(shard_plan_file_bytes(selected_shard))
    results_root = tmp_path / "results"
    results_root.mkdir()

    output_text = "Offline benchmark response."
    returned_model_id = "gpt-5.6-sol-2026-08-01"
    raw_response_source = PublicBenchmarkRawResponseSourceV1(
        schema_version="PublicBenchmarkRawResponseSourceV1",
        entries=tuple(
            PublicBenchmarkRawResponseSourceEntryV1(path=path, present=True, value=value)
            for path, value in (
                ("response.id", "offline-foundations-response"),
                ("response.status", "completed"),
                ("response.error", None),
                (
                    "response.output",
                    [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": output_text}],
                        }
                    ],
                ),
                ("response.model", returned_model_id),
                ("response.service_tier", "default"),
                ("response.prompt_cache_options.mode", "explicit"),
                ("response.prompt_cache_options.ttl", "30m"),
                ("response.usage.input_tokens", 100),
                ("response.usage.input_tokens_details.cached_tokens", 0),
                ("response.usage.input_tokens_details.cache_write_tokens", 0),
                ("response.usage.output_tokens", 20),
                ("response.usage.output_tokens_details.reasoning_tokens", 5),
                ("response.usage.total_tokens", 120),
            )
        ),
    )
    raw_response_sha256 = public_benchmark_raw_response_sha256(raw_response_source)
    usage = AttemptUsageV2(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        availability="complete",
        source="provider",
        cache_read_tokens=0,
        cache_write_tokens=0,
        ordinary_uncached_input_tokens=100,
        reasoning_tokens=5,
        cache_read_status="reported_zero",
        cache_write_status="reported_zero",
        reasoning_token_accounting="reported",
    )
    provider_evidence = PublicBenchmarkResponseEvidenceV1(
        schema_version="public-benchmark-response-evidence-v1",
        response_id="offline-foundations-response",
        raw_response_sha256=raw_response_sha256,
        output_text=output_text,
        raw_response_source=raw_response_source,
        usage=usage,
        requested_model_id="gpt-5.6-sol",
        returned_model_id=returned_model_id,
        returned_model_source_sha256=raw_response_sha256,
        requested_service_tier="default",
        returned_service_tier="default",
        service_tier_status="reported_default",
        service_tier_source_sha256=raw_response_sha256,
        applied_prompt_cache_mode="explicit",
        applied_prompt_cache_ttl="30m",
        applied_cache_control_status="reported_exact",
        applied_cache_control_source_sha256=raw_response_sha256,
        cache_read_source_sha256=raw_response_sha256,
        cache_write_source_sha256=raw_response_sha256,
        usage_source_sha256=raw_response_sha256,
        reasoning_tokens_source_sha256=raw_response_sha256,
    )
    recorded_requests: list[PublicBenchmarkRequestV1] = []

    class RecordingOpenAIProvider(OpenAIProvider):
        def generate_benchmark(
            self,
            request: PublicBenchmarkRequestV1,
        ) -> PublicBenchmarkProviderOutcomeV1:
            recorded_requests.append(request)
            return provider_evidence

    provider = RecordingOpenAIProvider(client=object(), timeout_seconds=60.0)
    installed_provenance = capture_installed_provenance(
        captured_inputs[0],
        source_root=repository_root,
        container_image_digest=None,
    )
    clean_runtime_state = _module_runtime(installed_provenance)
    original_prepare_runtime_capture = prepare_module.capture_runtime_import_state
    original_execution_build_policy = execution_module.build_import_policy
    original_execution_revalidate_state = execution_module.revalidate_import_state
    try:
        prepare_module.capture_runtime_import_state = lambda: clean_runtime_state
        execution_module.build_import_policy = lambda provenance: build_import_policy(
            provenance,
            runtime_state=clean_runtime_state,
        )
        execution_module.revalidate_import_state = lambda _policy, *, require_guard: None
        prepared = prepare_shard_capsule(
            PrepareShardRequest(
                prepare=PrepareRequest(
                    manifest_path=manifest_paths[0],
                    results_root=results_root,
                    invocation_cwd=tmp_path,
                    input_root=None,
                    source_root=repository_root,
                    container_image_digest=None,
                ),
                parent_plan_path=parent_plan_path,
                shard_plan_path=shard_plan_path,
            )
        )
        assert prepared.summary.planned_request_count == 40
        execution = _resume_capsule(
            prepared.path,
            provider_factory=ProviderFactory(),
            seams=_ExecutionSeams(
                install_guard=lambda _policy: None,
                checkpoint=lambda _provenance, _policy, _environment: None,
                private_provider_factory=lambda _request: _PrivateProviderBinding(provider, ()),
            ),
        )
    finally:
        prepare_module.capture_runtime_import_state = original_prepare_runtime_capture
        execution_module.build_import_policy = original_execution_build_policy
        execution_module.revalidate_import_state = original_execution_revalidate_state
    assert execution.exit_code == 0
    assert execution.result.state == "GENERATION_COMPLETE"

    expected_request_identities = tuple(
        (row.case_id, row.arm, row.repetition) for row in selected_projection
    )
    request_contracts = tuple(
        type(request) is PublicBenchmarkRequestV1
        and (request.case_id, request.arm, request.repetition)
        == expected_request_identities[ordinal]
        and request.requested_model_id == "gpt-5.6-sol"
        and request.reasoning_effort == "medium"
        and request.text_verbosity == "medium"
        and request.max_output_tokens == 1024
        and request.temperature is None
        and request.timeout_seconds == 60.0
        and request.policy.schema_version == "PublicBenchmarkRequestPolicyV1"
        and request.policy.reasoning_mode == "omitted"
        and request.policy.prompt_cache_mode == "explicit"
        and request.policy.prompt_cache_ttl == "30m"
        and request.policy.service_tier == "default"
        and request.policy.input_token_bound_version == "openai-utf8-envelope-v1"
        and request.policy.max_input_tokens == 272_000
        for ordinal, request in enumerate(recorded_requests)
    )

    finalized = finalize_capsule(prepared.path)
    assert finalized.state == "SEALED_COMPLETE"
    source_verification = verify_capsule(prepared.path, mode=VerificationMode.PREPARED)
    assert source_verification.status == "valid"
    assert source_verification.state == "SEALED_COMPLETE"
    assert source_verification.capsule_sha256 == finalized.capsule_sha256

    scored_root = tmp_path / "scored"
    scored_root.mkdir()
    scored_sidecar_path = scored_root / "scored-sidecar.json"
    scored_sidecar_sha256 = write_scored_sidecar(prepared.path, scored_sidecar_path)
    source_scored = load_verified_scored_capsule(prepared.path, scored_sidecar_path)
    source_sidecar_evidence_sha256 = ScoredCapsuleSidecarV2.model_validate_json(
        scored_sidecar_path.read_bytes()
    ).sidecar_sha256
    assert source_sidecar_evidence_sha256 == scored_sidecar_sha256
    all_attempt_evidence_exact = all(
        scored.terminal_reason == "success"
        and scored.raw.terminal is True
        and scored.raw.terminal_reason == "success"
        and scored.raw.delivery_certainty == "response_received"
        and scored.raw.requested_model_id == "gpt-5.6-sol"
        and scored.raw.returned_model_id == returned_model_id
        and scored.raw.response_model == returned_model_id
        and scored.raw.requested_service_tier == "default"
        and scored.raw.returned_service_tier == "default"
        and scored.raw.service_tier_status == "reported_default"
        and scored.raw.applied_prompt_cache_mode == "explicit"
        and scored.raw.applied_prompt_cache_ttl == "30m"
        and scored.raw.applied_cache_control_status == "reported_exact"
        and scored.raw.usage.cache_read_tokens == 0
        and scored.raw.usage.cache_write_tokens == 0
        and scored.raw.usage.cache_read_status == "reported_zero"
        and scored.raw.usage.cache_write_status == "reported_zero"
        and scored.raw.usage.reasoning_tokens == 5
        and scored.raw.usage.reasoning_token_accounting == "reported"
        and {
            scored.raw.returned_model_source_sha256,
            scored.raw.service_tier_source_sha256,
            scored.raw.applied_cache_control_source_sha256,
            scored.raw.cache_read_source_sha256,
            scored.raw.cache_write_source_sha256,
            scored.raw.usage_source_sha256,
            scored.raw.reasoning_tokens_source_sha256,
        }
        == {raw_response_sha256}
        for scored in source_scored.scored_attempts
    )
    all_visible_token_subtractions_exact = all(
        scored.raw.usage.output_tokens == 20
        and scored.raw.usage.reasoning_tokens == 5
        and visible_output_tokens(scored.raw.usage) == 15
        for scored in source_scored.scored_attempts
    )

    provenance = CheckpointProvenanceV1(
        campaign_id=selected_shard.campaign_id,
        model_id=selected_shard.model_id,
        scenario_uid=selected_shard.scenario_uid,
        batch_attempt_id=UUID("123e4567-e89b-42d3-a456-426614174000"),
        run_attempt=1,
    )
    transport_root = tmp_path / "transport"
    transport_root.mkdir()
    archive_path = transport_root / checkpoint_archive_name(provenance)
    artifact = pack_checkpoint(prepared.path, archive_path, provenance=provenance)
    capsule = CapsuleV1.model_validate_json((prepared.path / "capsule.json").read_bytes())
    expected_bindings = CheckpointExpectedBindingsV1(
        archive_sha256=artifact.sha256,
        manifest_sha256=capsule.manifest_sha256,
        plan_sha256=capsule.plan_sha256,
        parent_plan_sha256=sha256_bytes(parent_plan_bytes),
        shard_plan_sha256=selected_shard.shard_plan_sha256,
        requested_model=selected_shard.model_id,
        scenario_uid=selected_shard.scenario_uid,
        protocol_bindings=tuple(
            CheckpointProtocolBindingV1(
                binding_id=binding.binding_id,
                sha256=binding.sha256,
            )
            for binding in source_scored.manifest.capsule.protocol_bindings
        ),
        provenance=provenance,
    )
    restore_root = tmp_path / "restored"
    restore_root.mkdir()
    restored_path = restore_checkpoint(
        artifact.archive_path,
        artifact.sidecar_path,
        destination_parent=restore_root,
        destination_name=prepared.path.name,
        expected=expected_bindings,
    )
    restored_verification = verify_capsule(restored_path, mode=VerificationMode.PREPARED)
    assert restored_verification.status == "valid"
    assert restored_verification.state == "SEALED_COMPLETE"
    restored_scored = load_verified_scored_capsule(restored_path, scored_sidecar_path)
    restored_sidecar_evidence_sha256 = ScoredCapsuleSidecarV2.model_validate_json(
        scored_sidecar_path.read_bytes()
    ).sidecar_sha256
    assert source_scored == restored_scored
    assert isinstance(source_verification.capsule_sha256, str)
    assert isinstance(restored_verification.capsule_sha256, str)

    tree_hashes = {}
    for label, capsule_root in (("source", prepared.path), ("restored", restored_path)):
        root_descriptor = open_directory_no_follow(capsule_root)
        digest = hashlib.sha256()
        inventory = [(".", "directory")]
        work = ["."]
        try:
            while work:
                relative = work.pop()
                if relative == ".":
                    descriptor = os.dup(root_descriptor)
                else:
                    descriptor = os.open(
                        relative,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=root_descriptor,
                    )
                try:
                    assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
                    with os.scandir(descriptor) as iterator:
                        children = []
                        for entry in iterator:
                            if entry.is_dir(follow_symlinks=False):
                                kind = "directory"
                            elif entry.is_file(follow_symlinks=False):
                                kind = "file"
                            else:
                                raise AssertionError("capsule tree contains a non-regular node")
                            child = entry.name if relative == "." else f"{relative}/{entry.name}"
                            children.append((child, kind))
                    inventory.extend(children)
                    for child, kind in reversed(
                        sorted(children, key=lambda item: item[0].encode("utf-8"))
                    ):
                        if kind == "directory":
                            work.append(child)
                finally:
                    os.close(descriptor)

            for relative, expected_kind in sorted(
                inventory,
                key=lambda item: item[0].encode("utf-8"),
            ):
                if relative == ".":
                    descriptor = os.dup(root_descriptor)
                else:
                    descriptor = os.open(
                        relative,
                        os.O_RDONLY
                        | (os.O_DIRECTORY if expected_kind == "directory" else 0)
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=root_descriptor,
                    )
                try:
                    before = os.fstat(descriptor)
                    if expected_kind == "file":
                        assert stat.S_ISREG(before.st_mode)
                        chunks = []
                        while True:
                            chunk = os.read(descriptor, 65_536)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        payload_bytes = b"".join(chunks)
                        after = os.fstat(descriptor)
                        assert (
                            before.st_dev,
                            before.st_ino,
                            before.st_mode,
                            before.st_size,
                            before.st_mtime_ns,
                            before.st_ctime_ns,
                        ) == (
                            after.st_dev,
                            after.st_ino,
                            after.st_mode,
                            after.st_size,
                            after.st_mtime_ns,
                            after.st_ctime_ns,
                        )
                    else:
                        assert stat.S_ISDIR(before.st_mode)
                        payload_bytes = b""
                    for field in (
                        relative.encode("utf-8"),
                        expected_kind.encode("ascii"),
                        stat.S_IMODE(before.st_mode).to_bytes(4, "big"),
                        payload_bytes,
                    ):
                        digest.update(len(field).to_bytes(8, "big"))
                        digest.update(field)
                finally:
                    os.close(descriptor)
        finally:
            os.close(root_descriptor)
        tree_hashes[label] = digest.hexdigest()

    return FoundationRoundTripEvidence(
        provider_call_count=len(recorded_requests),
        request_contract_count=sum(request_contracts),
        all_request_contracts_exact=(
            len(recorded_requests) == len(request_contracts) == 40 and all(request_contracts)
        ),
        all_attempt_evidence_exact=(
            len(source_scored.scored_attempts) == 40 and all_attempt_evidence_exact
        ),
        all_visible_token_subtractions_exact=(
            len(source_scored.scored_attempts) == 40 and all_visible_token_subtractions_exact
        ),
        source_seal_sha256=source_verification.capsule_sha256,
        restored_seal_sha256=restored_verification.capsule_sha256,
        source_tree_sha256=tree_hashes["source"],
        restored_tree_sha256=tree_hashes["restored"],
        source_sidecar_evidence_sha256=source_sidecar_evidence_sha256,
        restored_sidecar_evidence_sha256=restored_sidecar_evidence_sha256,
    )
