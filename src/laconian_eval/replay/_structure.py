"""Raw schema and digest joins; these data never constitute verified capabilities."""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from laconian_eval.benchmark.context import (
    AttachmentLayerRootMemberV1,
    BenchmarkProtocolBindingsV1,
    GenerationContextExpectationV1,
    GenerationContextIndexV1,
    GenerationLayerRootMemberV1,
    LayerRootIndexV1,
)
from laconian_eval.benchmark.hard_score import HardScoreRequestSetV1, derive_judge_request_id
from laconian_eval.benchmark.judge import (
    JUDGE_PROMPT_SHA256_V1,
    JUDGE_PROTOCOL_SHA256_V1,
    JUDGE_SCHEMA_SHA256_V1,
    JudgeAttachmentV1,
    JudgeAttemptBoundaryV1,
    JudgeAttemptRootIndexV1,
    JudgeRequestAttachmentV1,
    _validate_attempt_root_structure,
    _validate_boundary_request_binding,
    derive_blind_id,
)
from laconian_eval.benchmark.provider_evidence import (
    BenchmarkProviderEvidenceProjectionV1,
    ProviderEvidenceIndexV1,
)
from laconian_eval.capsule.attempts import RawAttemptV2
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.planning import case_uid, scenario_uid
from laconian_eval.capsule.record_models import CapsuleV1, CaseIndexRowV1, PlanRowV1
from laconian_eval.capsule.seal_models import SealV1
from laconian_eval.capsule.sidecars import ScoredCapsuleSidecarV2
from laconian_eval.capsule.tree_policy import capsule_path_kind
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase, ResponseCaseFile
from laconian_eval.replay._inputs import Inputs, Tree, absolute, parse_model, parse_rows
from laconian_eval.yaml_io import safe_load_unique_bytes

_Model = TypeVar("_Model", bound=BaseModel)


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("offline structural input rejected")


@dataclass(frozen=True)
class Capsule:
    sidecar: ScoredCapsuleSidecarV2
    metadata: CapsuleV1
    manifest: ResolvedManifestV2
    plan: tuple[PlanRowV1, ...]
    cases_by_uid: dict[str, ResponseCase]


@dataclass
class Graph:
    expectation: GenerationContextExpectationV1
    context: GenerationContextIndexV1
    bindings: BenchmarkProtocolBindingsV1
    generation_index: LayerRootIndexV1
    capsules: tuple[Capsule, ...]
    hard_index: LayerRootIndexV1 | None = None
    hard: tuple[HardScoreRequestSetV1, ...] = ()
    request_index: LayerRootIndexV1 | None = None
    requests: tuple[JudgeRequestAttachmentV1, ...] = ()
    judge_index: LayerRootIndexV1 | None = None
    judgments: tuple[JudgeAttachmentV1, ...] = ()
    provider: ProviderEvidenceIndexV1 | None = None
    projection: BenchmarkProviderEvidenceProjectionV1 | None = None


