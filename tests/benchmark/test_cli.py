"""Public CLI contract for the offline, non-evidentiary benchmark replay."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from laconian_eval import cli
from laconian_eval.capsule.canonical import canonical_json, stable_digest

COMMANDS = (
    "hard-score",
    "prepare-judge",
    "seal-judge",
    "sample-audit",
    "seal-audit",
    "analyze",
    "verify",
)
GENERATION_OPTIONS = ("generation-expectation", "generation-index", "generation-root")
PROVIDER_OPTIONS = (
    "generation-expectation",
    "provider-index",
    "generation-root",
    "hard-score-root",
    "judge-request-root",
    "judge-root",
)
OPTIONS = {
    "hard-score": (*GENERATION_OPTIONS, "output-root"),
    "prepare-judge": (*GENERATION_OPTIONS, "hard-score-root", "output-root"),
    "seal-judge": (
        *GENERATION_OPTIONS,
        "hard-score-root",
        "judge-request-root",
        "judge-attempt-root",
        "output-root",
    ),
    "sample-audit": (*PROVIDER_OPTIONS, "output-root"),
    "seal-audit": (*PROVIDER_OPTIONS, "review-root", "output-root"),
    "analyze": (*PROVIDER_OPTIONS, "audit-root", "output-root"),
    "verify": (*PROVIDER_OPTIONS, "result-root", "protocol-review-archive"),
}


def _argv(command, root=None, output=None, **overrides):
    root = Path("canary-private-model-prompt-label") if root is None else root
    paths = {
        "generation-expectation": root / "GENERATION_COMPLETE/generation-context-expectation.json",
        "generation-index": root / "GENERATION/generation-context.json",
        "generation-root": root / "GENERATION",
        "hard-score-root": root / "HARD",
        "judge-request-root": root / "REQUESTS",
        "judge-attempt-root": root / "ATTEMPTS",
        "provider-index": root / "JUDGES/provider-evidence-index.json",
        "judge-root": root / "JUDGES",
        "review-root": root / "REVIEWS",
        "audit-root": root / "audit-evidence",
        "result-root": root / "result",
        "protocol-review-archive": root / "protocol-review-archive.json",
        "output-root": output or root / "offline-output",
    }
    paths.update(overrides)
    return [
        command,
        *(value for option in OPTIONS[command] for value in ("--" + option, str(paths[option]))),
    ]


def _closed_error(capsys, code, command):
    output = capsys.readouterr()
    assert output.out == ""
    assert (
        output.err.encode()
        == canonical_json({"code": code, "command": command, "status": "error"}) + b"\n"
    )


def _snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mode,
            path.lstat().st_ino,
            path.lstat().st_mtime_ns,
            path.lstat().st_ctime_ns,
            path.lstat().st_nlink,
            path.lstat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    }


def test_help_lists_exact_seven_commands_and_no_abbreviated_command_is_accepted(capsys):
    assert importlib.util.find_spec("laconian_eval.replay") is not None, (
        "offline benchmark parser is not implemented"
    )
    assert cli.main(["--help"], program="laconian-benchmark") == 0
    output = capsys.readouterr()
    assert "{" + ",".join(COMMANDS) + "}" in output.out
    assert output.err == ""
    assert cli.main(["--help", "--canary-unknown"], program="laconian-benchmark") == 2
    _closed_error(capsys, "usage", None)
    for command in COMMANDS:
        assert cli.main([command[:-1]], program="laconian-benchmark") == 2
        output = capsys.readouterr()
        assert output.out == ""
        assert json.loads(output.err) == {"code": "usage", "command": None, "status": "error"}
        assert cli.main([command, "--help", "--canary-unknown"], program="laconian-benchmark") == 2
        _closed_error(capsys, "usage", command)


def test_cli_main_signature_is_exactly_main_argv_program_none_and_preserves_legacy_dispatch(capsys):
    signature = inspect.signature(cli.main)
    assert tuple(signature.parameters) == ("argv", "program")
    assert signature.parameters["argv"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["program"].kind is inspect.Parameter.KEYWORD_ONLY
    assert all(item.default is None for item in signature.parameters.values())
    assert cli.main(argv=["--help"], program="laconian-benchmark") == 0
    help_output = capsys.readouterr()
    assert "{" + ",".join(COMMANDS) + "}" in help_output.out and help_output.err == ""
    assert cli.main(["--help"], program="laconian") == 0
    assert "{validate,plan,verify,resume,finalize,run,score,report}" in capsys.readouterr().out
    assert cli.main(["--help"], program="canary-private-program") == 2
    _closed_error(capsys, "usage", None)
    for program, commands in (
        ("laconian", "{validate,plan,verify,resume,finalize,run,score,report}"),
        ("laconian-benchmark", "{" + ",".join(COMMANDS) + "}"),
    ):
        script = Path(sys.executable).parent / program
        result = subprocess.run([str(script), "--help"], capture_output=True, check=False)
        assert result.returncode == 0 and result.stderr == b""
        assert commands.encode() in result.stdout


def test_help_lists_offline_replay_only_and_never_names_live_callables(capsys):
    notice = (
        "OFFLINE NON-EVIDENTIARY VALIDATION ONLY; replay validates structure but cannot "
        "authorize live execution"
    )
    for command in COMMANDS:
        assert cli.main([command, "--help"], program="laconian-benchmark") == 0
        output = capsys.readouterr()
        normalized = " ".join(output.out.split())
        assert notice in normalized
        assert output.err == ""
        for forbidden in ("load_verified", "build_", "publish", "run_live", "campaign_state"):
            assert forbidden not in output.out
        if command != "verify":
            assert "offline report only; never later-stage input" in normalized


def test_every_option_rejects_abbreviation_and_every_command_rejects_unknown_options(capsys):
    for command in COMMANDS:
        for option in OPTIONS[command]:
            argv = _argv(command)
            argv[argv.index("--" + option)] = "--" + option[:-1]
            assert cli.main(argv, program="laconian-benchmark") == 2
            _closed_error(capsys, "usage", command)
            assert (
                cli.main(
                    [*_argv(command), "--" + option, "canary-private-duplicate"],
                    program="laconian-benchmark",
                )
                == 2
            )
            _closed_error(capsys, "usage", command)
        assert cli.main([*_argv(command), "--canary-secret"], program="laconian-benchmark") == 2
        _closed_error(capsys, "usage", command)


def test_all_seven_commands_require_one_canonical_generation_expectation_path(
    replay_campaign, tmp_path, capsys
):
    for command in COMMANDS:
        argv = _argv(command)
        del argv[1:3]
        assert cli.main(argv, program="laconian-benchmark") == 2
        _closed_error(capsys, "usage", command)
        copied = tmp_path / (command + "-copied-expectation.json")
        copied.write_bytes(
            (
                replay_campaign.workspace_root
                / "GENERATION_COMPLETE/generation-context-expectation.json"
            ).read_bytes()
        )
        before = _snapshot(replay_campaign.workspace_root)
        assert (
            cli.main(
                _argv(
                    command,
                    replay_campaign.workspace_root,
                    tmp_path / command,
                    **{"generation-expectation": copied},
                ),
                program="laconian-benchmark",
            )
            == 3
        )
        _closed_error(capsys, "verification-failed", command)
        assert _snapshot(replay_campaign.workspace_root) == before
        assert not (tmp_path / command).exists()


def test_no_command_accepts_seed_commit_source_protocol_workflow_or_any_digest_flag(capsys):
    forbidden = (
        "seed",
        "campaign-seed",
        "commit",
        "input-tag-commit",
        "source-protocol",
        "workflow",
        "workflow-root",
        "digest",
        "generation-context-expectation-sha256",
        "model",
        "command",
        "reason",
    )
    for command in COMMANDS:
        for option in forbidden + (() if command == "verify" else ("protocol-review-archive",)):
            assert (
                cli.main(
                    [*_argv(command), "--" + option, "canary-private"], program="laconian-benchmark"
                )
                == 2
            )
            _closed_error(capsys, "usage", command)


@pytest.mark.parametrize("command", COMMANDS)
def test_all_seven_commands_emit_only_closed_offline_non_evidentiary_kinds(
    replay_campaign, tmp_path, capsys, command
):
    before = _snapshot(replay_campaign.workspace_root)
    assert (
        cli.main(
            _argv(command, replay_campaign.workspace_root, tmp_path / "report"),
            program="laconian-benchmark",
        )
        == 0
    )
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert set(payload) == {
        "artifact_count",
        "artifact_kind",
        "artifact_sha256",
        "command",
        "status",
    }
    assert payload == payload | {
        "artifact_count": 1,
        "artifact_kind": f"offline-{command}-validation",
        "command": command,
        "status": "ok",
    }
    assert len(payload["artifact_sha256"]) == 64
    assert output.out.encode() == canonical_json(payload) + b"\n"
    assert output.err == ""
    assert _snapshot(replay_campaign.workspace_root) == before


@pytest.mark.parametrize("command", COMMANDS[:-1])
def test_first_six_commands_write_only_one_offline_validation_report_and_no_evidence_tree(
    replay_campaign, tmp_path, capsys, command
):
    output = tmp_path / "offline"
    assert (
        cli.main(
            _argv(command, replay_campaign.workspace_root, output), program="laconian-benchmark"
        )
        == 0
    )
    envelope = json.loads(capsys.readouterr().out)
    assert tuple(path.relative_to(output).as_posix() for path in output.rglob("*")) == (
        "offline-non-evidentiary.json",
    )
    raw = (output / "offline-non-evidentiary.json").read_bytes()
    report = json.loads(raw)
    assert raw == canonical_json(report) + b"\n"
    assert set(report) == {
        "schema_version",
        "command",
        "artifact_kind",
        "generation_context_expectation_sha256",
        "ordered_input_sha256s",
        "status",
        "offline_report_sha256",
    }
    assert report["schema_version"] == "benchmark-offline-validation-report-v1"
    assert report["status"] == "structurally-valid-not-authorized"
    assert report["command"] == command
    assert report["artifact_kind"] == "offline-" + command + "-validation"
    assert report["ordered_input_sha256s"] == sorted(report["ordered_input_sha256s"])
    digest = report.pop("offline_report_sha256")
    assert digest == stable_digest("laconian-benchmark-offline-validation-report-v1", report)
    assert digest == envelope["artifact_sha256"]


def test_verify_is_read_only_and_emits_only_an_offline_verification_envelope(
    replay_campaign, capsys
):
    root = replay_campaign.workspace_root
    before = _snapshot(root)
    assert cli.main(_argv("verify", root), program="laconian-benchmark") == 0
    first = capsys.readouterr()
    assert _snapshot(root) == before
    assert cli.main(_argv("verify", root), program="laconian-benchmark") == 0
    assert capsys.readouterr() == first
    assert _snapshot(root) == before
    archive_bytes = (root / "protocol-review-archive.json").read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    # Independently account for each explicit input byte source, including the
    # installed scorer code identity checked against the raw context.
    from laconian_eval.benchmark.hard_score import HardScoreRequestSetV1

    input_files = {
        path
        for directory in ("GENERATION", "HARD", "REQUESTS", "JUDGES", "result")
        for path in (root / directory).rglob("*")
        if path.is_file()
    }
    input_files.update(
        {
            root / "GENERATION_COMPLETE/generation-context-expectation.json",
            root / "protocol-review-archive.json",
            Path(inspect.getfile(HardScoreRequestSetV1)),
        }
    )
    hashes = sorted(hashlib.sha256(path.read_bytes()).hexdigest() for path in input_files)
    expectation = replay_campaign.provider_fixture.expectation.expectation
    expected = {
        "schema_version": "benchmark-offline-validation-report-v1",
        "command": "verify",
        "artifact_kind": "offline-verify-validation",
        "generation_context_expectation_sha256": expectation.generation_context_expectation_sha256,
        "ordered_input_sha256s": hashes,
        "status": "structurally-valid-not-authorized",
    }
    assert digest in hashes
    assert json.loads(first.out)["artifact_sha256"] == stable_digest(
        "laconian-benchmark-offline-validation-report-v1", expected
    )
    argv = _argv("verify", root)
    del argv[-2:]
    assert cli.main(argv, program="laconian-benchmark") == 2
    _closed_error(capsys, "usage", "verify")
    # The private report schema is inspectable DATA, without being package-exported.
    from laconian_eval.replay import benchmark
    from laconian_eval.replay.benchmark import OfflineValidationReportV1

    assert "ordered_input_sha256s" in OfflineValidationReportV1.model_fields
    assert "protocol_review_archive" in inspect.getsource(benchmark)
    assert digest != replay_campaign.protocol.archive.protocol_review_object_archive_sha256


def test_offline_validation_reports_are_rejected_by_every_live_complete_root_loader(
    replay_campaign, tmp_path, capsys
):
    from laconian_eval.benchmark.audit_sampling import load_verified_audit_sample_root
    from laconian_eval.benchmark.context import (
        load_layer_root_index,
        load_verified_generation_context_index,
    )
    from laconian_eval.benchmark.judge import load_verified_judge_attempt_root
    from laconian_eval.benchmark.provider_evidence import (
        load_verified_audit_population,
        load_verified_benchmark_provider_evidence,
    )
    from laconian_eval.benchmark.reporting import (
        load_verified_analysis_evidence,
        load_verified_audit_evidence,
    )

    output = tmp_path / "report"
    assert (
        cli.main(
            _argv("hard-score", replay_campaign.workspace_root, output),
            program="laconian-benchmark",
        )
        == 0
    )
    capsys.readouterr()
    before = _snapshot(output)
    fixture = replay_campaign.provider_fixture
    for kind in ("generation", "hard-score", "judge-request", "judge"):
        with pytest.raises((ValueError, OSError)):
            load_layer_root_index(output, expected_kind=kind)
    with pytest.raises((ValueError, OSError)):
        load_verified_generation_context_index(
            generation_index_path=output / "generation-context.json",
            generation_root=output,
            expectation=fixture.expectation,
        )
    with pytest.raises((ValueError, OSError)):
        load_verified_judge_attempt_root(
            output,
            expected_request_root_index_sha256=fixture.judge_request_root_index.layer_root_index_sha256,
            request_attachments=fixture.judge_request_attachments,
        )
    with pytest.raises((ValueError, OSError)):
        load_verified_benchmark_provider_evidence(
            provider_index_path=output / "provider-evidence-index.json",
            generation_root=output,
            hard_score_root=output,
            judge_request_root=output,
            judge_attempt_root=output,
            judge_root=output,
            generation_expectation=fixture.expectation,
            identity_registry_bundle=fixture.identity_registry_bundle,
        )
    for loader in (
        load_verified_audit_population,
        load_verified_audit_sample_root,
        load_verified_audit_evidence,
        load_verified_analysis_evidence,
    ):
        with pytest.raises((ValueError, OSError)):
            loader(output, provider_evidence=replay_campaign.provider)
    assert _snapshot(output) == before


def test_cli_source_has_no_live_hook_campaign_import_verified_loader_builder_or_evidence_writer_call(  # noqa: E501
    capsys,
):
    import importlib
    import textwrap
    from dataclasses import is_dataclass
    from types import ModuleType

    assert cli.main(["--help"], program="laconian-benchmark") == 0
    capsys.readouterr()
    replay = Path(cli.__file__).parent / "replay"
    forbidden = (
        "load_verified_",
        "build_hard_score_",
        "build_judge_",
        "build_audit_",
        "build_bootstrap_",
        "select_audit_",
        "analyze_campaign",
        "write_layer_root",
        "write_generation_",
        "write_hard_score_",
        "write_judge_",
        "write_provider_",
        "write_audit_",
        "write_analysis_",
        "EvidenceInventoryV1",
        "verify_audit_sample",
        "verify_sensitivity_certificate",
        "verify_protocol_review_dag",
        "verify_hard_score_request_set",
        "verify_judge_request_attachment",
        "verify_judge_attachment",
        "compute_model_audit_metrics",
        "verify_audit_chain",
        "_derive_audit",
        "_mint_",
    )
    for path in replay.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert ".campaign" not in (node.module or "")
            if isinstance(node, (ast.Name, ast.Attribute)):
                name = node.id if isinstance(node, ast.Name) else node.attr
                assert not any(name.startswith(prefix) for prefix in forbidden)
    pending = []
    for path in replay.glob("*.py"):
        module = importlib.import_module(
            "laconian_eval.replay" + ("." + path.stem if path.stem != "__init__" else "")
        )
        for owner in vars(module).values():
            if inspect.isfunction(owner) and owner.__module__.startswith("laconian_eval.replay"):
                pending.append(owner)
    reached = set()
    while pending:
        function = pending.pop()
        if function in reached:
            continue
        reached.add(function)
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        scope = dict(function.__globals__)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert ".campaign" not in node.module
                module = importlib.import_module(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        scope[alias.asname or alias.name] = getattr(module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert ".campaign" not in alias.name
                    scope[alias.asname or alias.name.split(".")[0]] = importlib.import_module(
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = node.func
            owner = scope.get(call.id) if isinstance(call, ast.Name) else None
            if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name):
                parent = scope.get(call.value.id)
                if isinstance(parent, ModuleType):
                    owner = getattr(parent, call.attr, None)
            name = getattr(owner, "__name__", "")
            assert not any(name.startswith(prefix) for prefix in forbidden), (function, name)
            assert not (is_dataclass(owner) and name.startswith("Verified")), (function, name)
            if inspect.isfunction(owner) and owner.__module__.startswith("laconian_eval."):
                pending.append(owner)


def test_cli_cannot_construct_or_import_verified_generation_context_expectation(capsys):
    import importlib
    from dataclasses import is_dataclass

    assert cli.main(["--help"], program="laconian-benchmark") == 0
    capsys.readouterr()
    for path in (Path(cli.__file__).parent / "replay").glob("*.py"):
        assert "VerifiedGenerationContextExpectationV1" not in path.read_text()
        module = (
            importlib.import_module("laconian_eval.replay." + path.stem)
            if path.stem != "__init__"
            else importlib.import_module("laconian_eval.replay")
        )
        for name, owner in vars(module).items():
            assert not (
                is_dataclass(owner) and getattr(owner, "__name__", "").startswith("Verified")
            ), (path, name)
            assert not getattr(owner, "__name__", "").startswith("load_verified_"), (path, name)


def _rehashed_file(path, updates, domain, field):
    payload = json.loads(path.read_bytes())
    payload.update(updates)
    payload.pop(field)
    payload[field] = stable_digest(domain, payload)
    path.write_bytes(canonical_json(payload) + b"\n")


def _rehash(payload, domain, field):
    payload.pop(field, None)
    payload[field] = stable_digest(domain, payload)
    return payload


def _write_payload(path, payload):
    path.write_bytes(canonical_json(payload) + b"\n")


def _rehashed_generation_member(root, *, field):
    """Change a raw identity while keeping every actual generation byte parent sealed."""
    capsule = root / "GENERATION/generation/000/capsule"
    member_name = "case-index.jsonl" if field == "case-index-scenario" else "plan.jsonl"
    member = capsule / member_name
    rows = [json.loads(line) for line in member.read_bytes().splitlines()]
    if field == "case-index-scenario":
        selected = json.loads((capsule / "plan.jsonl").read_bytes().splitlines()[0])["case_uid"]
        next(row for row in rows if row["case_uid"] == selected)["scenario_uid"] = "f" * 64
    else:
        key = field.removeprefix("plan-")
        if key == "case_uid":
            value = next(row[key] for row in rows if row[key] != rows[0][key])
        elif key in {"ordinal", "repetition"}:
            value = rows[0][key] + 1
        elif key == "locale":
            value = "ru" if rows[0][key] == "en" else "en"
        elif key == "arm":
            value = "concise" if rows[0][key] == "if" else "if"
        elif key == "case_id":
            value = "canary-model-prompt-label"
        else:
            value = "f" * 64
        rows[0][key] = value
    member.write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows))
    member_digest = hashlib.sha256(member.read_bytes()).hexdigest()
    digest_field = "case_index_sha256" if member_name == "case-index.jsonl" else "plan_sha256"
    metadata_path = capsule / "capsule.json"
    metadata = json.loads(metadata_path.read_bytes())
    metadata[digest_field] = member_digest
    metadata_path.write_bytes(canonical_json(metadata))
    seal_path = capsule / "seal.json"
    seal = json.loads(seal_path.read_bytes())
    for entry in seal["files"]:
        if entry["path"] in {member_name, "capsule.json"}:
            raw = (capsule / entry["path"]).read_bytes()
            entry.update(byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    seal_path.write_bytes(canonical_json(seal))
    capsule_digest = hashlib.sha256(seal_path.read_bytes()).hexdigest()
    sidecar_path = capsule.parent / "scored.json"
    sidecar = json.loads(sidecar_path.read_bytes())
    sidecar.update({digest_field: member_digest, "capsule_sha256": capsule_digest})
    sidecar_path.write_bytes(
        canonical_json(_rehash(sidecar, "laconian-scored-capsule-sidecar-v2", "sidecar_sha256"))
    )
    index_path = root / "GENERATION/generation/index.json"
    index = json.loads(index_path.read_bytes())
    index["members"][0].update(
        generation_capsule_sha256=capsule_digest,
        scored_sidecar_sha256=hashlib.sha256(sidecar_path.read_bytes()).hexdigest(),
    )
    _write_payload(
        index_path,
        _rehash(index, "laconian-benchmark-layer-root-index-v1", "layer_root_index_sha256"),
    )
    context_path = root / "GENERATION/generation-context.json"
    context = json.loads(context_path.read_bytes())
    context["ordered_generation_capsule_sha256s"][0] = capsule_digest
    context["generation_root_index_sha256"] = index["layer_root_index_sha256"]
    _write_payload(
        context_path,
        _rehash(
            context,
            "laconian-benchmark-generation-context-index-v1",
            "generation_context_index_sha256",
        ),
    )
    _rehashed_file(
        root / "GENERATION_COMPLETE/generation-context-expectation.json",
        {
            "generation_layer_root": index["layer_root_index_sha256"],
            "expected_context_index_sha256": context["generation_context_index_sha256"],
        },
        "laconian-benchmark-generation-context-expectation-v1",
        "generation_context_expectation_sha256",
    )


def _failure_on_copy(campaign, tmp_path, capsys, command, change):
    root = tmp_path / "inputs"
    shutil.copytree(campaign.workspace_root, root)
    change(root)
    before = _snapshot(root)
    output = tmp_path / "output"
    assert cli.main(_argv(command, root, output), program="laconian-benchmark") == 3
    _closed_error(capsys, "verification-failed", command)
    assert _snapshot(root) == before
    assert not output.exists()


@pytest.mark.parametrize(
    "field",
    (
        "campaign_id",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "workflow_root",
        "capsule-member",
        "sidecar-member",
        "index-reference",
        "plan-ordinal",
        "plan-case_uid",
        "plan-case_definition_sha256",
        "plan-locale",
        "plan-arm",
        "plan-repetition",
        "plan-case_id",
        "plan-prompt_sha256",
        "plan-instruction_sha256",
        "plan-request_config_sha256",
        "case-index-scenario",
    ),
)
def test_offline_hard_score_detects_context_code_protocol_member_or_workflow_root_substitution(
    replay_campaign, tmp_path, capsys, field
):
    def change(root):
        if field.startswith("plan-") or field == "case-index-scenario":
            _rehashed_generation_member(root, field=field)
            return
        if field == "capsule-member":
            path = root / "GENERATION/generation/000/capsule/raw.jsonl"
            path.write_bytes(path.read_bytes() + b"canary-model-prompt-label\n")
            return
        if field == "sidecar-member":
            path = root / "GENERATION/generation/000/scored.json"
            path.write_bytes(path.read_bytes() + b"\n")
            return
        if field == "index-reference":
            path = root / "GENERATION/generation/index.json"
            index = json.loads(path.read_bytes())
            index["members"][0]["capsule_relative_path"] = "../canary-model-prompt-label"
            _write_payload(
                path,
                _rehash(index, "laconian-benchmark-layer-root-index-v1", "layer_root_index_sha256"),
            )
            return
        _rehashed_file(
            root / "GENERATION/generation-context.json",
            {field: "f" * 64},
            "laconian-benchmark-generation-context-index-v1",
            "generation_context_index_sha256",
        )

    _failure_on_copy(replay_campaign, tmp_path, capsys, "hard-score", change)


@pytest.mark.parametrize("ordinal", (*range(36), "requested-tier", "wire-field", "missing-tier"))
def test_offline_prepare_judge_checks_default_tier_context_and_all_36_hard_score_parents(
    replay_campaign, tmp_path, capsys, ordinal
):
    def change(root):
        if isinstance(ordinal, str):
            path = root / "GENERATION/generation-context.json"
            payload = json.loads(path.read_bytes())
            if ordinal == "requested-tier":
                payload["judge_requested_service_tier"] = "priority"
            elif ordinal == "wire-field":
                payload["judge_service_tier_wire_field"] = "serviceTier"
            else:
                del payload["judge_requested_service_tier"]
            _write_payload(
                path,
                _rehash(
                    payload,
                    "laconian-benchmark-generation-context-index-v1",
                    "generation_context_index_sha256",
                ),
            )
            return
        path = root / f"HARD/hard-score/{ordinal:03d}.json"
        _rehashed_file(
            path,
            {"generation_capsule_sha256": "f" * 64},
            "laconian-hard-score-request-set-v1",
            "hard_score_request_set_sha256",
        )
        index_path = root / "HARD/hard-score/index.json"
        index = json.loads(index_path.read_bytes())
        index["members"][ordinal]["attachment_sha256"] = json.loads(path.read_bytes())[
            "hard_score_request_set_sha256"
        ]
        _write_payload(
            index_path,
            _rehash(index, "laconian-benchmark-layer-root-index-v1", "layer_root_index_sha256"),
        )

    _failure_on_copy(replay_campaign, tmp_path, capsys, "prepare-judge", change)


@pytest.mark.parametrize(
    "ordinal",
    (
        *range(36),
        "retry-parent",
        "retry-authorization",
        "blind-parent",
        "request-parent",
        "terminal",
        "usage",
        "tier",
        "tier-status",
        "cache-status",
        "empty",
    ),
)
def test_offline_seal_judge_checks_36_attempt_boundaries_retry_lineage_and_tier_statuses(
    replay_campaign, tmp_path, capsys, ordinal
):
    def change(root):
        if isinstance(ordinal, int):
            (root / f"ATTEMPTS/judge-attempts/{ordinal:03d}.json").unlink()
            return
        index_path = root / "ATTEMPTS/judge-attempts/index.json"
        index = json.loads(index_path.read_bytes())
        boundary_ordinal = (
            next((row["ordinal"] for row in index["members"] if row["request_count"] == 0), None)
            if ordinal == "empty"
            else 0
        )
        assert boundary_ordinal is not None, "genuine fixture must retain an EMPTY boundary"
        path = root / f"ATTEMPTS/judge-attempts/{boundary_ordinal:03d}.json"
        boundary = json.loads(path.read_bytes())
        if ordinal == "empty":
            assert boundary["attempts"] == boundary["ordered_judge_request_ids"] == []
            boundary["ordered_judge_request_ids"] = ["f" * 64]
        else:
            row = (
                next(item for item in boundary["attempts"] if item["attempt_number"] == 2)
                if ordinal.startswith("retry-")
                else boundary["attempts"][-1]
            )
            field, value = {
                "retry-parent": ("retry_of_judge_attempt_sha256", "f" * 64),
                "retry-authorization": ("retry_authorization_sha256", "f" * 64),
                "blind-parent": ("blind_request_sha256", "f" * 64),
                "request-parent": ("judge_request_attachment_sha256", "f" * 64),
                "terminal": ("terminal", False),
                "usage": ("usage", row["usage"] | {"total_tokens": 999}),
                "tier": ("returned_service_tier", "priority"),
                "tier-status": ("service_tier_status", "canary-model-prompt-label"),
                "cache-status": ("applied_cache_control_status", "canary-model-prompt-label"),
            }[ordinal]
            row[field] = value
            _rehash(row, "laconian-judge-attempt-evidence-v1", "judge_attempt_evidence_sha256")
        _rehash(boundary, "laconian-judge-attempt-boundary-v1", "judge_attempt_boundary_sha256")
        _write_payload(path, boundary)
        index["members"][boundary_ordinal]["judge_attempt_boundary_sha256"] = boundary[
            "judge_attempt_boundary_sha256"
        ]
        _write_payload(
            index_path,
            _rehash(
                index, "laconian-judge-attempt-root-index-v1", "judge_attempt_root_index_sha256"
            ),
        )

    _failure_on_copy(
        replay_campaign,
        tmp_path,
        capsys,
        "seal-judge",
        change,
    )


@pytest.mark.parametrize(
    "field",
    (
        "ordered_generation_capsule_sha256s",
        "ordered_hard_score_request_set_sha256s",
        "ordered_judge_request_attachment_sha256s",
        "ordered_judge_attachment_sha256s",
        "ordered_judge_attempt_boundary_sha256s",
        "judge_attempt_root_index_sha256",
    ),
)
def test_offline_sample_audit_checks_provider_projection_and_all_parent_vectors_without_sampling(
    replay_campaign, tmp_path, capsys, field
):
    def change(root):
        path = root / "JUDGES/provider-evidence-index.json"
        value = json.loads(path.read_bytes())[field]
        changed = ["f" * 64, *value[1:]] if isinstance(value, list) else "f" * 64
        _rehashed_file(
            path,
            {field: changed},
            "laconian-benchmark-provider-evidence-index-v1",
            "provider_evidence_index_sha256",
        )

    if field.startswith("ordered_judge_attempt") or field == "judge_attempt_root_index_sha256":
        root = tmp_path / "inputs"
        shutil.copytree(replay_campaign.workspace_root, root)
        change(root)
        before = _snapshot(root)
        output = tmp_path / "offline"
        # No ATTEMPTS input exists for this command. A coherent rehash of an
        # otherwise unavailable attempt boundary is retained as non-authorizing
        # DATA; the independent audit copies reject it in commands 5-7 below.
        assert cli.main(_argv("sample-audit", root, output), program="laconian-benchmark") == 0
        capsys.readouterr()
        report = json.loads((output / "offline-non-evidentiary.json").read_bytes())
        assert (
            hashlib.sha256((root / "JUDGES/provider-evidence-index.json").read_bytes()).hexdigest()
            in report["ordered_input_sha256s"]
        )
        assert _snapshot(root) == before
        for command in ("seal-audit", "analyze", "verify"):
            assert (
                cli.main(_argv(command, root, tmp_path / command), program="laconian-benchmark")
                == 3
            )
            _closed_error(capsys, "verification-failed", command)
            assert _snapshot(root) == before
    else:
        _failure_on_copy(replay_campaign, tmp_path, capsys, "sample-audit", change)


def test_offline_seal_audit_checks_population_archive_sources_core_and_signoffs(
    replay_campaign, tmp_path, capsys
):
    paths = (
        "audit/population-attachment.json",
        "audit/population.jsonl",
        "audit/sample-manifest.json",
        "audit/blind-packet.json",
        "audit/git-object-archive.json",
        "audit/pull-request-sources/commitment/audit-a.json",
        "audit/pull-request-sources/commitment/audit-b.json",
        "audit/pull-request-sources/reveal/audit-a.json",
        "audit/pull-request-sources/reveal/audit-b.json",
        "audit/pull-request-sources/adjudication.json",
        "audit/commitments/audit-a.json",
        "audit/commitments/audit-b.json",
        "audit/reveals/audit-a/reveal.json",
        "audit/reveals/audit-b/reveal.json",
        "audit/reveals/audit-a/labels.jsonl",
        "audit/reveals/audit-b/labels.jsonl",
        "audit/reviewer-chains/audit-a.json",
        "audit/reviewer-chains/audit-b.json",
        "audit/adjudication-core.json",
        "audit/signoffs/audit-a.json",
        "audit/signoffs/audit-b.json",
        "audit/github-review-sources/701.json",
        "audit/github-review-sources/702.json",
        "audit/github-review-records/701.json",
        "audit/github-review-records/702.json",
        "audit/adjudication.json",
    )
    actual = {
        path.relative_to(replay_campaign.workspace_root / "REVIEWS").as_posix()
        for path in (replay_campaign.workspace_root / "REVIEWS").rglob("*")
        if path.is_file()
    }
    assert actual == set(paths) and len(paths) == 26
    before = _snapshot(replay_campaign.workspace_root)
    assert (
        cli.main(
            _argv(
                "seal-audit",
                replay_campaign.workspace_root,
                tmp_path / "wrong-root",
                **{"review-root": replay_campaign.workspace_root / "REVIEWS/audit"},
            ),
            program="laconian-benchmark",
        )
        == 3
    )
    _closed_error(capsys, "verification-failed", "seal-audit")
    assert _snapshot(replay_campaign.workspace_root) == before
    assert not (tmp_path / "wrong-root").exists()
    for index, relative in enumerate(paths):
        case = tmp_path / str(index)
        case.mkdir()
        _failure_on_copy(
            replay_campaign,
            case,
            capsys,
            "seal-audit",
            lambda root, relative=relative: (root / "REVIEWS" / relative).unlink(),
        )
    for index, relative in enumerate(("audit/audit-evidence.json", "audit/metrics.json", "extra")):
        case = tmp_path / f"extra-{index}"
        case.mkdir()
        _failure_on_copy(
            replay_campaign,
            case,
            capsys,
            "seal-audit",
            lambda root, relative=relative: (root / "REVIEWS" / relative).write_bytes(
                b"canary-private-label"
            ),
        )
    case = tmp_path / "empty"
    case.mkdir()
    _failure_on_copy(
        replay_campaign,
        case,
        capsys,
        "seal-audit",
        lambda root: (root / "REVIEWS/audit/extra-empty").mkdir(),
    )
    for attack in (
        "population-parent",
        "sample-parent",
        "packet-parent",
        "archive",
        "source-rest",
        "source-graphql",
        "core",
        "signoff",
        "review-record",
        "envelope",
    ):

        def change(root, attack=attack):
            from laconian_eval.benchmark import audit_commit_reveal as ac
            from tests.benchmark.test_audit_commit_reveal import _source_with_signature_raw

            audit = root / "REVIEWS/audit"
            if attack.startswith("source-"):
                path = audit / "pull-request-sources/commitment/audit-a.json"
                source = ac.AuditPullRequestEvidenceSourceV1.model_validate_json(path.read_bytes())
                raw, _ = ac._decode_signature_pairs(source)
                bodies = [json.loads(item) for item in raw]
                if attack == "source-rest":
                    bodies[0]["verification"]["verified"] = False
                else:
                    bodies[1]["data"]["repository"]["object"]["signature"]["signer"][
                        "databaseId"
                    ] += 1
                changed = _source_with_signature_raw(
                    source, tuple(canonical_json(item) for item in bodies)
                )
                _write_payload(path, changed.model_dump(mode="json"))
                chain_path = audit / "reviewer-chains/audit-a.json"
                chain = json.loads(chain_path.read_bytes())
                chain["commitment_pr"]["pull_request_source_sha256"] = (
                    changed.pull_request_source_sha256
                )
                _rehash(
                    chain["commitment_pr"],
                    "laconian-audit-pull-request-proof-v1",
                    "pull_request_proof_sha256",
                )
                _write_payload(
                    chain_path,
                    _rehash(
                        chain,
                        "laconian-audit-reviewer-chain-proof-v1",
                        "reviewer_chain_proof_sha256",
                    ),
                )
                return
            filename, field, value, domain, digest_field = {
                "population-parent": (
                    "population-attachment.json",
                    "judge_attempt_root_index_sha256",
                    "f" * 64,
                    "laconian-audit-population-attachment-v1",
                    "population_attachment_sha256",
                ),
                "sample-parent": (
                    "sample-manifest.json",
                    "population_attachment_sha256",
                    "f" * 64,
                    "laconian-audit-sample-manifest-v1",
                    "sample_manifest_sha256",
                ),
                "packet-parent": (
                    "blind-packet.json",
                    "sample_manifest_sha256",
                    "f" * 64,
                    "laconian-blind-audit-packet-v1",
                    "packet_sha256",
                ),
                "archive": (
                    "git-object-archive.json",
                    "object_closure_root",
                    "f" * 64,
                    "laconian-audit-git-object-archive-v1",
                    "audit_git_object_archive_sha256",
                ),
                "core": (
                    "adjudication-core.json",
                    "judge_labels_were_available",
                    True,
                    "laconian-audit-adjudication-core-v1",
                    "adjudication_core_sha256",
                ),
                "signoff": (
                    "signoffs/audit-a.json",
                    "reviewed_head_sha",
                    "f" * 40,
                    "laconian-audit-adjudication-github-review-v1",
                    "signoff_proof_sha256",
                ),
                "review-record": (
                    "github-review-records/701.json",
                    "actor_account_id",
                    99999,
                    "laconian-audit-github-review-record-v1",
                    "exact_api_record_sha256",
                ),
                "envelope": (
                    "adjudication.json",
                    "schema_version",
                    "canary-model-prompt-label",
                    "laconian-audit-adjudication-v1",
                    "adjudication_sha256",
                ),
            }[attack]
            _rehashed_file(audit / filename, {field: value}, domain, digest_field)

        case = tmp_path / ("join-" + attack)
        case.mkdir()
        _failure_on_copy(replay_campaign, case, capsys, "seal-audit", change)


def test_offline_analyze_checks_audit_and_statistical_protocol_inputs_without_running_analysis(
    replay_campaign, tmp_path, capsys
):
    before = _snapshot(replay_campaign.workspace_root)
    assert (
        cli.main(
            _argv(
                "analyze",
                replay_campaign.workspace_root,
                tmp_path / "wrong-root",
                **{"audit-root": replay_campaign.workspace_root / "result"},
            ),
            program="laconian-benchmark",
        )
        == 3
    )
    _closed_error(capsys, "verification-failed", "analyze")
    assert _snapshot(replay_campaign.workspace_root) == before
    assert not (tmp_path / "wrong-root").exists()
    _failure_on_copy(
        replay_campaign,
        tmp_path,
        capsys,
        "analyze",
        lambda root: (root / "audit-evidence/audit/metrics.json").unlink(),
    )
    for attack in (
        "audit-protocol",
        "statistical-protocol",
        "weights",
        "wilson-lower",
        "wilson-upper",
        "two-sided",
        "z",
        "effective-n",
        "numerator",
        "unavailability",
    ):

        def change(root, attack=attack):
            path = root / "audit-evidence/audit/metrics.json"
            metrics = json.loads(path.read_bytes())
            metric = metrics[0]
            if attack.endswith("protocol"):
                metric["protocol_bindings"][attack.replace("-", "_") + "_sha256"] = "f" * 64
            elif attack == "weights":
                metric["weights_by_record"][next(iter(metric["weights_by_record"]))] = {
                    "numerator": 123,
                    "denominator": 1,
                }
            else:
                field, value = {
                    "wilson-lower": ("lower", "0.01"),
                    "wilson-upper": ("upper", "0.99"),
                    "two-sided": ("confidence_level", "one-sided-0.95"),
                    "z": ("z", "1.6448536269514722"),
                    "effective-n": ("effective_n", "42"),
                    "numerator": ("numerator", {"numerator": 1, "denominator": 1}),
                    "unavailability": ("unavailable_reasons", ["unresolved_sampled_consensus"]),
                }[attack]
                metric["agreement"][field] = value
            _rehash(metric, "laconian-model-audit-metric-v1", "model_audit_metric_sha256")
            _write_payload(path, metrics)
            attachment_path = root / "audit-evidence/audit/audit-evidence.json"
            attachment = json.loads(attachment_path.read_bytes())
            attachment["model_audit_metric_sha256s"][0] = metric["model_audit_metric_sha256"]
            _write_payload(
                attachment_path,
                _rehash(attachment, "laconian-verified-audit-evidence-v1", "audit_evidence_sha256"),
            )

        case = tmp_path / attack
        case.mkdir()
        _failure_on_copy(replay_campaign, case, capsys, "analyze", change)

    # The analyze command has no analysis-result input. Supplied U/K, exact
    # assignment counts/certificate inputs and descriptive cache-write fields
    # therefore enter the same offline statistical path through verify/RESULT.
    for attack in (
        "upper-u",
        "count-k",
        "candidate-m",
        "known-d",
        "assignment-count",
        "certificate-input",
        "cache-write",
    ):

        def change(root, attack=attack):
            path = root / "result/analysis/analysis.json"
            analysis = json.loads(path.read_bytes())
            model = analysis["models"][1 if attack == "upper-u" else 0]
            if attack == "cache-write":
                model["usage_by_arm"]["if"]["cache_write_tokens"].update(
                    minimum="1", maximum="1", median="1"
                )
            elif attack == "assignment-count":
                model["sensitivity"]["assignment_count"] = 2
            elif attack == "certificate-input":
                model["sensitivity"]["model_audit_metric_sha256"] = "f" * 64
            else:
                field, value = {
                    "upper-u": ("upper_false_fail", "0.5"),
                    "count-k": ("k_max_reclassified", 1),
                    "candidate-m": ("m_all_judge_fail", 1),
                    "known-d": ("d_known_false_fail", 1),
                }[attack]
                model["false_fail_limits"][1 if attack == "upper-u" else 0][field] = value
            _write_payload(
                path, _rehash(analysis, "laconian-campaign-analysis-v1", "campaign_analysis_sha256")
            )
            if attack in {"upper-u", "cache-write"}:
                from laconian_eval.benchmark.reporting import CampaignAnalysisV1

                # These remain independently valid raw schemas: only comparison
                # with the supplied audit/provider inputs can reject them.
                CampaignAnalysisV1.model_validate_json(path.read_bytes())
            checksum_path = root / "result/analysis/checksums.json"
            checksums = json.loads(checksum_path.read_bytes())
            entry = next(
                item
                for item in checksums["entries"]
                if item["relative_path"] == "analysis/analysis.json"
            )
            raw = path.read_bytes()
            entry.update(byte_length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            _write_payload(
                checksum_path,
                _rehash(checksums, "laconian-analysis-checksums-v1", "checksums_sha256"),
            )
            attachment_path = root / "result/analysis/analysis-evidence.json"
            attachment = json.loads(attachment_path.read_bytes())
            attachment.update(
                campaign_analysis_sha256=analysis["campaign_analysis_sha256"],
                checksums_sha256=checksums["checksums_sha256"],
            )
            _write_payload(
                attachment_path,
                _rehash(
                    attachment, "laconian-verified-analysis-evidence-v1", "analysis_evidence_sha256"
                ),
            )

        case = tmp_path / attack
        case.mkdir()
        _failure_on_copy(replay_campaign, case, capsys, "verify", change)


@pytest.mark.parametrize(
    "change",
    (
        "missing",
        "lf",
        "audit-archive",
        "raw-object",
        "directory",
        "api-blob",
        "second-campaign",
        "protocol_review_object_archive_sha256",
        "object_closure_root",
        "ordered_generation_capsule_sha256s",
        "ordered_hard_score_request_set_sha256s",
        "ordered_judge_request_attachment_sha256s",
        "ordered_judge_attachment_sha256s",
        "ordered_judge_attempt_boundary_sha256s",
        "judge_attempt_root_index_sha256",
    ),
)
def test_offline_verify_checks_all_four_layer_vectors_and_attempt_root(
    replay_campaign, tmp_path, capsys, change
):
    import base64

    from laconian_eval.benchmark.attachments import canonical_json_v1
    from laconian_eval.benchmark.context import GenerationContextIndexV1
    from laconian_eval.benchmark.protocol_review import ProtocolReviewObjectArchiveV1
    from tests.benchmark.test_replay_protocol import _alternate_final_graph, _replace_response

    def mutate(root):
        path = root / "protocol-review-archive.json"
        raw = path.read_bytes()
        archive = ProtocolReviewObjectArchiveV1.model_validate_json(raw)
        assert canonical_json_v1(archive.model_dump(mode="json")) == raw
        assert not raw.endswith(b"\n")
        context_path = root / "GENERATION/generation-context.json"
        context = GenerationContextIndexV1.model_validate_json(context_path.read_bytes())
        assert context.protocol_review_object_archive_sha256 == (
            archive.protocol_review_object_archive_sha256
        )
        assert context.object_closure_root == archive.object_closure_root
        if change == "missing":
            path.unlink()
        elif change == "lf":
            path.write_bytes(path.read_bytes() + b"\n")
        elif change == "audit-archive":
            path.write_bytes((root / "result/audit/git-object-archive.json").read_bytes())
        elif change == "raw-object":
            payload = json.loads(path.read_bytes())
            payload["objects"][0]["raw_content_base64"] = "Y2FuYXJ5LXByaXZhdGU="
            path.write_bytes(canonical_json(payload))
        elif change == "directory":
            path.unlink()
            path.mkdir()
        elif change == "api-blob":
            payload = json.loads(raw)
            binding = next(
                item
                for item in payload["api_receipts"]
                if item["receipt_kind"] == "github_signature"
            )
            blob = next(
                item
                for item in payload["api_blobs"]
                if item["path"] == binding["raw_blob_paths"][1]
            )
            response = json.loads(base64.b64decode(blob["raw_bytes_base64"]))
            response["data"]["repository"]["object"]["signature"]["signer"]["login"] = (
                "canary-other-campaign-model"
            )
            # Rehash raw blob, receipt, relocated blob paths and archive envelope:
            # the rejection is not merely a stale archive self digest.
            changed = _replace_response(payload, binding, 1, canonical_json_v1(response))
            ProtocolReviewObjectArchiveV1.model_validate_json(changed)
            path.write_bytes(changed)
        elif change == "second-campaign":
            # This coherent alternate graph has its own positive raw-helper case.
            # Only the explicit archive changes here; the retained first campaign
            # must not accept another campaign's fully rehashed T1/receipt graph.
            changed, bindings = _alternate_final_graph(
                replay_campaign.protocol, corrupt_local_receipt=False
            )
            other = ProtocolReviewObjectArchiveV1.model_validate_json(changed)
            assert other.protocol_review_object_archive_sha256 != (
                context.protocol_review_object_archive_sha256
            )
            assert other.object_closure_root != context.object_closure_root
            assert other.object_closure_root == bindings["object_closure_root"]
            path.write_bytes(changed)
        elif change in {"protocol_review_object_archive_sha256", "object_closure_root"}:
            _rehashed_file(
                context_path,
                {change: "f" * 64},
                "laconian-benchmark-generation-context-index-v1",
                "generation_context_index_sha256",
            )
            changed_context = GenerationContextIndexV1.model_validate_json(
                context_path.read_bytes()
            )
            _rehashed_file(
                root / "GENERATION_COMPLETE/generation-context-expectation.json",
                {"expected_context_index_sha256": changed_context.generation_context_index_sha256},
                "laconian-benchmark-generation-context-expectation-v1",
                "generation_context_expectation_sha256",
            )
        else:
            provider_path = root / "JUDGES/provider-evidence-index.json"
            original = json.loads(provider_path.read_bytes())[change]
            replacement = ["f" * 64, *original[1:]] if isinstance(original, list) else "f" * 64
            _rehashed_file(
                provider_path,
                {change: replacement},
                "laconian-benchmark-provider-evidence-index-v1",
                "provider_evidence_index_sha256",
            )

    _failure_on_copy(replay_campaign, tmp_path, capsys, "verify", mutate)


@pytest.mark.parametrize("command", COMMANDS)
def test_commands_are_input_read_only_output_no_replace_and_failure_atomic(
    replay_campaign, tmp_path, capsys, command, monkeypatch
):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep").write_bytes(b"unchanged")
    before = _snapshot(replay_campaign.workspace_root)
    if command != "verify":
        assert (
            cli.main(
                _argv(command, replay_campaign.workspace_root, output), program="laconian-benchmark"
            )
            == 4
        )
        _closed_error(capsys, "output-exists", command)
    else:
        assert (
            cli.main(
                [*_argv(command, replay_campaign.workspace_root), "--output-root", str(output)],
                program="laconian-benchmark",
            )
            == 2
        )
        _closed_error(capsys, "usage", command)
    assert (output / "keep").read_bytes() == b"unchanged"
    assert _snapshot(replay_campaign.workspace_root) == before
    if command == "hard-score":
        import errno

        # Real namespace races/final-witness changes, with validation left intact.
        from laconian_eval.capsule.posix import PosixOps

        open_parent = tmp_path / "stage-open-parent"
        open_parent.mkdir()
        original_open = os.open

        def fail_stage_open(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith(".offline-") and path.endswith(".tmp"):
                raise OSError(errno.EMFILE, "canary-model-prompt-label")
            return original_open(path, *args, **kwargs)

        with monkeypatch.context() as fault:
            fault.setattr(os, "open", fail_stage_open)
            assert (
                cli.main(
                    _argv(command, replay_campaign.workspace_root, open_parent / "offline"),
                    program="laconian-benchmark",
                )
                == 3
            )
        _closed_error(capsys, "verification-failed", command)
        assert list(open_parent.iterdir()) == []
        assert _snapshot(replay_campaign.workspace_root) == before

        race_parent = tmp_path / "race-parent"
        race_parent.mkdir()
        moved_parent = tmp_path / "moved-parent"
        original_rename = PosixOps.rename_noreplace

        def replace_parent(self, *args):
            original_rename(self, *args)
            race_parent.rename(moved_parent)
            race_parent.mkdir()

        with monkeypatch.context() as fault:
            fault.setattr(PosixOps, "rename_noreplace", replace_parent)
            assert (
                cli.main(
                    _argv(command, replay_campaign.workspace_root, race_parent / "offline"),
                    program="laconian-benchmark",
                )
                == 3
            )
        _closed_error(capsys, "verification-failed", command)
        assert list(race_parent.iterdir()) == list(moved_parent.iterdir()) == []

        competing_parent = tmp_path / "competing-parent"
        competing_parent.mkdir()
        competing_output = competing_parent / "offline"

        def install_competing_output(self, *args):
            competing_output.mkdir()
            (competing_output / "keep").write_bytes(b"external-owner")
            original_rename(self, *args)

        with monkeypatch.context() as fault:
            fault.setattr(PosixOps, "rename_noreplace", install_competing_output)
            assert (
                cli.main(
                    _argv(command, replay_campaign.workspace_root, competing_output),
                    program="laconian-benchmark",
                )
                == 4
            )
        _closed_error(capsys, "output-exists", command)
        assert (competing_output / "keep").read_bytes() == b"external-owner"
        assert list(competing_parent.iterdir()) == [competing_output]
        assert _snapshot(replay_campaign.workspace_root) == before

        authority = tmp_path / "GENERATION_COMPLETE"
        authority.mkdir()
        expectation = authority / "generation-context-expectation.json"
        expectation.write_bytes(
            (
                replay_campaign.workspace_root
                / "GENERATION_COMPLETE/generation-context-expectation.json"
            ).read_bytes()
        )
        late_parent = tmp_path / "late-parent"
        late_parent.mkdir()
        parent_inode = late_parent.stat().st_ino
        original_fsync = os.fsync

        def late_change(descriptor):
            original_fsync(descriptor)
            if os.fstat(descriptor).st_ino == parent_inode:
                expectation.write_bytes(expectation.read_bytes() + b"\n")

        with monkeypatch.context() as fault:
            fault.setattr(os, "fsync", late_change)
            assert (
                cli.main(
                    _argv(
                        command,
                        replay_campaign.workspace_root,
                        late_parent / "offline",
                        **{"generation-expectation": expectation},
                    ),
                    program="laconian-benchmark",
                )
                == 3
            )
        _closed_error(capsys, "verification-failed", command)
        assert list(late_parent.iterdir()) == []
        assert _snapshot(replay_campaign.workspace_root) == before


@pytest.mark.parametrize("command", COMMANDS)
def test_every_error_is_canonical_content_free_json_without_path_model_prompt_or_label_text(
    replay_campaign, tmp_path, capsys, command, monkeypatch
):
    original_inputs = _snapshot(replay_campaign.workspace_root)
    assert (
        cli.main(
            _argv(command, tmp_path / "canary-model-prompt-label"), program="laconian-benchmark"
        )
        == 3
    )
    _closed_error(capsys, "verification-failed", command)
    assert cli.main(["canary-model-prompt-label"], program="laconian-benchmark") == 2
    _closed_error(capsys, "usage", None)
    original = (
        replay_campaign.workspace_root / "GENERATION_COMPLETE/generation-context-expectation.json"
    )
    for kind in ("symlink", "fifo", "directory", "alias", "malformed-canonical", "wrong-campaign"):
        parent = tmp_path / kind / "GENERATION_COMPLETE"
        parent.mkdir(parents=True)
        path = parent / "generation-context-expectation.json"
        if kind == "symlink":
            path.symlink_to(original)
        elif kind == "fifo":
            os.mkfifo(path)
        elif kind == "directory":
            path.mkdir()
        elif kind == "alias":
            path.write_bytes(original.read_bytes())
            os.link(path, parent / "canary-model-prompt-label-alias.json")
        elif kind == "malformed-canonical":
            path.write_bytes(original.read_bytes() + b"\n")
        else:
            path.write_bytes(original.read_bytes())
            _rehashed_file(
                path,
                {"campaign_id": "canary-model-prompt-label"},
                "laconian-benchmark-generation-context-expectation-v1",
                "generation_context_expectation_sha256",
            )
        before = _snapshot(parent)
        assert (
            cli.main(
                _argv(
                    command,
                    replay_campaign.workspace_root,
                    tmp_path / f"out-{kind}",
                    **{"generation-expectation": path},
                ),
                program="laconian-benchmark",
            )
            == 3
        )
        _closed_error(capsys, "verification-failed", command)
        assert _snapshot(parent) == before
        assert _snapshot(replay_campaign.workspace_root) == original_inputs

    def fail_open(*args, **kwargs):
        raise RuntimeError("canary-model-prompt-label-exception")

    with monkeypatch.context() as fault:
        fault.setattr(os, "open", fail_open)
        assert (
            cli.main(
                _argv(command, replay_campaign.workspace_root, tmp_path / "software"),
                program="laconian-benchmark",
            )
            == 70
        )
    _closed_error(capsys, "software-error", command)
    assert _snapshot(replay_campaign.workspace_root) == original_inputs
    if command in {"seal-audit", "verify"}:
        from tests.benchmark.replay_boundary_cases import check_explicit_input_boundaries

        check_explicit_input_boundaries(replay_campaign, tmp_path, capsys, monkeypatch, command)
