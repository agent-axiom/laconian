"""Source-backed publication and hostile artifact regression tests."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1
from laconian_eval.capsule.canonical import canonical_json, stable_digest


@pytest.fixture(scope="module")
def source_evidence(tmp_path_factory):
    from laconian_eval.benchmark.audit_metrics import compute_model_audit_metrics
    from laconian_eval.benchmark.audit_sampling import select_audit_sample, write_audit_sample_root
    from laconian_eval.benchmark.provider_evidence import build_audit_population
    from tests.benchmark import helpers
    from tests.benchmark.test_audit_commit_reveal import _build_source_backed_audit

    directory = tmp_path_factory.mktemp("real-reporting")
    identity = helpers.real_runtime_identity_registry_bundle()
    varied_attempt = helpers._successful_judge_attempt
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture_patch.setattr(helpers, "protocol_identity_registry_bundle", lambda: identity)
        fixture_patch.setattr(
            helpers,
            "_successful_judge_attempt",
            lambda **kwargs: helpers.with_all_passing_judgment(varied_attempt(**kwargs)),
        )
        provider_fixture = helpers.build_complete_provider_evidence_fixture(
            directory, fixture_patch
        )
    provider = provider_fixture.load()
    population = build_audit_population(provider_evidence=provider)
    manifest, packet = select_audit_sample(population=population, provider_evidence=provider)
    sample_root = directory / "sample"
    sample = write_audit_sample_root(
        sample_root,
        population=population,
        manifest=manifest,
        packet=packet,
        provider_evidence=provider,
    )
    sources = _build_source_backed_audit(provider=provider, sample=sample)
    metrics = tuple(
        compute_model_audit_metrics(
            model=model,
            manifest=manifest,
            population=population.records,
            chains=sources.chains,
            adjudication=sources.adjudication,
        )
        for model in sorted({row.generation_model for row in population.records})
    )
    return SimpleNamespace(
        directory=directory,
        provider=provider,
        provider_fixture=provider_fixture,
        sample_root=sample_root,
        sample=sample,
        sources=sources,
        metrics=metrics,
    )


def write_audit(fixture, output: Path):
    return reporting().write_audit_evidence_root(
        output,
        source_sample_root=fixture.sample_root,
        provider_evidence=fixture.provider,
        sample=fixture.sample,
        audit_git_object_archive=fixture.sources.archive,
        pull_request_sources=fixture.sources.pull_request_sources,
        reviewer_chains=fixture.sources.chains,
        github_review_sources=fixture.sources.github_review_sources,
        adjudication=fixture.sources.adjudication,
        metrics=fixture.metrics,
    )


@pytest.fixture(scope="module")
def audit_evidence(source_evidence):
    root = source_evidence.directory / "audit-root"
    attachment = write_audit(source_evidence, root)
    audit = reporting().load_verified_audit_evidence(
        root, provider_evidence=source_evidence.provider
    )
    assert audit.attachment == attachment
    return SimpleNamespace(root=root, audit=audit, source=source_evidence)


def test_audit_evidence_writer_emits_exact_allowlist_and_copies_sample_bytes_unchanged(
    audit_evidence,
):
    fixture = audit_evidence
    expected = {
        f"audit/{path}"
        for path in (
            "audit-evidence.json",
            "population-attachment.json",
            "population.jsonl",
            "sample-manifest.json",
            "blind-packet.json",
            "git-object-archive.json",
            "pull-request-sources/adjudication.json",
            "adjudication-core.json",
            "adjudication.json",
            "metrics.json",
        )
    }
    for chain in fixture.audit.reviewer_chains:
        reviewer = chain.identity.reviewer_id
        expected.update(
            f"audit/{path}"
            for path in (
                f"pull-request-sources/commitment/{reviewer}.json",
                f"pull-request-sources/reveal/{reviewer}.json",
                f"commitments/{reviewer}.json",
                f"reveals/{reviewer}/reveal.json",
                f"reveals/{reviewer}/labels.jsonl",
                f"reviewer-chains/{reviewer}.json",
                f"signoffs/{reviewer}.json",
            )
        )
    for record in fixture.audit.github_review_records:
        expected.update(
            (
                f"audit/github-review-sources/{record.review_id}.json",
                f"audit/github-review-records/{record.review_id}.json",
            )
        )
    assert {
        path.relative_to(fixture.root).as_posix()
        for path in fixture.root.rglob("*")
        if path.is_file()
    } == expected
    for source in (fixture.source.sample_root / "audit").iterdir():
        assert (fixture.root / "audit" / source.name).read_bytes() == source.read_bytes()
    for path in fixture.root.rglob("*.json"):
        raw = path.read_bytes()
        assert raw == canonical_json(json.loads(raw)) + b"\n"


def test_verified_audit_loader_reconstructs_canonical_github_review_records_from_sources_offline(
    audit_evidence,
):
    audit = audit_evidence.audit
    assert audit.github_review_records == tuple(
        source.record for source in audit.github_review_sources
    )
    assert audit.metrics == audit_evidence.source.metrics


def test_bootstrap_artifact_builder_derives_seed_from_provider_evidence_and_round_trips_c_order_bytes(  # noqa: E501
    source_evidence,
):
    import numpy as np

    from laconian_eval.benchmark.seeds import derive_seed128

    module = reporting()
    artifact = module.build_bootstrap_artifact(provider_evidence=source_evidence.provider)
    index = source_evidence.provider.index
    assert artifact.metadata.seed == derive_seed128(
        "laconian-bootstrap-v1",
        index.campaign_seed,
        index.input_tag_commit,
        index.judge_protocol_sha256,
    )
    matrix = np.array(artifact.indices, dtype=np.uint8, order="C")
    assert matrix.shape == (10000, 12)
    expected = hashlib.sha256(
        b"laconian-bootstrap-artifact-v1\0"
        + canonical_json(artifact.metadata.model_dump(mode="json"))
        + b"\0"
        + matrix.tobytes(order="C")
    )
    assert artifact.bootstrap_artifact_sha256 == expected.hexdigest()
    assert artifact == module.BootstrapArtifactV1.model_validate_json(artifact.model_dump_json())


@pytest.fixture(scope="module")
def analysis_evidence(audit_evidence):
    module = reporting()
    provider = audit_evidence.source.provider
    artifact = module.build_bootstrap_artifact(provider_evidence=provider)
    analysis = module.analyze_campaign(
        provider_evidence=provider, audit=audit_evidence.audit, vectors=artifact
    )
    report = module.render_public_report(analysis)
    return SimpleNamespace(
        audit=audit_evidence, bootstrap=artifact, analysis=analysis, report=report
    )


def test_report_places_intervals_denominators_missingness_and_direction_adjacent(analysis_evidence):
    lines = analysis_evidence.report.decode().splitlines()
    rows = [line for line in lines if "bootstrap point=" in line]
    assert len(rows) == 36
    for line in rows:
        assert all(
            label in line
            for label in (
                "two-sided 95 percent interval=",
                "planned denominator=120",
                "scenario coverage=",
                "eligible pairs=",
                "token pairs=",
                "missingness=",
            )
        )
    for line in [line for line in rows if "visible" in line]:
        assert "visible tokens(concise) - visible tokens(if)" in line
        assert "among jointly successful matched responses" in line


def test_report_labels_bootstrap_target_and_nominal_approximate_twelve_cluster_coverage(
    analysis_evidence,
):
    report = analysis_evidence.report.decode()
    for line in [line for line in report.splitlines() if "bootstrap point=" in line]:
        assert "scenario-superpopulation variation conditional on the fixed campaign" in line
        assert "nominal 95 percent percentile coverage is approximate with 12 clusters" in line
    assert (
        "do not generalize to new models, provider versions, prompts, domains, or time periods"
        in report
    )
    assert "95% CI" not in report


def test_visible_tokens_are_never_labelled_billed_output_or_cost_savings(analysis_evidence):
    report = analysis_evidence.report.decode()
    for line in report.splitlines():
        if "visible tokens(concise)" in line:
            assert "billed" not in line and "cost savings" not in line
    assert "unconditional savings" not in report


def test_report_keeps_cache_reads_writes_uncached_input_and_cost_availability_separate(
    analysis_evidence,
):
    report = analysis_evidence.report.decode()
    for label in (
        "ordinary uncached input tokens",
        "cache read tokens",
        "cache write tokens",
        "trusted usage cost usd",
        "definitely rejected zero cost usd",
        "retained worst case exposure usd",
        "reasoning tokens",
        "billed output tokens",
    ):
        assert label in report
    assert "cost availability counts" in report.lower() and "cache policy status counts" in report


def test_usage_status_maps_are_closed_complete_and_sum_to_120_per_arm(analysis_evidence):
    owner = reporting().DescriptiveUsageV1
    for model in analysis_evidence.analysis.models:
        for usage in model.usage_by_arm.values():
            assert len(usage.cost_availability_counts) == 3
            assert len(usage.cache_policy_status_counts) == 4
            for field in ("cost_availability_counts", "cache_policy_status_counts"):
                assert sum(getattr(usage, field).values()) == 120
                payload = usage.model_dump(mode="json")
                payload[field].pop(next(iter(payload[field])))
                with pytest.raises(ValueError):
                    owner.model_validate_json(canonical_json(payload))


def test_report_discloses_audit_weights_confusion_intervals_and_search_caps(analysis_evidence):
    report = analysis_evidence.report.decode()
    for value in (
        "weighted confusion",
        "exact record weights",
        "audit cell",
        "reviewer agreement",
        "weighted kappa",
        "critical primary coverage",
        "M=",
        "D=",
        "U=",
        "K=",
        "A=",
        "1000000",
        "4096",
        "cardinality pruning v1",
        "semantic and token dominance are disabled",
        "visited_nodes=",
        "evaluated_assignments=",
        "certificate_sha256=",
        "exhaustion_reason=",
    ):
        assert value.lower() in report.lower()
    assert analysis_evidence.audit.audit.manifest.sample_manifest_sha256 in report


def test_report_uses_two_sided_design_weighted_wilson_for_gate_and_false_fail_u(analysis_evidence):
    report = analysis_evidence.report.decode()
    for line in report.splitlines():
        if "Wilson" in line or "U=" in line:
            assert "design-weighted-wilson-score-v1" in line
            assert "two-sided-0.95" in line and "1.959963984540054" in line
        if "U=" in line:
            assert "upper endpoint" in line and "n_eff=" in line
            assert "exact Decimal-derived K=" in line and "unavailable reasons=" in line


def test_report_never_renders_candidate_or_judge_text_as_markdown(analysis_evidence):
    report = analysis_evidence.report
    source = analysis_evidence.audit.audit
    for record in source.packet.records:
        if len(record.candidate_response) > 24:
            assert record.candidate_response.encode() not in report
    judge_evidence = {
        item.evidence
        for boundary in analysis_evidence.audit.source.provider.judge_attempt_root.boundaries
        for attempt in boundary.attempts
        if attempt.judgment is not None
        for item in attempt.judgment.rubric_items
    }
    assert judge_evidence
    assert all(text.encode() not in report for text in judge_evidence)
    module = reporting()
    payload = analysis_evidence.analysis.model_dump(mode="json")
    payload["campaign_id"] = (
        "![image](https://evil.invalid) <script>@everyone</script>\n# heading\n```"
    )
    payload["campaign_analysis_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        module.CampaignAnalysisV1.model_validate_json(canonical_json(payload))
    assert "<script>" not in module._display(
        "![image](https://evil.invalid) <script>@everyone</script>\n# ```"
    )
    assert "@everyone" not in module._display("@everyone")
    payload = analysis_evidence.analysis.model_dump(mode="json")
    model = payload["models"][0]
    hostile = (
        "![image](https://evil.invalid) [link](https://evil.invalid) "
        "<script>@everyone</script>\n# heading\n```"
    )
    model["generation_model"] = hostile
    metrics = model["audit_metrics"]
    metrics["generation_model"] = hostile
    metrics.pop("model_audit_metric_sha256")
    digest = stable_digest("laconian-model-audit-metric-v1", metrics)
    metrics["model_audit_metric_sha256"] = digest
    model["audit_gate"]["generation_model"] = hostile
    model["outcome"]["reasons"] = [f"Reviewer rationale: {hostile}"]
    for value in (*model["false_fail_limits"], model["sensitivity"]):
        value["generation_model"] = hostile
        value["model_audit_metric_sha256"] = digest
    payload.pop("campaign_analysis_sha256")
    payload["campaign_analysis_sha256"] = stable_digest("laconian-campaign-analysis-v1", payload)
    hostile_analysis = module.CampaignAnalysisV1.model_validate_json(canonical_json(payload))
    encoded = module.render_public_report(hostile_analysis).decode()
    assert hostile not in encoded
    for active in ("![image]", "[link]", "<script>", "@everyone", "\n# heading", "```"):
        assert active not in encoded
    assert "Reviewer rationale:" not in encoded  # The punctuation is encoded, too.
    assert "Reviewer rationale" in encoded


def test_analysis_writer_copies_verified_audit_parent_into_combined_result_root(
    analysis_evidence, tmp_path
):
    module = reporting()
    fixture = analysis_evidence.audit
    root = tmp_path / "combined"
    attachment = module.write_analysis_evidence_root(
        root,
        source_audit_root=fixture.root,
        provider_evidence=fixture.source.provider,
        audit=fixture.audit,
        bootstrap=analysis_evidence.bootstrap,
    )
    loaded = module.load_verified_analysis_evidence(root, provider_evidence=fixture.source.provider)
    assert loaded.attachment == attachment
    assert loaded.analysis == analysis_evidence.analysis
    assert loaded.report_bytes == analysis_evidence.report
    for path in fixture.root.rglob("*"):
        if path.is_file():
            assert (root / path.relative_to(fixture.root)).read_bytes() == path.read_bytes()
    assert len(list((root / "analysis").iterdir())) == 5


def reporting():
    assert importlib.util.find_spec("laconian_eval.benchmark.reporting") is not None, (
        "Task 13 must own the sealed reporting boundary"
    )
    return importlib.import_module("laconian_eval.benchmark.reporting")


@pytest.fixture
def literal_bootstrap():
    from laconian_eval.benchmark.bootstrap import make_cluster_vectors

    metadata, matrix = make_cluster_vectors(
        seed=42, scenario_uids=tuple(f"{i:064x}" for i in range(12))
    )
    return reporting().BootstrapArtifactV1(
        schema_version="bootstrap-artifact-v1",
        metadata=metadata,
        indices=tuple(tuple(int(value) for value in row) for row in matrix),
        bootstrap_artifact_sha256="f5c7612d9a9bac1a9f57cc3ce58078302ba22c9bf1825b0334a63764cd80195a",
    )


def test_bootstrap_artifact_literal_commitment_and_json_roundtrip(literal_bootstrap):
    assert literal_bootstrap.metadata.indices_sha256 == (
        "8c2ce05ebcab18fe5b75bc3ab5b4bb648cbcb790c9f587e16597f8ad77bc99b4"
    )
    assert (
        reporting().BootstrapArtifactV1.model_validate_json(literal_bootstrap.model_dump_json())
        == literal_bootstrap
    )
    assert (
        reporting()._checked(literal_bootstrap, reporting().BootstrapArtifactV1)
        == literal_bootstrap
    )


@pytest.mark.parametrize("mutation", ["shape", "range", "bool", "metadata", "digest", "owner"])
def test_bootstrap_artifact_builder_rejects_shape_range_metadata_or_digest_substitution(
    literal_bootstrap,
    mutation,
):
    payload = literal_bootstrap.model_dump(mode="json")
    if mutation == "shape":
        payload["indices"].pop()
    elif mutation == "range":
        payload["indices"][0][0] = 12
    elif mutation == "bool":
        payload["indices"][0][0] = True
    elif mutation == "metadata":
        payload["metadata"]["seed"] += 1
    elif mutation == "digest":
        payload["bootstrap_artifact_sha256"] = "0" * 64
    else:
        forged = literal_bootstrap.model_copy()
        object.__setattr__(forged, "indices", [[0] * 12] * 10000)
        with pytest.raises((ValueError, TypeError)):
            reporting()._checked(forged, reporting().BootstrapArtifactV1)
        return
    with pytest.raises((ValueError, TypeError)):
        reporting().BootstrapArtifactV1.model_validate_json(canonical_json(payload))


def test_distribution_median_preserves_integer_precision_under_small_decimal_context():
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 2
        summary = reporting()._distribution([10**30, 10**30 + 1], "tokens")
    assert summary.median == Decimal("1000000000000000000000000000000.5")


@pytest.mark.parametrize("missing", [False, True])
def test_usage_separates_missing_write_and_forbidden_write_source_bases(missing):
    from laconian_eval.benchmark.aggregation import PlannedObservationV1
    from tests.benchmark.helpers import compact_sensitivity_aggregate

    rows = tuple(
        PlannedObservationV1.model_validate(
            {
                **dict(row.__dict__),
                "cache_write_status": "missing" if missing else "reported_nonzero",
                "cache_write_tokens": None if missing else 2,
                "ordinary_uncached_input_tokens": None if missing else 18,
                "cache_policy_status": "missing_write_detail"
                if missing
                else "forbidden_nonzero_write",
                "cost_availability": "retained_worst_case" if missing else "trusted_usage",
            }
        )
        for row in compact_sensitivity_aggregate().rows
        if row.arm == "if"
    )
    usage = reporting()._usage(rows)
    assert usage.cache_write_tokens.missing_count == (120 if missing else 0)
    assert usage.cache_write_tokens.minimum == (None if missing else Decimal(2))
    assert usage.cache_read_tokens.minimum == Decimal(0)
    assert usage.ordinary_uncached_input_tokens.minimum == (None if missing else Decimal(18))
    assert usage.retained_worst_case_exposure_usd.observed_count == (120 if missing else 0)
    assert usage.trusted_usage_cost_usd.observed_count == (0 if missing else 120)


def test_visible_delta_median_adds_integer_endpoints_before_float_conversion(literal_bootstrap):
    from laconian_eval.benchmark.aggregation import PlannedObservationV1
    from tests.benchmark.helpers import compact_sensitivity_aggregate

    rows = []
    for row in compact_sensitivity_aggregate().rows:
        tokens = (0 if row.locale == "en" else 2**61 + 2) if row.arm == "concise" else 2**60
        rows.append(
            PlannedObservationV1.model_validate(
                {
                    **dict(row.__dict__),
                    "semantic_success": True,
                    "visible_output_tokens": tokens,
                    "output_tokens": tokens,
                    "total_tokens": row.input_tokens + tokens,
                }
            )
        )
    _, _, interval = reporting()._quality_intervals(tuple(rows), literal_bootstrap, "hard")
    assert (interval.point, interval.lower, interval.upper) == (1.0, 1.0, 1.0)


def test_analysis_writers_are_canonical_failure_atomic_and_no_replace(tmp_path, monkeypatch):
    module = reporting()
    output = tmp_path / "published"
    source = {"analysis/report.md": b"fixed report\n", "audit/component.json": b"{}\n"}
    primary = RuntimeError("fresh-loader failure")

    def fail():
        raise primary

    with pytest.raises(RuntimeError, match="fresh-loader failure"):
        module._publish(output, source, fail)
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []
    output.mkdir()
    (output / "sentinel").write_bytes(b"preexisting")
    with pytest.raises(FileExistsError):
        module._publish(output, source, fail)
    assert (output / "sentinel").read_bytes() == b"preexisting"


def test_publication_preserves_primary_failure_when_cleanup_also_fails(tmp_path, monkeypatch):
    module = reporting()
    original_cleanup = module.cleanup_owned_staging
    primary = RuntimeError("primary write failure")

    def fail_write(*args):
        raise primary

    def fail_cleanup(*args, **kwargs):
        original_cleanup(*args, **kwargs)
        raise OSError("secondary teardown error")

    monkeypatch.setattr(module, "_write_sample_member", fail_write)
    monkeypatch.setattr(module, "cleanup_owned_staging", fail_cleanup)
    with pytest.raises(RuntimeError, match="primary write failure"):
        module._publish(tmp_path / "out", {"audit/a.json": b"{}\n"}, lambda: None)


def test_publication_closes_parent_when_posix_construction_fails(tmp_path, monkeypatch):
    import os

    module = reporting()
    original = module.open_directory_no_follow
    captured = []

    def capture(path):
        descriptor = original(path)
        captured.append(descriptor)
        return descriptor

    def fail():
        raise RuntimeError("POSIX construction failed")

    monkeypatch.setattr(module, "open_directory_no_follow", capture)
    monkeypatch.setattr(module, "PosixOps", fail)
    with pytest.raises(RuntimeError, match="POSIX construction failed"):
        module._publish(tmp_path / "out", {"audit/a.json": b"{}\n"}, lambda: None)
    with pytest.raises(OSError):
        os.fstat(captured[0])


def test_publication_rolls_back_after_post_publish_parent_fsync_failure(tmp_path, monkeypatch):
    from laconian_eval.capsule.filesystem import PostPublishSyncError

    module = reporting()
    original = module.PosixOps.fsync
    output = tmp_path / "published"
    parent_identity = (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    failed = False

    def fail_once(self, descriptor):
        nonlocal failed
        current = os.fstat(descriptor)
        if not failed and output.exists() and (current.st_dev, current.st_ino) == parent_identity:
            failed = True
            raise OSError("injected parent fsync failure")
        return original(self, descriptor)

    monkeypatch.setattr(module.PosixOps, "fsync", fail_once)
    with pytest.raises(PostPublishSyncError):
        module._publish(output, {"audit/a.json": b"{}\n"}, lambda: None)
    assert failed
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_publication_never_removes_a_substituted_destination(tmp_path):
    module = reporting()
    output = tmp_path / "published"
    displaced = tmp_path / "displaced-owned-tree"

    def substitute():
        output.rename(displaced)
        output.mkdir()
        (output / "sentinel").write_bytes(b"not operation-owned")
        raise RuntimeError("verification failed after substitution")

    with pytest.raises(RuntimeError, match="verification failed") as failure:
        module._publish(output, {"audit/a.json": b"{}\n"}, substitute)
    assert (output / "sentinel").read_bytes() == b"not operation-owned"
    assert (displaced / "audit/a.json").read_bytes() == b"{}\n"
    assert any("rollback refused" in note for note in failure.value.__notes__)


@pytest.mark.parametrize("foreign_content", [False, True])
def test_rollback_never_removes_or_restores_late_quarantine_substitution(
    tmp_path, monkeypatch, foreign_content
):
    module = reporting()
    output = tmp_path / "published"
    displaced = tmp_path / "displaced-owned-root"
    real_fsync = os.fsync
    owned_identity = None
    foreign_path = None
    primary = RuntimeError("fresh verification failed")

    def fail_verify():
        nonlocal owned_identity
        metadata = output.stat()
        owned_identity = (metadata.st_dev, metadata.st_ino)
        raise primary

    def substitute_after_sync(descriptor):
        nonlocal foreign_path
        real_fsync(descriptor)
        metadata = os.fstat(descriptor)
        if foreign_path is not None or (metadata.st_dev, metadata.st_ino) != owned_identity:
            return
        candidates = tuple(tmp_path.glob(".laconian-rollback.*"))
        if len(candidates) == 1 and not tuple(candidates[0].iterdir()):
            foreign_path = candidates[0]
            foreign_path.rename(displaced)
            foreign_path.mkdir()
            if foreign_content:
                (foreign_path / "foreign-content").mkdir()

    monkeypatch.setattr(os, "fsync", substitute_after_sync)
    with pytest.raises(RuntimeError) as failure:
        module._publish(output, {"audit/a.json": b"{}\n"}, fail_verify)
    assert failure.value is primary
    assert foreign_path is not None and foreign_path.is_dir()
    assert displaced.is_dir()
    assert not output.exists()
    assert any("rollback refused" in note for note in primary.__notes__)


def test_publication_preserves_write_error_when_inner_descriptor_close_fails(tmp_path, monkeypatch):
    module = reporting()
    primary = RuntimeError("original write failure")
    real_close = os.close
    failed_descriptor = None
    attempted = []

    def fail_write(descriptor, *args):
        nonlocal failed_descriptor
        failed_descriptor = descriptor
        raise primary

    def close_then_fail(descriptor):
        attempted.append(descriptor)
        real_close(descriptor)
        if descriptor == failed_descriptor:
            raise OSError("secondary close failure")

    monkeypatch.setattr(module, "_write_sample_member", fail_write)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(RuntimeError) as failure:
        module._publish(tmp_path / "output", {"audit/a.json": b"{}\n"}, lambda: None)
    assert failure.value is primary
    assert attempted.count(failed_descriptor) == 1


def test_snapshot_preserves_read_error_and_closes_every_descriptor_once(tmp_path, monkeypatch):
    module = reporting()
    root = tmp_path / "root"
    (root / "audit").mkdir(parents=True)
    (root / "audit/a.json").write_bytes(b"{}\n")
    primary = RuntimeError("original read failure")
    real_close = os.close
    attempted = []
    failed_descriptor = None

    def fail_read(descriptor, size):
        nonlocal failed_descriptor
        failed_descriptor = descriptor
        raise primary

    def close_then_fail(descriptor):
        if failed_descriptor is not None:
            attempted.append(descriptor)
        real_close(descriptor)
        if descriptor == failed_descriptor:
            raise OSError("secondary close failure")

    monkeypatch.setattr(os, "read", fail_read)
    monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(RuntimeError) as failure:
        module._snapshot(root)
    assert failure.value is primary
    assert len(attempted) == len(set(attempted)) == 4


def _clone_audit(fixture, tmp_path):
    root = tmp_path / "audit-clone"
    shutil.copytree(fixture.root, root)
    return root


def _rehash_file(path, domain, field, change):
    payload = json.loads(path.read_bytes())
    change(payload)
    payload.pop(field)
    payload[field] = stable_digest(domain, payload)
    path.write_bytes(canonical_json(payload) + b"\n")


def test_audit_evidence_writer_is_canonical_failure_atomic_no_replace_and_fresh_reloads(
    audit_evidence,
    tmp_path,
    monkeypatch,
):
    module = reporting()
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "sentinel").write_bytes(b"untouched")
    with pytest.raises(FileExistsError):
        write_audit(audit_evidence.source, destination)
    assert (destination / "sentinel").read_bytes() == b"untouched"
    destination = tmp_path / "rollback"

    def fail(*args, **kwargs):
        raise RuntimeError("installed audit reload failure")

    monkeypatch.setattr(module, "load_verified_audit_evidence", fail)
    with pytest.raises(RuntimeError, match="installed audit reload failure"):
        write_audit(audit_evidence.source, destination)
    assert not destination.exists()


@pytest.mark.parametrize("attack", ["missing", "extra", "record", "source", "alias", "symlink"])
def test_verified_audit_loader_rejects_missing_extra_or_mismatched_review_source_or_record(
    audit_evidence,
    tmp_path,
    attack,
):
    root = _clone_audit(audit_evidence, tmp_path)
    directory = root / "audit/github-review-records"
    records = sorted(directory.iterdir())
    if attack == "missing":
        records[0].unlink()
    elif attack == "extra":
        (directory / "01.json").write_bytes(records[0].read_bytes())
    elif attack in {"record", "source"}:
        path = (
            records[0]
            if attack == "record"
            else root / "audit/github-review-sources" / records[0].name
        )
        path.write_bytes(b"{}\n")
    elif attack == "alias":
        records[1].unlink()
        os.link(records[0], records[1])
    else:
        original = records[0].read_bytes()
        records[0].unlink()
        outside = tmp_path / "outside.json"
        outside.write_bytes(original)
        records[0].symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


@pytest.mark.parametrize(
    "path", ["git-object-archive.json", "pull-request-sources/adjudication.json"]
)
def test_verified_audit_loader_rejects_archive_or_pull_request_source_substitution(
    audit_evidence,
    tmp_path,
    path,
):
    root = _clone_audit(audit_evidence, tmp_path)
    target = root / "audit" / path
    payload = json.loads(target.read_bytes())
    payload[next(field for field in payload if field.endswith("sha256"))] = "0" * 64
    target.write_bytes(canonical_json(payload) + b"\n")
    with pytest.raises(ValueError):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


@pytest.mark.parametrize("attack", ["proof", "identity"])
def test_verified_audit_loader_rejects_reviewer_chain_proof_or_account_identity_substitution(
    audit_evidence,
    tmp_path,
    attack,
):
    root = _clone_audit(audit_evidence, tmp_path)
    target = next((root / "audit/reviewer-chains").iterdir())
    if attack == "proof":
        payload = json.loads(target.read_bytes())
        payload["reviewer_chain_proof_sha256"] = "0" * 64
        target.write_bytes(canonical_json(payload) + b"\n")
    else:

        def mutate(payload):
            payload["identity"]["reviewer_numeric_account_id"] = 999999

        _rehash_file(
            target, "laconian-audit-reviewer-chain-proof-v1", "reviewer_chain_proof_sha256", mutate
        )
    with pytest.raises(ValueError):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


def test_verified_audit_loader_recomputes_every_component_and_root_digest(audit_evidence, tmp_path):
    root = _clone_audit(audit_evidence, tmp_path)
    target = root / "audit/audit-evidence.json"
    _rehash_file(
        target,
        "laconian-verified-audit-evidence-v1",
        "audit_evidence_sha256",
        lambda payload: payload.update(blind_packet_sha256="0" * 64),
    )
    with pytest.raises(ValueError):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


def test_audit_attachment_directly_binds_all_four_layer_vectors_and_judge_attempt_vector(
    audit_evidence,
):
    attachment = audit_evidence.audit.attachment
    for name in (
        "ordered_generation_capsule_sha256s",
        "ordered_hard_score_request_set_sha256s",
        "ordered_judge_request_attachment_sha256s",
        "ordered_judge_attachment_sha256s",
        "ordered_judge_attempt_boundary_sha256s",
    ):
        assert len(getattr(attachment, name)) == 36
        assert getattr(attachment, name) == getattr(audit_evidence.source.provider.index, name)
    assert attachment.judge_attempt_root_index_sha256 == (
        audit_evidence.source.provider.index.judge_attempt_root_index_sha256
    )


@pytest.mark.parametrize("position", [None, *range(36)])
def test_verified_audit_loader_rejects_provider_projection_or_any_of_36_judge_parent_substitutions(
    audit_evidence,
    tmp_path,
    position,
):
    root = _clone_audit(audit_evidence, tmp_path)

    def mutate(payload):
        if position is None:
            payload["provider_projection_root"] = "1" * 64
        else:
            payload["ordered_judge_attachment_sha256s"][position] = "0" * 64

    _rehash_file(
        root / "audit/audit-evidence.json",
        "laconian-verified-audit-evidence-v1",
        "audit_evidence_sha256",
        mutate,
    )
    with pytest.raises(ValueError):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


def test_complete_audit_allowlist_is_checked_before_population_byte_admission(
    audit_evidence, tmp_path, monkeypatch
):
    root = _clone_audit(audit_evidence, tmp_path)
    (root / "audit/surplus.json").write_bytes(b"{}\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("population byte owner must not see a nonallowlisted tree")

    monkeypatch.setattr(reporting(), "_load_verified_audit_population_from_bytes", forbidden)
    with pytest.raises(ValueError, match="allowlist"):
        reporting().load_verified_audit_evidence(
            root, provider_evidence=audit_evidence.source.provider
        )


def test_standalone_sample_loader_still_rejects_the_expanded_audit_tree(audit_evidence):
    from laconian_eval.benchmark.audit_sampling import load_verified_audit_sample_root

    with pytest.raises(ValueError, match="allowlist"):
        load_verified_audit_sample_root(
            audit_evidence.root, provider_evidence=audit_evidence.source.provider
        )


def test_primary_coverage_uses_complete_semantic_pairs_without_extra_hard_token_gate():
    from laconian_eval.benchmark.aggregation import PairDenominatorsV1
    from laconian_eval.benchmark.bootstrap import BootstrapIntervalV1

    interval = BootstrapIntervalV1(
        point=0.0, lower=0.0, upper=0.0, valid_replicates=10000, available=True
    )
    denominator = PairDenominatorsV1(eligible_pairs=119, token_pairs=119, eligible_scenarios=12)
    assert reporting()._confirmatory_coverage(denominator, interval, interval, interval)
    missing = PairDenominatorsV1(eligible_pairs=119, token_pairs=118, eligible_scenarios=12)
    assert not reporting()._confirmatory_coverage(missing, interval, interval, interval)


def test_reporting_bootstrap_matches_independent_resampled_integer_medians(literal_bootstrap):
    from statistics import median

    import numpy as np

    from tests.benchmark.helpers import compact_sensitivity_aggregate

    aggregate = compact_sensitivity_aggregate()
    by_key = {
        (row.scenario_uid, row.case_id, row.locale, row.repetition, row.arm): row
        for row in aggregate.rows
    }
    blocks = []
    for uid in literal_bootstrap.metadata.scenario_uids:
        block = []
        for row in aggregate.rows:
            if row.scenario_uid == uid and row.arm == "if":
                other = by_key[(uid, row.case_id, row.locale, row.repetition, "concise")]
                if row.semantic_success and other.semantic_success:
                    block.append(other.visible_output_tokens - row.visible_output_tokens)
        blocks.append(block)
    medians = [
        median([value for cluster in vector for value in blocks[cluster]])
        for vector in literal_bootstrap.indices
    ]
    expected = np.quantile(medians, (0.025, 0.975), method="linear")
    _, _, actual = reporting()._quality_intervals(aggregate.rows, literal_bootstrap, "semantic")
    assert actual.point == median([value for block in blocks for value in block])
    assert (actual.lower, actual.upper) == tuple(expected)


@pytest.fixture(scope="module")
def combined_evidence(analysis_evidence):
    source = analysis_evidence.audit
    root = source.source.directory / "combined"
    reporting().write_analysis_evidence_root(
        root,
        source_audit_root=source.root,
        provider_evidence=source.source.provider,
        audit=source.audit,
        bootstrap=analysis_evidence.bootstrap,
    )
    return SimpleNamespace(root=root, source=analysis_evidence)


@pytest.mark.parametrize("attack", ["extra-file", "empty-directory", "partial-analysis"])
def test_analysis_writer_rechecks_source_allowlist_after_fresh_audit_load(
    analysis_evidence, tmp_path, monkeypatch, attack
):
    module = reporting()
    source = tmp_path / "source"
    destination = tmp_path / "output"
    shutil.copytree(analysis_evidence.audit.root, source)
    real_load = module.load_verified_audit_evidence

    def load_then_change(root, *, provider_evidence):
        fresh = real_load(root, provider_evidence=provider_evidence)
        if root == source:
            if attack == "extra-file":
                (source / "audit/extra.json").write_bytes(b"{}\n")
            elif attack == "empty-directory":
                (source / "audit/extra-directory").mkdir()
            else:
                (source / "analysis").mkdir()
                (source / "analysis/report.md").write_bytes(b"partial\n")
        return fresh

    def unexpected_publish(*args, **kwargs):
        raise AssertionError("source mutation must be rejected before publication")

    monkeypatch.setattr(module, "load_verified_audit_evidence", load_then_change)
    monkeypatch.setattr(module, "_publish", unexpected_publish)
    with pytest.raises(ValueError, match=r"allowlist|partial"):
        module.write_analysis_evidence_root(
            destination,
            source_audit_root=source,
            provider_evidence=analysis_evidence.audit.source.provider,
            audit=analysis_evidence.audit.audit,
            bootstrap=analysis_evidence.bootstrap,
        )
    assert not destination.exists()


def test_analysis_writer_accepts_complete_combined_source(combined_evidence, tmp_path):
    module = reporting()
    evidence = combined_evidence.source
    attachment = module.write_analysis_evidence_root(
        tmp_path / "copy",
        source_audit_root=combined_evidence.root,
        provider_evidence=evidence.audit.source.provider,
        audit=evidence.audit.audit,
        bootstrap=evidence.bootstrap,
    )
    original = module.AnalysisEvidenceAttachmentV1.model_validate_json(
        (combined_evidence.root / "analysis/analysis-evidence.json").read_bytes(), strict=True
    )
    assert attachment == original


@pytest.mark.parametrize("attack", ["extra-file", "empty-directory", "partial-analysis"])
def test_audit_copy_snapshot_checks_all_files_and_directories(tmp_path, attack):
    module = reporting()
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit/a.json").write_bytes(b"{}\n")
    expected = {"audit/a.json": b"{}\n"}
    if attack == "extra-file":
        (tmp_path / "audit/extra.json").write_bytes(b"{}\n")
    elif attack == "empty-directory":
        (tmp_path / "audit/extra").mkdir()
    else:
        (tmp_path / "analysis").mkdir()
        (tmp_path / "analysis/report.md").write_bytes(b"partial\n")
    with pytest.raises(ValueError, match=r"allowlist|partial"):
        module._check_audit_copy_tree(module._snapshot(tmp_path), expected)


def _resign_analysis_root(root, *, analysis_payload=None, report_bytes=None):
    directory = root / "analysis"
    if analysis_payload is not None:
        analysis_payload.pop("campaign_analysis_sha256")
        analysis_payload["campaign_analysis_sha256"] = stable_digest(
            "laconian-campaign-analysis-v1", analysis_payload
        )
        (directory / "analysis.json").write_bytes(canonical_json(analysis_payload) + b"\n")
    if report_bytes is not None:
        (directory / "report.md").write_bytes(report_bytes)
    checksum = {"schema_version": "analysis-checksums-v1", "entries": []}
    for name in ("analysis.json", "bootstrap.json", "report.md"):
        raw = (directory / name).read_bytes()
        checksum["entries"].append(
            {
                "relative_path": f"analysis/{name}",
                "byte_length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    checksum["checksums_sha256"] = stable_digest("laconian-analysis-checksums-v1", checksum)
    (directory / "checksums.json").write_bytes(canonical_json(checksum) + b"\n")
    attachment = json.loads((directory / "analysis-evidence.json").read_bytes())
    attachment["checksums_sha256"] = checksum["checksums_sha256"]
    attachment["report_sha256"] = hashlib.sha256((directory / "report.md").read_bytes()).hexdigest()
    attachment["campaign_analysis_sha256"] = json.loads((directory / "analysis.json").read_bytes())[
        "campaign_analysis_sha256"
    ]
    attachment.pop("analysis_evidence_sha256")
    attachment["analysis_evidence_sha256"] = stable_digest(
        "laconian-verified-analysis-evidence-v1", attachment
    )
    (directory / "analysis-evidence.json").write_bytes(canonical_json(attachment) + b"\n")


@pytest.mark.parametrize("artifact", ["report", "bootstrap", "attachment"])
def test_verified_analysis_loader_rejects_report_bootstrap_or_attachment_substitution(
    combined_evidence,
    tmp_path,
    artifact,
):
    root = tmp_path / "combined-clone"
    shutil.copytree(combined_evidence.root, root)
    if artifact == "report":
        _resign_analysis_root(root, report_bytes=b"# Forged report\n")
    elif artifact == "bootstrap":
        path = root / "analysis/bootstrap.json"
        payload = json.loads(path.read_bytes())
        payload["indices"][0][0] = (payload["indices"][0][0] + 1) % 12
        path.write_bytes(canonical_json(payload) + b"\n")
        _resign_analysis_root(root)
    else:
        _rehash_file(
            root / "analysis/analysis-evidence.json",
            "laconian-verified-analysis-evidence-v1",
            "analysis_evidence_sha256",
            lambda payload: payload.update(audit_evidence_sha256="0" * 64),
        )
    with pytest.raises(ValueError):
        reporting().load_verified_analysis_evidence(
            root, provider_evidence=combined_evidence.source.audit.source.provider
        )


def test_verified_analysis_loader_rejects_analysis_only_root_without_bound_audit_tree(
    combined_evidence, tmp_path
):
    root = tmp_path / "analysis-only"
    root.mkdir()
    shutil.copytree(combined_evidence.root / "analysis", root / "analysis")
    with pytest.raises(ValueError):
        reporting().load_verified_analysis_evidence(
            root, provider_evidence=combined_evidence.source.audit.source.provider
        )


def test_analysis_writer_and_loader_rederive_analysis_before_accepting_bytes(
    combined_evidence, tmp_path
):
    root = tmp_path / "aggregate-forgery"
    shutil.copytree(combined_evidence.root, root)
    path = root / "analysis/analysis.json"
    payload = json.loads(path.read_bytes())
    interval = payload["models"][0]["hard_pass_by_arm"]["if"]
    interval.update(point=0.25, lower=0.25, upper=0.25)
    payload.pop("campaign_analysis_sha256")
    payload["campaign_analysis_sha256"] = stable_digest("laconian-campaign-analysis-v1", payload)
    forged = reporting().CampaignAnalysisV1.model_validate_json(canonical_json(payload))
    _resign_analysis_root(
        root, analysis_payload=payload, report_bytes=reporting().render_public_report(forged)
    )
    with pytest.raises(ValueError, match="rederivation"):
        reporting().load_verified_analysis_evidence(
            root, provider_evidence=combined_evidence.source.audit.source.provider
        )


def test_analysis_builder_rederives_aggregates_only_from_verified_provider_evidence(
    analysis_evidence, monkeypatch
):
    module = reporting()
    provider = analysis_evidence.audit.source.provider
    real_aggregate = module.aggregate_verified_evidence
    calls = []

    def observe_aggregate(*, provider_evidence):
        calls.append(provider_evidence)
        return real_aggregate(provider_evidence=provider_evidence)

    monkeypatch.setattr(module, "aggregate_verified_evidence", observe_aggregate)
    derived = module.analyze_campaign(
        provider_evidence=provider,
        audit=analysis_evidence.audit.audit,
        vectors=analysis_evidence.bootstrap,
    )
    assert derived == analysis_evidence.analysis
    assert len(calls) == 1 and calls[0] is not provider
    assert calls[0].projection == provider.projection
    # A copied provider cannot gain mint authority even if all caller-visible fields exist.
    with pytest.raises((TypeError, ValueError)):
        forged = replace(provider, index=provider.index.model_copy())
        module.analyze_campaign(
            provider_evidence=forged,
            audit=analysis_evidence.audit.audit,
            vectors=analysis_evidence.bootstrap,
        )


def _test_protocol_binding(analysis_evidence, field):
    module = reporting()
    payload = analysis_evidence.audit.audit.attachment.model_dump(mode="json")
    payload[field] = "0" * 64
    payload["protocol_bindings"][field] = "0" * 64
    payload.pop("audit_evidence_sha256")
    payload["audit_evidence_sha256"] = stable_digest("laconian-verified-audit-evidence-v1", payload)
    attachment = module.AuditEvidenceAttachmentV1.model_validate_json(canonical_json(payload))
    audit = replace(analysis_evidence.audit.audit, attachment=attachment)
    with pytest.raises(ValueError, match="fixed provider parent"):
        module.analyze_campaign(
            provider_evidence=analysis_evidence.audit.source.provider,
            audit=audit,
            vectors=analysis_evidence.bootstrap,
        )


def _test_stored_protocol_binding(combined_evidence, tmp_path, field):
    root = tmp_path / field
    shutil.copytree(combined_evidence.root, root)
    payload = json.loads((root / "analysis/analysis.json").read_bytes())
    payload[field] = "0" * 64
    payload["protocol_bindings"][field] = "0" * 64
    manifest = payload["audit_sample_manifest"]
    manifest["protocol_bindings"][field] = "0" * 64
    if field in manifest:
        manifest[field] = "0" * 64
    manifest.pop("sample_manifest_sha256")
    manifest["sample_manifest_sha256"] = stable_digest(
        "laconian-audit-sample-manifest-v1", manifest
    )
    for model in payload["models"]:
        metrics = model["audit_metrics"]
        metrics["protocol_bindings"][field] = "0" * 64
        metrics.pop("model_audit_metric_sha256")
        digest = stable_digest("laconian-model-audit-metric-v1", metrics)
        metrics["model_audit_metric_sha256"] = digest
        for component in (*model["false_fail_limits"], model["sensitivity"]):
            component["model_audit_metric_sha256"] = digest
    payload.pop("campaign_analysis_sha256")
    payload["campaign_analysis_sha256"] = stable_digest("laconian-campaign-analysis-v1", payload)
    forged = reporting().CampaignAnalysisV1.model_validate_json(
        canonical_json(payload), strict=True
    )
    _resign_analysis_root(
        root, analysis_payload=payload, report_bytes=reporting().render_public_report(forged)
    )

    def mutate_attachment(value):
        value[field] = "0" * 64
        value["protocol_bindings"][field] = "0" * 64

    _rehash_file(
        root / "analysis/analysis-evidence.json",
        "laconian-verified-analysis-evidence-v1",
        "analysis_evidence_sha256",
        mutate_attachment,
    )
    with pytest.raises(ValueError, match="fixed provider"):
        reporting().load_verified_analysis_evidence(
            root, provider_evidence=combined_evidence.source.audit.source.provider
        )


def test_analysis_builder_and_loader_require_provider_bound_statistical_protocol(
    analysis_evidence, combined_evidence, tmp_path
):
    _test_protocol_binding(analysis_evidence, "statistical_protocol_sha256")
    _test_stored_protocol_binding(combined_evidence, tmp_path, "statistical_protocol_sha256")


def test_analysis_builder_and_loader_require_exact_provider_bound_audit_protocol(
    analysis_evidence, combined_evidence, tmp_path
):
    _test_protocol_binding(analysis_evidence, "audit_protocol_sha256")
    _test_stored_protocol_binding(combined_evidence, tmp_path, "audit_protocol_sha256")


@pytest.mark.parametrize("field", tuple(BenchmarkProtocolBindingsV1.model_fields))
def test_every_rehashed_protocol_binding_is_rejected_against_fixed_provider(audit_evidence, field):
    module = reporting()
    payload = audit_evidence.audit.attachment.model_dump(mode="json")
    payload["protocol_bindings"][field] = "0" * 64
    if field in payload:
        payload[field] = "0" * 64
    payload.pop("audit_evidence_sha256")
    payload["audit_evidence_sha256"] = stable_digest("laconian-verified-audit-evidence-v1", payload)
    attachment = module.AuditEvidenceAttachmentV1.model_validate_json(canonical_json(payload))
    audit = replace(audit_evidence.audit, attachment=attachment)
    with pytest.raises(ValueError, match="fixed provider parent"):
        module._revalidate_audit(audit, audit_evidence.source.provider)


def test_unestimable_limits_require_zero_space_instead_of_placeholder_a_formula(analysis_evidence):
    module = reporting()
    payload = analysis_evidence.analysis.models[0].model_dump(mode="json")
    for limit in payload["false_fail_limits"]:
        limit.update(
            estimable=False, upper_false_fail=None, k_max_reclassified=limit["d_known_false_fail"]
        )
    sensitivity = payload["sensitivity"]
    sensitivity.update(
        assignment_count=0,
        visited_nodes=0,
        evaluated_assignments=0,
        search_exhausted=False,
        exhaustion_reason=None,
        certificate_sha256=None,
        semantic_min_lower=None,
        semantic_max_upper=None,
        token_min_lower=None,
        token_max_upper=None,
    )
    assert (
        module.ModelAnalysisV1.model_validate_json(
            canonical_json(payload)
        ).sensitivity.assignment_count
        == 0
    )
    for change in (
        {"assignment_count": 1},
        {"visited_nodes": 1},
        {"evaluated_assignments": 1},
        {"certificate_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError):
            module.ModelAnalysisV1.model_validate_json(
                canonical_json({**payload, "sensitivity": {**sensitivity, **change}})
            )


@pytest.mark.parametrize(
    "policy,reason",
    [
        ("missing_write_detail", "cache_write_detail_missing"),
        ("forbidden_nonzero_write", "forbidden_cache_write_observed"),
    ],
)
def test_report_surfaces_missing_or_forbidden_cache_write_integrity_limitations(
    analysis_evidence,
    policy,
    reason,
):
    payload = analysis_evidence.analysis.model_dump(mode="json")
    usage = payload["models"][0]["usage_by_arm"]["if"]
    usage["cache_policy_status_counts"] = {
        key: 120 if key == policy else 0 for key in usage["cache_policy_status_counts"]
    }
    if policy == "missing_write_detail":
        usage["cache_write_tokens"].update(
            observed_count=0, missing_count=120, minimum=None, median=None, maximum=None
        )
    payload.pop("campaign_analysis_sha256")
    payload["campaign_analysis_sha256"] = stable_digest("laconian-campaign-analysis-v1", payload)
    analysis = reporting().CampaignAnalysisV1.model_validate_json(canonical_json(payload))
    report = reporting().render_public_report(analysis).decode()
    assert reason in next(line for line in report.splitlines() if line.startswith("Outcome:"))
    assert any(
        reason in line and "Cost availability counts" in line for line in report.splitlines()
    )


def test_distribution_requires_coherent_finite_values_and_exact_counts():
    owner = reporting().DistributionSummaryV1
    good = dict(
        unit="tokens",
        observed_count=1,
        missing_count=119,
        minimum=Decimal(1),
        median=Decimal(1),
        maximum=Decimal(1),
    )
    assert owner(**good).observed_count == 1
    for change in (
        {"minimum": Decimal("NaN")},
        {"observed_count": True},
        {"median": Decimal(0)},
        {"observed_count": 0},
        {"minimum": None},
        {"surprise": 1},
    ):
        with pytest.raises((TypeError, ValueError)):
            owner(**(good | change))


@pytest.mark.parametrize("attack", ["mapping", "top_extra", "nested_extra"])
def test_reporting_models_reject_python_substitutions_before_normalization(
    literal_bootstrap, attack
):
    owner = reporting().BootstrapArtifactV1
    artifact = literal_bootstrap
    if attack == "mapping":

        class ForeignMapping(dict):
            pass

        value = ForeignMapping(artifact.model_dump())
    elif attack == "top_extra":
        value = artifact.model_copy(deep=True)
        object.__setattr__(value, "unexpected", True)
    else:
        value = artifact.model_dump()
        metadata = artifact.metadata.model_copy(deep=True)
        object.__setattr__(metadata, "unexpected", True)
        value["metadata"] = metadata
    with pytest.raises((TypeError, ValueError)):
        owner.model_validate(value)


def test_large_search_space_limitation_is_unambiguously_inconclusive():
    limitation = reporting()._LIMITATIONS[-1]
    assert "4096 reach either" in limitation
    assert "and are inconclusive" in limitation
    assert "may hit" not in limitation


def test_false_fail_u_discloses_model_wide_unresolved_veto():
    from laconian_eval.benchmark.audit_metrics import ModelAuditMetricsV1
    from tests.benchmark.test_sensitivity_direct import _metrics

    payload = _metrics().model_dump(mode="json")
    payload["agreement"].update(
        point=None,
        effective_n=None,
        lower=None,
        upper=None,
        available=False,
        unavailable_reasons=["unresolved_sampled_consensus"],
    )
    payload.pop("model_audit_metric_sha256")
    payload["model_audit_metric_sha256"] = stable_digest("laconian-model-audit-metric-v1", payload)
    metrics = ModelAuditMetricsV1.model_validate_json(canonical_json(payload))
    assert metrics.false_fail_by_primary_arm["if"].available
    assert reporting()._limit_unavailability(metrics, "if") == ("unresolved_sampled_consensus",)


def test_reporting_admission_revalidates_imported_nonrevalidating_owner():
    from laconian_eval.benchmark.outcomes import ModelOutcomeV1

    class Envelope(reporting()._ReportModel):
        outcome: ModelOutcomeV1

    # This imported exact owner does not itself revalidate existing instances.
    forged = ModelOutcomeV1.model_construct(outcome="bogus", reasons=())
    with pytest.raises((TypeError, ValueError)):
        Envelope(outcome=forged)


@pytest.mark.parametrize("field", ["outcome", "hard_primary_difference"])
def test_model_analysis_admission_revalidates_forged_imported_owner(analysis_evidence, field):
    from laconian_eval.benchmark.bootstrap import BootstrapIntervalV1
    from laconian_eval.benchmark.outcomes import ModelOutcomeV1

    original = analysis_evidence.analysis.models[0]
    forged = (
        ModelOutcomeV1.model_construct(outcome="bogus", reasons=())
        if field == "outcome"
        else BootstrapIntervalV1.model_construct(
            **{**dict(original.hard_primary_difference.__dict__), "lower": 2.0, "upper": 1.0}
        )
    )
    with pytest.raises((TypeError, ValueError)):
        reporting().ModelAnalysisV1.model_validate({**dict(original.__dict__), field: forged})


def test_bootstrap_artifact_builder_has_no_raw_seed_or_protocol_override():
    assert tuple(inspect.signature(reporting().build_bootstrap_artifact).parameters) == (
        "provider_evidence",
    )


def test_analysis_builder_has_no_bare_aggregate_hard_set_or_judge_attachment_override():
    assert tuple(inspect.signature(reporting().analyze_campaign).parameters) == (
        "provider_evidence",
        "audit",
        "vectors",
    )
    assert tuple(inspect.signature(reporting().write_analysis_evidence_root).parameters) == (
        "output_root",
        "source_audit_root",
        "provider_evidence",
        "audit",
        "bootstrap",
    )


def test_campaign_analysis_hash_binds_manifest_immediately_before_models():
    fields = tuple(reporting().CampaignAnalysisV1.model_fields)
    assert fields[fields.index("models") - 1] == "audit_sample_manifest"


def test_public_evidence_owners_are_lazy_package_exports():
    module = reporting()
    package = importlib.import_module("laconian_eval.benchmark")
    for name in (
        "VerifiedAuditEvidenceV1",
        "VerifiedAnalysisEvidenceV1",
        "load_verified_audit_evidence",
        "load_verified_analysis_evidence",
        "write_audit_evidence_root",
        "write_analysis_evidence_root",
        "BootstrapArtifactV1",
        "build_bootstrap_artifact",
        "AuditEvidenceAttachmentV1",
        "AnalysisEvidenceAttachmentV1",
    ):
        assert getattr(package, name) is getattr(module, name)
