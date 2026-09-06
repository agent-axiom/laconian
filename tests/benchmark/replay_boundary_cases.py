"""Real public-CLI checks for the two explicitly supplied Task 15 inputs."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

from laconian_eval import cli
from laconian_eval.benchmark.protocol_review import (
    ProtocolReviewObjectArchiveV1,
    protocol_review_digest,
)
from laconian_eval.capsule.canonical import canonical_json, stable_digest

_CANDIDATE = "CANDIDATE-CANARY-private-response-DO-NOT-PRINT"
_MODEL = "MODEL-CANARY-private-model-DO-NOT-PRINT"
_EXCEPTION = "EXCEPTION-CANARY-private-error-DO-NOT-PRINT"


def _member_snapshot(root: Path) -> dict:
    """Snapshot bytes and identity without opening symlinks or special files."""
    result = {}
    # `root` is the operation's temporary parent, not an input. Creating and
    # rolling back a report stage may change that parent's timestamps.
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None,
            os.readlink(path) if stat.S_ISLNK(metadata.st_mode) else None,
        )
    return result


def _replace_archive_object(path: Path, *, kind: str) -> None:
    """Rehash ordinary source bytes, their Git identity, closure and archive."""
    payload = json.loads(path.read_bytes())
    if kind == "wrong-campaign":
        item = next(row for row in payload["objects"] if row["type"] == "tag")
        previous = base64.b64decode(item["raw_content_base64"])
        raw = previous.replace(b"20260831.1", b"20990101.1")
        assert raw != previous
    else:
        item = next(row for row in payload["objects"] if row["type"] == "blob")
        raw = canonical_json(
            {"candidate_response": _CANDIDATE} if kind == "candidate-canary" else {"model": _MODEL}
        )
    wire = item["type"].encode() + b" " + str(len(raw)).encode() + b"\0" + raw
    item.update(
        oid=hashlib.sha1(wire).hexdigest(),
        size=len(raw),
        git_object_sha256=hashlib.sha256(wire).hexdigest(),
        raw_content_base64=base64.b64encode(raw).decode(),
    )
    payload["objects"].sort(key=lambda row: row["oid"])
    payload["object_closure_root"] = protocol_review_digest(
        "laconian-protocol-review-object-closure-v1",
        [
            {field: row[field] for field in ("oid", "type", "size", "git_object_sha256")}
            for row in payload["objects"]
        ],
    )
    payload.pop("protocol_review_object_archive_sha256")
    payload["protocol_review_object_archive_sha256"] = protocol_review_digest(
        "laconian-protocol-review-object-archive-v1", payload
    )
    raw = canonical_json(payload)
    # This remains strict raw archive DATA. Its changed campaign/source graph
    # must not be accepted merely because all these ordinary hashes are coherent.
    assert ProtocolReviewObjectArchiveV1.model_validate_json(raw)
    path.write_bytes(raw)


def _replace_review_data(root: Path, *, kind: str) -> None:
    if kind == "model-canary":
        path = root / "audit/population.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[0]["generation_model"] = _MODEL
        path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows))
        return
    if kind == "candidate-canary":
        path = root / "audit/blind-packet.json"
        payload = json.loads(path.read_bytes())
        payload["records"][0]["candidate_response"] = _CANDIDATE
        domain, digest_field = "laconian-blind-audit-packet-v1", "packet_sha256"
    else:
        path = root / "audit/population-attachment.json"
        payload = json.loads(path.read_bytes())
        payload["campaign_id"] = "benchmark-second-campaign"
        domain = "laconian-audit-population-attachment-v1"
        digest_field = "population_attachment_sha256"
    payload.pop(digest_field)
    payload[digest_field] = stable_digest(domain, payload)
    path.write_bytes(canonical_json(payload) + b"\n")


def check_explicit_input_boundaries(campaign, tmp_path, capsys, monkeypatch, command):
    """Extend the existing named CLI test without adding another test inventory."""
    from tests.benchmark.test_cli import _argv, _closed_error, _snapshot

    if command not in {"seal-audit", "verify"}:
        return
    original_root = campaign.workspace_root
    original_before = _snapshot(original_root)
    cases = (
        "success",
        "symlink",
        "ancestor-symlink",
        "fifo",
        "directory",
        "hardlink",
        "inode-alias",
        "unstable-identity",
        "malformed-json",
        "noncanonical",
        "wrong-campaign",
        "candidate-canary",
        "model-canary",
        "exception-canary",
    )
    option = "review-root" if command == "seal-audit" else "protocol-review-archive"
    for kind in cases:
        case = tmp_path / f"explicit-{command}-{kind}"
        case.mkdir()
        boundary_parent = case / "inputs"
        boundary_parent.mkdir()
        if command == "seal-audit":
            boundary = boundary_parent / "REVIEWS"
            shutil.copytree(original_root / "REVIEWS", boundary)
            assert len([path for path in boundary.rglob("*") if path.is_file()]) == 26
            member = boundary / "audit/population-attachment.json"
        else:
            # The archive's explicit filename has no fixed-basename requirement.
            boundary = member = boundary_parent / "arbitrary-archive-name.json"
            shutil.copy2(original_root / "protocol-review-archive.json", member)
        overrides = {option: boundary}
        if kind == "symlink":
            retained = case / "retained-member.json"
            member.rename(retained)
            member.symlink_to(retained)
        elif kind == "ancestor-symlink":
            alias = case / "input-alias"
            alias.symlink_to(boundary_parent, target_is_directory=True)
            overrides[option] = alias / boundary.name
        elif kind in {"fifo", "directory"}:
            member.unlink()
            if kind == "fifo":
                os.mkfifo(member)
            else:
                member.mkdir()
        elif kind == "hardlink":
            retained = case / "retained-member.json"
            member.rename(retained)
            member.hardlink_to(retained)
            assert member.stat().st_nlink == 2
        elif kind == "inode-alias":
            if command == "seal-audit":
                duplicate = boundary / "audit/blind-packet.json"
            else:
                # Alias across explicit arguments, not only inside one tree.
                authority = boundary_parent / "GENERATION_COMPLETE"
                authority.mkdir()
                duplicate = authority / "generation-context-expectation.json"
                shutil.copy2(
                    original_root / "GENERATION_COMPLETE/generation-context-expectation.json",
                    duplicate,
                )
                overrides["generation-expectation"] = duplicate
            member.unlink()
            member.hardlink_to(duplicate)
            assert member.stat().st_ino == duplicate.stat().st_ino
        elif kind == "malformed-json":
            member.write_bytes(b'{"candidate_response":"' + _CANDIDATE.encode())
        elif kind == "noncanonical":
            member.write_bytes(member.read_bytes() + b"\n")
        elif kind in {"wrong-campaign", "candidate-canary", "model-canary"}:
            if command == "verify":
                _replace_archive_object(member, kind=kind)
            else:
                _replace_review_data(boundary, kind=kind)

        before = _member_snapshot(case)
        target_identity = (
            (member.stat().st_dev, member.stat().st_ino)
            if kind in {"unstable-identity", "exception-canary"}
            else None
        )
        changed_snapshot = None
        triggered = False
        original_close, original_read = os.close, os.read

        def close_and_replace(
            descriptor,
            target_identity=target_identity,
            original_close=original_close,
            member=member,
            case=case,
        ):
            nonlocal triggered, changed_snapshot
            metadata = os.fstat(descriptor)
            replace = not triggered and (metadata.st_dev, metadata.st_ino) == target_identity
            original_close(descriptor)
            if replace:
                # The real read has finished. Replace the visible inode with
                # identical bytes so only the retained identity check can catch it.
                triggered = True
                raw = member.read_bytes()
                member.rename(case / "retired-member.json")
                member.write_bytes(raw)
                assert member.stat().st_ino != target_identity[1]
                changed_snapshot = _member_snapshot(case)

        def read_with_exception(
            descriptor, size, target_identity=target_identity, original_read=original_read
        ):
            nonlocal triggered
            metadata = os.fstat(descriptor)
            if (metadata.st_dev, metadata.st_ino) == target_identity:
                triggered = True
                raise RuntimeError(_EXCEPTION)
            return original_read(descriptor, size)

        output = case / "offline-output"
        with monkeypatch.context() as fault:
            if kind == "unstable-identity":
                fault.setattr(os, "close", close_and_replace)
            elif kind == "exception-canary":
                fault.setattr(os, "read", read_with_exception)
            result = cli.main(
                _argv(command, original_root, output, **overrides), program="laconian-benchmark"
            )
        if kind == "success":
            assert result == 0
            console = capsys.readouterr()
            envelope = json.loads(console.out)
            assert console.out.encode() == canonical_json(envelope) + b"\n"
            assert console.err == ""
            assert envelope["artifact_kind"] == f"offline-{command}-validation"
            if command == "seal-audit":
                assert {path.relative_to(output).as_posix() for path in output.rglob("*")} == {
                    "offline-non-evidentiary.json"
                }
                # Account only for the explicitly permitted output tree.
                after = _member_snapshot(case)
                assert {
                    name: value
                    for name, value in after.items()
                    if name != "." and not name.startswith("offline-output")
                } == {name: value for name, value in before.items() if name != "."}
            else:
                assert _member_snapshot(case) == before
        else:
            code = "software-error" if kind == "exception-canary" else "verification-failed"
            assert result == (70 if kind == "exception-canary" else 3), kind
            _closed_error(capsys, code, command)
            if kind == "unstable-identity":
                assert triggered and changed_snapshot is not None
                assert _member_snapshot(case) == changed_snapshot
            else:
                assert _member_snapshot(case) == before
            assert not output.exists()
        if command == "verify":
            assert not output.exists()
        if kind == "exception-canary":
            assert triggered
        assert _snapshot(original_root) == original_before