def generation(inputs: Inputs, expectation_path: Path, index_path: Path, root: Path) -> Graph:
    expectation_path, index_path, root = map(absolute, (expectation_path, index_path, root))
    require(expectation_path.name == "generation-context-expectation.json")
    require(expectation_path.parent.name == "GENERATION_COMPLETE")
    require(index_path == root / "generation-context.json")
    expectation = parse_model(inputs.file(expectation_path), GenerationContextExpectationV1)
    context = parse_model(inputs.file(index_path), GenerationContextIndexV1)
    for name in (
        "campaign_id",
        "campaign_registry_sha256",
        "audit_reviewer_registry_sha256",
        "protocol_reviewer_registry_sha256",
        "protocol_attestations_root",
        "workflow_root",
    ):
        require(getattr(expectation, name) == getattr(context, name))
    require(context.generation_context_index_sha256 == expectation.expected_context_index_sha256)
    require(context.generation_root_index_sha256 == expectation.generation_layer_root)
    require(context.judge_protocol_sha256 == JUDGE_PROTOCOL_SHA256_V1)
    require(context.judge_prompt_sha256 == JUDGE_PROMPT_SHA256_V1)
    require(context.judge_schema_sha256 == JUDGE_SCHEMA_SHA256_V1)
    scorer_source = inputs.file(Path(inspect.getfile(HardScoreRequestSetV1)))
    require(hashlib.sha256(scorer_source).hexdigest() == context.hard_scorer_source_sha256)
    tree = inputs.tree(root)
    index = tree.model("generation/index.json", LayerRootIndexV1)
    require(index.layer_kind == "generation" and index.campaign_id == context.campaign_id)
    require(index.layer_root_index_sha256 == context.generation_root_index_sha256)
    members = cast(tuple[GenerationLayerRootMemberV1, ...], index.members)
    require(
        tuple(item.generation_capsule_sha256 for item in members)
        == context.ordered_generation_capsule_sha256s
    )
    files = {"generation/index.json", "generation-context.json"}
    allowed_empty: set[str] = set()
    capsules: list[Capsule] = []
    for member in members:
        prefix = member.capsule_relative_path
        seal_raw = tree.members[prefix + "/seal.json"]
        seal = parse_model(seal_raw, SealV1, final_lf=False)
        require(seal.generation_status == "complete")
        require(hashlib.sha256(seal_raw).hexdigest() == member.generation_capsule_sha256)
        sealed_names = {prefix + "/" + row.path for row in seal.files}
        files.update(sealed_names | {prefix + "/seal.json", member.scored_sidecar_relative_path})
        if prefix + "/.laconian.lock" in tree.members:
            require(tree.members[prefix + "/.laconian.lock"] == b"")
            files.add(prefix + "/.laconian.lock")
        for row in seal.files:
            raw = tree.members[prefix + "/" + row.path]
            require(len(raw) == row.byte_length and hashlib.sha256(raw).hexdigest() == row.sha256)
        for directory in tree.directories:
            if directory.startswith(prefix + "/"):
                relative = directory[len(prefix) + 1 :]
                require(capsule_path_kind(relative) == "directory")
                # Capsule V1 explicitly permits its fixed empty input subdirectories.
                if relative in {"inputs/planning", "inputs/protocols", "inputs/provider"}:
                    allowed_empty.add(directory)
        metadata = parse_model(tree.members[prefix + "/capsule.json"], CapsuleV1, final_lf=False)
        manifest = parse_model(
            tree.members[prefix + "/manifest.json"], ResolvedManifestV2, final_lf=False
        )
        sidecar = parse_model(
            tree.members[member.scored_sidecar_relative_path],
            ScoredCapsuleSidecarV2,
            final_lf=False,
        )
        plan = parse_rows(tree.members[prefix + "/plan.jsonl"], PlanRowV1)
        raw_attempts = parse_rows(tree.members[prefix + "/raw.jsonl"], RawAttemptV2)
        require(len(raw_attempts) == seal.raw_attempt_count)
        terminal = {row.plan_item_id: row for row in raw_attempts if row.terminal}
        require(len(terminal) == sum(row.terminal for row in raw_attempts) == 40)
        case_index = parse_rows(tree.members[prefix + "/case-index.jsonl"], CaseIndexRowV1)
        indexed_cases = {row.case_uid: row for row in case_index}
        require(len(indexed_cases) == len(case_index))
        sources = {
            ordinal: ResponseCaseFile.model_validate(
                safe_load_unique_bytes(tree.members[prefix + f"/inputs/cases/{ordinal:03d}.yaml"])
            )
            for ordinal in {row.source_ordinal for row in case_index}
        }
        cases: dict[str, ResponseCase] = {}
        for case_row in case_index:
            case = sources[case_row.source_ordinal].cases[case_row.record_ordinal]
            require(case.id == case_row.case_id and case.locale == case_row.locale)
            require(case.category == case_row.category and case.scenario_id == case_row.scenario_id)
            require(response_case_sha256(case) == case_row.case_definition_sha256)
            require(hashlib.sha256(case.prompt.encode()).hexdigest() == case_row.prompt_sha256)
            require(len(case.prompt.encode()) == case_row.prompt_utf8_bytes)
            require(
                case_row.scenario_uid
                == scenario_uid(case_row.dataset_id, case_row.dataset_version, case_row.scenario_id)
            )
            require(
                case_row.case_uid
                == case_uid(
                    case_row.scenario_uid,
                    case_row.case_id,
                    case_row.locale,
                    case_row.case_definition_sha256,
                )
            )
            require(case_row.case_uid not in cases)
            cases[case_row.case_uid] = case
        require(
            hashlib.sha256(tree.members[member.scored_sidecar_relative_path]).hexdigest()
            == member.scored_sidecar_sha256
        )
        require(sidecar.capsule_sha256 == member.generation_capsule_sha256)
        require(
            metadata.run_id == seal.run_id and manifest.provider.model == member.generation_model
        )
        require(len(plan) == len(sidecar.scored_attempts) == 40)
        require(tuple(row.ordinal for row in plan) == tuple(range(40)))
        require(all(row.scenario_uid == member.scenario_uid for row in plan))
        for field, path in (
            ("manifest_sha256", "manifest.json"),
            ("case_index_sha256", "case-index.jsonl"),
            ("plan_sha256", "plan.jsonl"),
            ("raw_sha256", "raw.jsonl"),
        ):
            digest = hashlib.sha256(tree.members[prefix + "/" + path]).hexdigest()
            require(getattr(sidecar, field) == digest)
            if field != "raw_sha256":
                require(getattr(metadata, field) == digest)
        require(tuple(row.plan_item_id for row in plan) == sidecar.ordered_plan_item_ids)
        plans_by_id = {row.plan_item_id: row for row in plan}
        require(len(plans_by_id) == 40)
        for attempt in raw_attempts:
            planned = plans_by_id[attempt.plan_item_id]
            for field in (
                "plan_item_id",
                "case_uid",
                "case_definition_sha256",
                "case_id",
                "scenario_uid",
                "locale",
                "arm",
                "repetition",
                "prompt_sha256",
                "instruction_sha256",
                "request_config_sha256",
            ):
                require(getattr(attempt, field) == getattr(planned, field))
            require(attempt.model == member.generation_model)
            require(
                attempt.manifest_sha256 == sidecar.manifest_sha256 and attempt.run_id == seal.run_id
            )
        for plan_row, scored in zip(plan, sidecar.scored_attempts, strict=True):
            require(scored.raw == terminal[plan_row.plan_item_id])
            require(scored.raw.model == member.generation_model)
            require(scored.raw.scenario_uid == member.scenario_uid)
            require(plan_row.plan_item_id == scored.plan_item_id)
            require(plan_row.ordinal == scored.ordinal)
            require(scored.raw.manifest_sha256 == sidecar.manifest_sha256)
            indexed = indexed_cases[plan_row.case_uid]
            for field in (
                "case_uid",
                "case_id",
                "case_definition_sha256",
                "scenario_uid",
                "locale",
                "prompt_sha256",
            ):
                require(getattr(plan_row, field) == getattr(indexed, field))
        require(set(row.case_uid for row in plan) <= set(cases))
        capsules.append(Capsule(sidecar, metadata, manifest, plan, cases))
    tree.exact(files, extra_directories=allowed_empty)
    bindings = BenchmarkProtocolBindingsV1.model_validate(
        {name: getattr(context, name) for name in BenchmarkProtocolBindingsV1.model_fields}
    )
    return Graph(expectation, context, bindings, index, tuple(capsules))


