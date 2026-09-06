"""Real filesystem regressions for the private retained-input boundary."""

from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

import pytest

from laconian_eval.replay._inputs import Inputs, absolute


def _metadata(path: Path) -> tuple[int, int, int, int, int]:
    value = path.stat()
    return value.st_ino, value.st_mode, value.st_nlink, value.st_mtime_ns, value.st_ctime_ns


def test_file_then_tree_preserves_bytes_metadata_and_one_digest_per_member(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    paths = (root / "a.json", root / "nested/b.json")
    for path, raw in zip(paths, (b"first\n", b"second\n"), strict=True):
        path.write_bytes(raw)
    before = {path: (path.read_bytes(), _metadata(path)) for path in paths}
    with Inputs() as inputs:
        assert inputs.file(paths[0]) == b"first\n"
        tree = inputs.tree(root)
        tree.exact({"a.json", "nested/b.json"})
        assert inputs.file(paths[1]) == b"second\n"
        assert inputs.tree(root) is tree
        assert inputs.ordered_hashes() == tuple(
            sorted(hashlib.sha256(raw).hexdigest() for raw, _ in before.values())
        )
    assert {path: (path.read_bytes(), _metadata(path)) for path in paths} == before


@pytest.mark.parametrize("boundary", ("file", "tree"))
@pytest.mark.parametrize("kind", ("symlink", "ancestor-symlink", "hardlink", "fifo", "socket"))
def test_unsafe_input_members_are_rejected_without_following_or_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str, kind: str
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    member = root / "member"
    outside = tmp_path / "outside"
    outside.write_bytes(b"private-content-must-not-change")
    before = (outside.read_bytes(), _metadata(outside))
    listener = None
    if kind == "symlink":
        member.symlink_to(outside)
    elif kind == "ancestor-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        member.write_bytes(b"raw")
        root = alias
        member = alias / "member"
    elif kind == "hardlink":
        member.hardlink_to(outside)
        before = (outside.read_bytes(), _metadata(outside))
    elif kind == "fifo":
        os.mkfifo(member)
    else:
        listener = socket.socket(socket.AF_UNIX)
    try:
        if listener is not None:
            # macOS pytest roots can exceed AF_UNIX's pathname length limit.
            # Bind a short relative name; the input validator still gets an absolute path.
            monkeypatch.chdir(root)
            listener.bind(member.name)
        with pytest.raises((ValueError, OSError)), Inputs() as inputs:
            if boundary == "file":
                inputs.file(member)
            else:
                inputs.tree(root)
    finally:
        if listener is not None:
            listener.close()
    assert (outside.read_bytes(), _metadata(outside)) == before


@pytest.mark.parametrize("reference", ("a/../b", "a\\b"))
def test_raw_path_traversal_is_rejected_before_normalization(reference: str) -> None:
    with pytest.raises(ValueError, match="offline input rejected"):
        absolute(Path(reference))


@pytest.mark.parametrize("mutation", ("bytes", "inode", "parent", "addition", "empty-directory"))
def test_retained_tree_rechecks_bytes_identity_and_exact_membership(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    member = root / "member"
    member.write_bytes(b"original")
    with pytest.raises(ValueError, match="offline input changed"), Inputs() as inputs:
        inputs.tree(root).exact({"member"})
        if mutation == "bytes":
            member.write_bytes(b"modified")
        elif mutation == "inode":
            member.rename(root / "old-member")
            member.write_bytes(b"original")
        elif mutation == "parent":
            root.rename(tmp_path / "retained-but-hidden")
            root.mkdir()
            member.write_bytes(b"original")
        elif mutation == "addition":
            (root / "extra").write_bytes(b"extra")
        else:
            (root / "empty").mkdir()


def test_tree_exact_rejects_unexpected_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    (tmp_path / "member").write_bytes(b"original")
    with Inputs() as inputs:
        tree = inputs.tree(tmp_path)
        with pytest.raises(ValueError, match="offline root membership rejected"):
            tree.exact({"member"})
        tree.exact({"member"}, extra_directories={"empty"})


@pytest.mark.parametrize("order", ("parent-first", "child-first"))
def test_overlapping_root_aliases_are_rejected(tmp_path: Path, order: str) -> None:
    child = tmp_path / "child"
    child.mkdir()
    (child / "member").write_bytes(b"original")
    roots = (tmp_path, child) if order == "parent-first" else (child, tmp_path)
    with Inputs() as inputs:
        inputs.tree(roots[0])
        with pytest.raises(ValueError, match="offline overlapping roots rejected"):
            inputs.tree(roots[1])


def test_output_overlap_rejects_retained_tree_and_ancestors(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    member = root / "member"
    member.write_bytes(b"original")
    with Inputs() as inputs:
        inputs.tree(root)
        for output in (tmp_path, root, member, root / "new-output"):
            with pytest.raises(ValueError, match="offline output overlaps inputs"):
                inputs.reject_output_overlap(output)
        inputs.reject_output_overlap(tmp_path / "separate-output")
