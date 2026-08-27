from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from laconian_eval.capsule.bounded_io import (
    normalize_source_path,
    open_directory_no_follow,
    read_regular_file_once,
    write_owned_file,
)
from laconian_eval.capsule.limits import ResourceLimitError
from laconian_eval.yaml_io import safe_load_unique_bytes


@pytest.mark.parametrize(
    "value",
    [
        "cases/response.yaml",
        "one.yaml",
        "unicode/\u03b1.yaml",
        "spaces are literal/input.yaml",
    ],
)
def test_normalize_source_path_preserves_valid_relative_posix_spelling(value: str) -> None:
    assert normalize_source_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "/absolute",
        "//server/share",
        "../escape",
        "inside/../escape",
        "inside/./file",
        "inside//file",
        "inside/",
        "./inside",
        "C:/windows",
        "c:relative",
        "C:\\windows",
        "\\\\server\\share",
        "inside\\file",
        "inside/\x00file",
        "inside/\x1ffile",
        "inside/\x7ffile",
    ],
)
def test_normalize_source_path_rejects_noncanonical_or_platform_aliases(value: str) -> None:
    with pytest.raises(ValueError) as caught:
        normalize_source_path(value)
    if value:
        assert value not in str(caught.value)


def test_normalize_source_path_rejects_non_string_values() -> None:
    with pytest.raises(ValueError):
        normalize_source_path(Path("cases/input.yaml"))  # type: ignore[arg-type]


def test_open_directory_no_follow_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError):
        open_directory_no_follow(link)


def test_open_directory_no_follow_fails_closed_without_required_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "O_NOFOLLOW")

    with pytest.raises(RuntimeError, match="no-follow"):
        open_directory_no_follow(tmp_path)