def attachment_layer(
    tree: Tree,
    graph: Graph,
    directory: str,
    kind: str,
    owner: type[_Model],
    digest_field: str,
    *,
    extra: set[str] | None = None,
) -> tuple[LayerRootIndexV1, tuple[_Model, ...]]:
    index = tree.model(directory + "/index.json", LayerRootIndexV1)
    require(index.layer_kind == kind and index.campaign_id == graph.context.campaign_id)
    files = {directory + "/index.json", *(extra or ())}
    rows: list[_Model] = []
    for member, generation_member in zip(
        index.members, graph.generation_index.members, strict=True
    ):
        require(type(member) is AttachmentLayerRootMemberV1)
        member = cast(AttachmentLayerRootMemberV1, member)
        row = tree.model(member.relative_path, owner)
        typed_row = cast(Any, row)
        require(member.generation_model == generation_member.generation_model)
        require(member.scenario_uid == generation_member.scenario_uid)
        require(getattr(row, digest_field) == member.attachment_sha256)
        for field in ("generation_model", "scenario_uid"):
            require(getattr(row, field) == getattr(member, field))
        require(typed_row.campaign_id == graph.context.campaign_id)
        require(typed_row.protocol_bindings == graph.bindings)
        require(
            typed_row.generation_capsule_sha256
            == graph.context.ordered_generation_capsule_sha256s[member.ordinal]
        )
        files.add(member.relative_path)
        rows.append(row)
    tree.exact(files)
    return index, tuple(rows)


def hard_scores(inputs: Inputs, graph: Graph, root: Path) -> None:
    graph.hard_index, graph.hard = attachment_layer(
        inputs.tree(root),
        graph,
        "hard-score",
        "hard-score",
        HardScoreRequestSetV1,
        "hard_score_request_set_sha256",
    )
    for hard, capsule in zip(graph.hard, graph.capsules, strict=True):
        require(hard.manifest_sha256 == capsule.sidecar.manifest_sha256)
        require(hard.plan_sha256 == capsule.sidecar.plan_sha256)
        for record, scored in zip(hard.records, capsule.sidecar.scored_attempts, strict=True):
            for field in (
                "ordinal",
                "plan_item_id",
                "attempt_id",
                "response_id",
                "terminal_reason",
                "hard_pass",
            ):
                require(getattr(record, field) == getattr(scored, field))
            if record.judge_request_id is not None:
                require(record.response_id is not None)
                require(
                    record.judge_request_id
                    == derive_judge_request_id(
                        campaign_id=hard.campaign_id,
                        generation_capsule_sha256=hard.generation_capsule_sha256,
                        plan_item_id=record.plan_item_id,
                        response_id=cast(str, record.response_id),
                        judge_protocol_sha256=graph.context.judge_protocol_sha256,
                    )
                )


