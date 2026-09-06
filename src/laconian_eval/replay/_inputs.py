"""Retained-descriptor, read-only input witnesses for private offline replay."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Self, TypeVar

from pydantic import BaseModel

from laconian_eval.benchmark.context import (
    _FilesystemIdentity,
    _open_retained_directory,
    _stable_regular_file_snapshot,
)
from laconian_eval.benchmark.provider_evidence import _RetainedTreeWitness
from laconian_eval.capsule.canonical import canonical_json

_Model = TypeVar("_Model", bound=BaseModel)


def absolute(path: Path) -> Path:
    if ".." in path.parts or not path.name or "\\" in str(path):
        raise ValueError("offline input rejected")
    return Path(os.path.abspath(path))


def parse_model(raw: bytes, owner: type[_Model], *, final_lf: bool = True) -> _Model:
    body = raw[:-1] if final_lf else raw
    if (final_lf and not raw.endswith(b"\n")) or canonical_json(json.loads(body)) != body:
        raise ValueError("offline canonical input rejected")
    result = owner.model_validate_json(body)
    if canonical_json(result.model_dump(mode="json")) != body:
        raise ValueError("offline canonical model rejected")
    return result


def parse_rows(raw: bytes, owner: type[_Model]) -> tuple[_Model, ...]:
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ValueError("offline JSONL rejected")
    return tuple(parse_model(line, owner, final_lf=False) for line in raw[:-1].split(b"\n"))


@dataclass(frozen=True)
class Tree:
    root: Path
    members: dict[str, bytes]
    directories: frozenset[str]

    def exact(self, files: set[str], *, extra_directories: set[str] | None = None) -> None:
        expected_directories = {
            str(parent)
            for name in files
            for parent in PurePosixPath(name).parents
            if str(parent) != "."
        }
        expected_directories.update(extra_directories or ())
        if set(self.members) != files or self.directories != expected_directories:
            raise ValueError("offline root membership rejected")

    def model(self, name: str, owner: type[_Model]) -> _Model:
        return parse_model(self.members[name], owner)


@dataclass(frozen=True)
class _File:
    path: Path
    parent: int
    name: str
    raw: bytes
    identity: _FilesystemIdentity


class Inputs:
    def __init__(self) -> None:
        self._trees: dict[Path, tuple[_RetainedTreeWitness, Tree]] = {}
        self._files: dict[Path, _File] = {}
        self._parents: list[int] = []
        self._inodes: dict[tuple[int, int], Path] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.recheck()
        finally:
            for witness, _ in reversed(tuple(self._trees.values())):
                witness.close()
            for descriptor in reversed(self._parents):
                os.close(descriptor)

    def _remember(self, path: Path, parent: int, name: str) -> bytes:
        raw, identity = _stable_regular_file_snapshot(parent, name)
        previous = self._files.get(path)
        if previous is not None:
            if previous.raw != raw or previous.identity != identity:
                raise ValueError("offline input changed")
            return raw
        inode = (identity.device, identity.inode)
        if inode in self._inodes:
            raise ValueError("offline input alias rejected")
        self._inodes[inode] = path
        self._files[path] = _File(path, parent, name, raw, identity)
        return raw

    def file(self, path: Path) -> bytes:
        path = absolute(path)
        for root, (witness, _tree) in self._trees.items():
            if path.is_relative_to(root):
                name = path.relative_to(root).as_posix()
                return self._remember(path, witness.descriptor, name)
        parent, _ = _open_retained_directory(path.parent)
        self._parents.append(parent)
        return self._remember(path, parent, path.name)

    def tree(self, root: Path) -> Tree:
        root = absolute(root)
        if root in self._trees:
            return self._trees[root][1]
        if any(root.is_relative_to(other) or other.is_relative_to(root) for other in self._trees):
            raise ValueError("offline overlapping roots rejected")
        witness = _RetainedTreeWitness.open(root)
        members: dict[str, bytes] = {}
        directories: set[str] = set()
        tree = Tree(root, members, frozenset())
        self._trees[root] = (witness, tree)
        for name, identity in witness.tree:
            if stat.S_ISREG(identity.mode):
                members[name] = self._remember(root / name, witness.descriptor, name)
            else:
                directories.add(name)
        tree = Tree(root, members, frozenset(directories))
        self._trees[root] = (witness, tree)
        return tree

    def reject_output_overlap(self, output: Path) -> None:
        target = absolute(output)
        if any(target == file or file.is_relative_to(target) for file in self._files):
            raise ValueError("offline output overlaps inputs")
        if any(
            file.parent.name == "GENERATION_COMPLETE" and target.is_relative_to(file.parent)
            for file in self._files
        ):
            raise ValueError("offline output overlaps expectation package")
        if any(target.is_relative_to(root) or root.is_relative_to(target) for root in self._trees):
            raise ValueError("offline output overlaps inputs")

    def recheck(self) -> None:
        failure: Exception | None = None
        for file in self._files.values():
            try:
                raw, identity = _stable_regular_file_snapshot(file.parent, file.name)
                probe, _ = _open_retained_directory(file.path.parent)
                try:
                    visible_raw, visible_identity = _stable_regular_file_snapshot(
                        probe, file.path.name
                    )
                finally:
                    os.close(probe)
                if (
                    raw != file.raw
                    or identity != file.identity
                    or visible_raw != raw
                    or visible_identity != identity
                ):
                    raise ValueError("offline input changed")
            except Exception as error:
                failure = error
        for witness, _ in self._trees.values():
            try:
                witness.recheck()
            except Exception as error:
                failure = error
        if failure is not None:
            raise ValueError("offline input changed") from None

    def ordered_hashes(self) -> tuple[str, ...]:
        return tuple(sorted(hashlib.sha256(file.raw).hexdigest() for file in self._files.values()))