def test_read_regular_file_once_uses_no_follow_nonblocking_single_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"abc")
    root_fd = open_directory_no_follow(tmp_path)
    real_open = os.open
    final_opens: list[int] = []

    def tracking_open(
        opened_path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if opened_path == "payload.bin":
            final_opens.append(flags)
        return real_open(opened_path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", tracking_open)
    try:
        assert (
            read_regular_file_once(
                root_fd,
                "payload.bin",
                limit=3,
                code="test_file_limit",
            )
            == b"abc"
        )
    finally:
        os.close(root_fd)

    assert len(final_opens) == 1
    assert final_opens[0] & os.O_NOFOLLOW
    assert final_opens[0] & os.O_NONBLOCK


def test_read_regular_file_once_rejects_intermediate_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "payload.bin").write_bytes(b"secret")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    root_fd = open_directory_no_follow(tmp_path)
    try:
        with pytest.raises(OSError):
            read_regular_file_once(
                root_fd,
                "alias/payload.bin",
                limit=100,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)


def test_read_regular_file_once_rejects_non_regular_directory(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    root_fd = open_directory_no_follow(tmp_path)
    try:
        with pytest.raises(ValueError, match="regular file"):
            read_regular_file_once(
                root_fd,
                "nested",
                limit=100,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_read_regular_file_once_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "source.fifo"
    os.mkfifo(fifo)
    root_fd = open_directory_no_follow(tmp_path)
    try:
        with pytest.raises(ValueError, match="regular file"):
            read_regular_file_once(
                root_fd,
                "source.fifo",
                limit=100,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)


def test_read_regular_file_once_checks_size_before_read_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "oversized.bin").write_bytes(b"four")
    root_fd = open_directory_no_follow(tmp_path)

    def forbidden_read(file_descriptor: int, count: int) -> bytes:
        raise AssertionError("oversized source must be rejected before read")

    monkeypatch.setattr(os, "read", forbidden_read)
    try:
        with pytest.raises(ResourceLimitError) as caught:
            read_regular_file_once(
                root_fd,
                "oversized.bin",
                limit=3,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)

    assert caught.value.code == "test_file_limit"
    assert b"four".decode() not in str(caught.value)


def test_read_regular_file_once_rejects_detectable_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mutable.bin"
    path.write_bytes(b"captured")
    root_fd = open_directory_no_follow(tmp_path)
    real_read = os.read
    changed = False

    def mutating_read(file_descriptor: int, count: int) -> bytes:
        nonlocal changed
        result = real_read(file_descriptor, count)
        if not changed:
            changed = True
            before = path.stat()
            os.utime(
                path,
                ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
            )
        return result

    monkeypatch.setattr(os, "read", mutating_read)
    try:
        with pytest.raises(ValueError, match="mutated"):
            read_regular_file_once(
                root_fd,
                "mutable.bin",
                limit=100,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)


def test_read_regular_file_once_rejects_growth_past_exact_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "growing.bin"
    path.write_bytes(b"abc")
    root_fd = open_directory_no_follow(tmp_path)
    real_read = os.read
    appended = False

    def growing_read(file_descriptor: int, count: int) -> bytes:
        nonlocal appended
        result = real_read(file_descriptor, count)
        if not appended:
            appended = True
            with path.open("ab") as stream:
                stream.write(b"d")
        return result

    monkeypatch.setattr(os, "read", growing_read)
    try:
        with pytest.raises(ResourceLimitError) as caught:
            read_regular_file_once(
                root_fd,
                "growing.bin",
                limit=3,
                code="test_file_limit",
            )
    finally:
        os.close(root_fd)

    assert caught.value.code == "test_file_limit"


def test_write_owned_file_is_descriptor_relative_private_and_no_overwrite(
    tmp_path: Path,
) -> None:
    (tmp_path / "owned").mkdir()
    root_fd = open_directory_no_follow(tmp_path)
    try:
        write_owned_file(root_fd, "owned/result.bin", b"result")
        with pytest.raises(FileExistsError):
            write_owned_file(root_fd, "owned/result.bin", b"replacement")
    finally:
        os.close(root_fd)

    target = tmp_path / "owned" / "result.bin"
    assert target.read_bytes() == b"result"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_write_owned_file_rejects_intermediate_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "alias").symlink_to(outside, target_is_directory=True)
    root_fd = open_directory_no_follow(tmp_path)
    try:
        with pytest.raises(OSError):
            write_owned_file(root_fd, "alias/escape.bin", b"must not escape")
    finally:
        os.close(root_fd)
    assert not (outside / "escape.bin").exists()


@pytest.mark.parametrize(
    "document",
    [
        b"value: &shared secret\n",
        b"value: *shared\n",
        b"base: {key: value}\ncopy: {<<: {key: replacement}}\n",
    ],
)
def test_strict_yaml_bytes_reject_anchors_aliases_and_merge(document: bytes) -> None:
    with pytest.raises(ValueError):
        safe_load_unique_bytes(document)


def test_strict_yaml_bytes_rejects_duplicates_without_echoing_values() -> None:
    secret = b"never-echo-this-secret"
    document = b"key: first\nkey: " + secret + b"\n"

    with pytest.raises(ValueError, match="duplicate mapping key") as caught:
        safe_load_unique_bytes(document)

    assert secret.decode() not in str(caught.value)


def test_strict_yaml_bytes_distinguishes_different_scalar_key_types() -> None:
    assert safe_load_unique_bytes(b'true: boolean\n"true": string\n') == {
        True: "boolean",
        "true": "string",
    }


def test_strict_yaml_bytes_accepts_depth_64_and_rejects_depth_65() -> None:
    depth_64 = b"[" * 64 + b"0" + b"]" * 64
    depth_65 = b"[" * 65 + b"0" + b"]" * 65

    safe_load_unique_bytes(depth_64)
    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(depth_65)
    assert caught.value.code == "nesting_depth_limit"


def test_strict_yaml_bytes_checks_collection_limit_before_construction() -> None:
    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(
            b"values: [one, two, three]\n",
            collection_limit=2,
            collection_code="test_collection_limit",
        )
    assert caught.value.code == "test_collection_limit"


def test_strict_yaml_bytes_rejects_invalid_utf8_without_echoing_content() -> None:
    rejected = b"secret-\xff-value"
    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(rejected)
    assert caught.value.code == "invalid_utf8"
    assert "secret" not in str(caught.value)


def test_strict_yaml_bytes_checks_byte_limit_before_decode() -> None:
    rejected = b"secret"
    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(
            rejected,
            byte_limit=5,
            byte_code="test_yaml_bytes_limit",
        )
    assert caught.value.code == "test_yaml_bytes_limit"
    assert rejected.decode() not in str(caught.value)


@pytest.mark.parametrize(
    "document",
    [
        b"value: !!int ''\n",
        b"value: !!timestamp nope\n",
        b"value: !!bool maybe\n",
    ],
)
def test_strict_yaml_bytes_contains_constructor_exceptions(document: bytes) -> None:
    with pytest.raises(ValueError, match="invalid YAML") as caught:
        safe_load_unique_bytes(document)
    assert document.decode().strip() not in str(caught.value)