def judge_requests(inputs: Inputs, graph: Graph, root: Path) -> None:
    graph.request_index, graph.requests = attachment_layer(
        inputs.tree(root),
        graph,
        "judge-requests",
        "judge-request",
        JudgeRequestAttachmentV1,
        "judge_request_attachment_sha256",
    )
    for request, hard, capsule in zip(graph.requests, graph.hard, graph.capsules, strict=True):
        require(request.hard_score_request_set_sha256 == hard.hard_score_request_set_sha256)
        require(request.campaign_seed_sha256 == graph.context.campaign_seed_sha256)
        require(
            tuple(row.blind_request.judge_request_id for row in request.requests)
            == hard.ordered_judge_request_ids
        )
        passed = tuple(row for row in capsule.sidecar.scored_attempts if row.hard_pass)
        for wrapper, row in zip(request.requests, passed, strict=True):
            blind = wrapper.blind_request
            case = capsule.cases_by_uid[row.case_uid]
            require(
                blind.blind_id
                == derive_blind_id(
                    judge_request_id=blind.judge_request_id,
                    campaign_seed=graph.context.campaign_seed,
                )
            )
            require(
                blind.candidate_response == row.raw.output_text and blind.locale == row.raw.locale
            )
            require(blind.prompt == case.prompt)
            require(
                tuple((item.item_index, item.requirement) for item in blind.rubric)
                == tuple(enumerate(case.semantic_rubric.required_facts))
            )
            require(blind.material_warning_requirement == case.semantic_rubric.material_warning)
            require(
                blind.material_warning_severity == case.semantic_rubric.material_warning_severity
            )


def judge_attempts(inputs: Inputs, graph: Graph, root: Path) -> None:
    tree = inputs.tree(root)
    index = tree.model("judge-attempts/index.json", JudgeAttemptRootIndexV1)
    tree.exact({"judge-attempts/index.json", *(f"judge-attempts/{i:03d}.json" for i in range(36))})
    boundaries = tuple(
        tree.model(member.relative_path, JudgeAttemptBoundaryV1) for member in index.members
    )
    require(graph.request_index is not None)
    assert graph.request_index is not None
    require(index.judge_request_root_index_sha256 == graph.request_index.layer_root_index_sha256)
    _validate_attempt_root_structure(index, boundaries)
    for member, boundary, attachment in zip(index.members, boundaries, graph.requests, strict=True):
        _validate_boundary_request_binding(
            index=index, member=member, boundary=boundary, attachment=attachment
        )


