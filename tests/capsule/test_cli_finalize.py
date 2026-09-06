from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import laconian_eval.cli as cli
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes
from laconian_eval.capsule.finalize import FinalizationError, finalize_capsule
from laconian_eval.capsule.verify import VerificationMode, verify_capsule
from laconian_eval.cli import main

from .test_execution import _single_plan_capsule

TreeSnapshot = dict[str, tuple[int, int, int, int, int, bytes | None]]


@pytest.fixture
def prepared_capsule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _single_plan_capsule(tmp_path, monkeypatch)


@pytest.fixture
def sealed_capsule(prepared_capsule: Path) -> Path:
    result = finalize_capsule(prepared_capsule, seal_incomplete=True)
    assert result.state == "SEALED_BLOCKED"
    return prepared_capsule


def _snapshot_tree(root: Path) -> TreeSnapshot:
    snapshot: TreeSnapshot = {}
    for path in (root, *sorted(root.rglob("*"))):
        metadata = path.lstat()
        snapshot[path.relative_to(root).as_posix() or "."] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None,
        )
    return snapshot


@pytest.mark.parametrize(
    ("argv", "expected_incomplete"),
    [
        (["finalize", "capsule"], False),
        (["finalize", "capsule", "--seal-incomplete"], True),
    ],
)
def test_finalize_parser_dispatches_exact_supported_forms(
    argv: list[str],
    expected_incomplete: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[Path, bool]] = []

    def fake_finalize(path: Path, *, seal_incomplete: bool) -> int:
        calls.append((path, seal_incomplete))
        return 0

    monkeypatch.setattr(cli, "_finalize", fake_finalize, raising=False)

    assert main(argv, program="laconian") == 0
    assert calls == [(Path("capsule"), expected_incomplete)]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["fin", "capsule"],
        ["finalize"],
        ["finalize", "capsule", "extra"],
        ["finalize", "capsule", "--seal"],
        ["finalize", "capsule", "--seal-incomplete=true"],
    ],
)
def test_finalize_parser_rejects_every_other_shape_before_dispatch(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def forbidden(_path: Path, *, seal_incomplete: bool) -> int:
        del seal_incomplete
        nonlocal calls
        calls += 1
        raise AssertionError("invalid finalize syntax reached dispatch")

    monkeypatch.setattr(cli, "_finalize", forbidden, raising=False)

    assert main(argv, program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "usage:" in captured.err


@pytest.mark.parametrize("seal_incomplete", [False, True])
def test_finalize_success_announces_one_lexical_absolute_target_and_exits_zero(
    seal_incomplete: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation = tmp_path / "invocation"
    invocation.mkdir()
    monkeypatch.chdir(invocation)
    calls: list[tuple[Path, bool, object]] = []

    def fake_finalize_capsule(
        path: Path,
        *,
        seal_incomplete: bool,
        on_target_known: object,
        seams: object,
    ) -> SimpleNamespace:
        calls.append((path, seal_incomplete, seams))
        assert callable(on_target_known)
        on_target_known(path)
        on_target_known(path)
        return SimpleNamespace(
            path=path,
            state="SEALED_BLOCKED" if seal_incomplete else "SEALED_COMPLETE",
            capsule_sha256="1" * 64,
        )

    monkeypatch.setattr(cli, "_finalize_capsule", fake_finalize_capsule)
    argv = ["finalize", "nested/../capsule"]
    if seal_incomplete:
        argv.append("--seal-incomplete")

    assert main(argv, program="laconian") == 0

    captured = capsys.readouterr()
    expected = Path(os.path.abspath("nested/../capsule"))
    assert calls == [(expected, seal_incomplete, None)]
    assert captured.out == f"{expected}\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "code",
    [
        "busy",
        "unsupported_filesystem",
        "incomplete_requires_flag",
        "integrity_error",
        "destination_collision",
        "seal_mismatch",
    ],
)
def test_finalize_rejections_announce_known_target_and_exit_two(
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "capsule"

    def reject(
        path: Path,
        *,
        seal_incomplete: bool,
        on_target_known: object,
        seams: object,
    ) -> None:
        del seal_incomplete, seams
        assert callable(on_target_known)
        on_target_known(path)
        on_target_known(path)
        raise FinalizationError(code)

    monkeypatch.setattr(cli, "_finalize_capsule", reject)

    assert main(["finalize", str(target)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == f"{target}\n"
    assert captured.err == "error: capsule finalization rejected\n"


def test_finalize_invalid_target_does_not_announce_unknown_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "missing"

    def reject(
        path: Path,
        *,
        seal_incomplete: bool,
        on_target_known: object,
        seams: object,
    ) -> None:
        del path, seal_incomplete, on_target_known, seams
        raise FinalizationError("invalid_argument")

    monkeypatch.setattr(cli, "_finalize_capsule", reject)

    assert main(["finalize", str(target)], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: capsule finalization rejected\n"


def test_finalize_postpublication_fsync_failure_announces_once_and_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "capsule"

    def fail_after_publication(
        path: Path,
        *,
        seal_incomplete: bool,
        on_target_known: object,
        seams: object,
    ) -> None:
        del seal_incomplete, seams
        assert callable(on_target_known)
        on_target_known(path)
        on_target_known(path)
        raise FinalizationError("post_publish_fsync_failed")

    monkeypatch.setattr(cli, "_finalize_capsule", fail_after_publication)

    assert main(["finalize", str(target)], program="laconian") == 1

    captured = capsys.readouterr()
    assert captured.out == f"{target}\n"
    assert captured.err == "finalize failed: capsule finalization rejected\n"


def test_verify_require_sealed_accepts_sealed_capsule_without_mutating_parent_tree(
    sealed_capsule: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent = sealed_capsule.parent
    before = _snapshot_tree(parent)

    direct = verify_capsule(sealed_capsule, mode=VerificationMode.PREPARED)

    assert direct.status == "valid", direct
    assert direct.state == "SEALED_BLOCKED"
    assert direct.capsule_sha256 == sha256_bytes((sealed_capsule / "seal.json").read_bytes())
    assert _snapshot_tree(parent) == before

    assert main(["verify", str(sealed_capsule), "--require", "sealed"], program="laconian") == 0

    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == canonical_json(direct.model_dump(mode="json")) + b"\n"
    assert captured.err == ""
    assert _snapshot_tree(parent) == before


def test_verify_require_sealed_preserves_valid_unsealed_json_and_parent_tree(
    prepared_capsule: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent = prepared_capsule.parent
    before = _snapshot_tree(parent)

    direct = verify_capsule(prepared_capsule, mode=VerificationMode.PREPARED)

    assert direct.status == "valid"
    assert direct.state == "PREPARED"
    assert direct.capsule_sha256 is None
    assert _snapshot_tree(parent) == before

    assert main(["verify", str(prepared_capsule), "--require", "sealed"], program="laconian") == 2

    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == canonical_json(direct.model_dump(mode="json")) + b"\n"
    assert captured.err == ""
    assert _snapshot_tree(parent) == before