def provider_graph(inputs: Inputs, graph: Graph, provider_path: Path, root: Path) -> None:
    require(absolute(provider_path) == absolute(root) / "provider-evidence-index.json")
    tree = inputs.tree(root)
    provider = tree.model("provider-evidence-index.json", ProviderEvidenceIndexV1)
    graph.judge_index, graph.judgments = attachment_layer(
        tree,
        graph,
        "judge",
        "judge",
        JudgeAttachmentV1,
        "judge_attachment_sha256",
        extra={"provider-evidence-index.json"},
    )
    for field in set(GenerationContextIndexV1.model_fields) & set(
        ProviderEvidenceIndexV1.model_fields
    ):
        if field != "schema_version":
            require(getattr(provider, field) == getattr(graph.context, field))
    require(
        provider.generation_context_expectation_sha256
        == graph.expectation.generation_context_expectation_sha256
    )
    for index, root_field, vector_field, digest_field, rows in (
        (
            graph.hard_index,
            "hard_score_root_index_sha256",
            "ordered_hard_score_request_set_sha256s",
            "hard_score_request_set_sha256",
            graph.hard,
        ),
        (
            graph.request_index,
            "judge_request_root_index_sha256",
            "ordered_judge_request_attachment_sha256s",
            "judge_request_attachment_sha256",
            graph.requests,
        ),
        (
            graph.judge_index,
            "judge_root_index_sha256",
            "ordered_judge_attachment_sha256s",
            "judge_attachment_sha256",
            graph.judgments,
        ),
    ):
        require(index is not None)
        assert index is not None
        require(getattr(provider, root_field) == index.layer_root_index_sha256)
        require(
            getattr(provider, vector_field) == tuple(getattr(row, digest_field) for row in rows)
        )
    for judge, request, hard in zip(graph.judgments, graph.requests, graph.hard, strict=True):
        require(judge.hard_score_request_set_sha256 == hard.hard_score_request_set_sha256)
        require(judge.judge_request_attachment_sha256 == request.judge_request_attachment_sha256)
        require(
            tuple(row.judge_request_id for row in judge.records) == hard.ordered_judge_request_ids
        )
        for record, wrapper in zip(judge.records, request.requests, strict=True):
            require(record.blind_id == wrapper.blind_request.blind_id)
    for cache in (*provider.generation_cache_evidence, *provider.judge_cache_evidence):
        require(
            cache.service_tier_status in {"reported_default", "not_applicable_definitely_rejected"}
        )
        require(cache.returned_service_tier in {None, "default"})
        require(cache.cache_write_tokens in {0, None})
        require(cache.applied_prompt_cache_mode in {None, "explicit"})
        require(cache.applied_prompt_cache_ttl in {None, "30m"})
    generation_rows = tuple(
        row for capsule in graph.capsules for row in capsule.sidecar.scored_attempts
    )
    require(len(provider.generation_cache_evidence) == len(generation_rows) == 1440)
    for cache, scored in zip(provider.generation_cache_evidence, generation_rows, strict=True):
        raw = scored.raw
        require(cache.attempt_id == raw.attempt_id)
        for field in (
            "applied_prompt_cache_mode",
            "applied_prompt_cache_ttl",
            "applied_cache_control_status",
            "requested_service_tier",
            "returned_service_tier",
            "service_tier_status",
            "applied_cache_control_source_sha256",
            "cache_read_source_sha256",
            "cache_write_source_sha256",
            "service_tier_source_sha256",
            "usage_source_sha256",
            "reasoning_tokens_source_sha256",
        ):
            require(getattr(cache, field) == getattr(raw, field))
        for field in (
            "ordinary_uncached_input_tokens",
            "cache_read_tokens",
            "cache_read_status",
            "cache_write_tokens",
            "cache_write_status",
            "reasoning_tokens",
        ):
            require(getattr(cache, field) == getattr(raw.usage, field))
        visible = (
            raw.usage.output_tokens - raw.usage.reasoning_tokens
            if raw.usage.output_tokens is not None and raw.usage.reasoning_tokens is not None
            else None
        )
        require(cache.visible_output_tokens == visible)
    for model in provider.requested_returned_model_ids:
        if model.purpose == "generation":
            successes = tuple(
                row.raw
                for row in generation_rows
                if row.raw.requested_model_id == model.requested_model_id
                and row.terminal_reason == "success"
            )
            require(bool(successes))
            require({row.returned_model_id for row in successes} == {model.returned_model_id})
            require(
                model.returned_model_source_sha256
                == stable_digest(
                    "laconian-requested-returned-model-sources-v1",
                    {
                        "purpose": "generation",
                        "requested_model_id": model.requested_model_id,
                        "returned_model_id": model.returned_model_id,
                        "ordered_returned_model_source_sha256s": tuple(
                            row.returned_model_source_sha256 for row in successes
                        ),
                    },
                )
            )
        else:
            require(
                {row.returned_judge_model_id for judge in graph.judgments for row in judge.records}
                == {model.returned_model_id}
            )
    # This raw projection preserves the retained attempt root and vector. No raw
    # attempt directory is discovered: only seal-judge accepts that explicit input.
    payload: dict[str, Any] = {
        field: getattr(provider, field)
        for field in BenchmarkProviderEvidenceProjectionV1.model_fields
        if field
        not in {"schema_version", "protocol_bindings", "benchmark_provider_evidence_sha256"}
    }
    payload.update(
        schema_version="benchmark-provider-evidence-v1", protocol_bindings=graph.bindings
    )
    json_payload = {
        name: (
            value.model_dump(mode="json")
            if isinstance(value, BaseModel)
            else [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in value
            ]
            if isinstance(value, tuple)
            else value
        )
        for name, value in payload.items()
    }
    json_payload["benchmark_provider_evidence_sha256"] = stable_digest(
        "laconian-benchmark-provider-evidence-v1", json_payload
    )
    graph.provider = provider
    graph.projection = BenchmarkProviderEvidenceProjectionV1.model_validate_json(
        canonical_json(json_payload)
    )
