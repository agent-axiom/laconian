from __future__ import annotations

import errno
import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from laconian_eval.capsule.bounded_io import (
    normalize_source_path,
    open_directory_no_follow,
    read_regular_file_once,
    write_owned_file,
)
from laconian_eval.capsule.limits import ResourceLimitError
from laconian_eval.yaml_io import StrictYamlError, safe_load_unique_bytes


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


def test_open_directory_no_follow_rejects_intermediate_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    target = real / "target"
    target.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(OSError):
        open_directory_no_follow(alias / "target")


def test_open_directory_no_follow_fails_closed_without_required_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "O_NOFOLLOW")

    with pytest.raises(RuntimeError, match="no-follow"):
        open_directory_no_follow(tmp_path)


def test_open_directory_no_follow_never_retries_an_ambiguous_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from laconian_eval.capsule import bounded_io

    target = tmp_path / "nested"
    target.mkdir()
    real_close = os.close
    real_open = os.open
    opened_by_subject: list[int] = []
    replacement_fd: int | None = None
    injected = False

    def tracking_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        opened_by_subject.append(descriptor)
        return descriptor

    def close_then_reuse_and_raise(descriptor: int) -> None:
        nonlocal injected, replacement_fd
        if not injected:
            injected = True
            real_close(descriptor)
            replacement_fd = real_open("/dev/null", os.O_RDONLY)
            assert replacement_fd == descriptor
            raise OSError(errno.EIO, "injected ambiguous close")
        real_close(descriptor)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(bounded_io.os, "open", tracking_open)
            patch.setattr(bounded_io.os, "close", close_then_reuse_and_raise)
            with pytest.raises(OSError) as caught:
                open_directory_no_follow(target)
        assert caught.value.errno == errno.EIO
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        for descriptor in {*opened_by_subject, replacement_fd} - {None}:
            try:
                os.fstat(descriptor)
            except OSError:
                continue
            real_close(descriptor)


def test_parent_walk_never_retries_an_ambiguous_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from laconian_eval.capsule import bounded_io

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "payload.bin").write_bytes(b"payload")
    root_fd = open_directory_no_follow(tmp_path)
    real_close = os.close
    real_open = os.open
    opened_by_subject: list[int] = []
    replacement_fd: int | None = None
    injected = False

    def tracking_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        opened_by_subject.append(descriptor)
        return descriptor

    def close_then_reuse_and_raise(descriptor: int) -> None:
        nonlocal injected, replacement_fd
        if not injected:
            injected = True
            real_close(descriptor)
            replacement_fd = real_open("/dev/null", os.O_RDONLY)
            assert replacement_fd == descriptor
            raise OSError(errno.EIO, "injected ambiguous close")
        real_close(descriptor)

    try:
        try:
            with monkeypatch.context() as patch:
                patch.setattr(bounded_io.os, "open", tracking_open)
                patch.setattr(bounded_io.os, "close", close_then_reuse_and_raise)
                with pytest.raises(OSError) as caught:
                    read_regular_file_once(
                        root_fd,
                        "nested/payload.bin",
                        limit=100,
                        code="test_file_limit",
                    )
            assert caught.value.errno == errno.EIO
            assert replacement_fd is not None
            os.fstat(replacement_fd)
        finally:
            real_close(root_fd)
    finally:
        for descriptor in {*opened_by_subject, replacement_fd} - {None}:
            try:
                os.fstat(descriptor)
            except OSError:
                continue
            real_close(descriptor)


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
    previous_umask = os.umask(0)
    try:
        root_fd = open_directory_no_follow(tmp_path)
        try:
            write_owned_file(root_fd, "owned/result.bin", b"result")
            with pytest.raises(FileExistsError):
                write_owned_file(root_fd, "owned/result.bin", b"replacement")
        finally:
            os.close(root_fd)
    finally:
        os.umask(previous_umask)

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


def test_strict_yaml_bytes_does_not_construct_implicit_sexagesimal_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import yaml_io

    def forbidden_integer_constructor(*args: object, **kwargs: object) -> object:
        raise AssertionError("implicit sexagesimal must not reach the integer constructor")

    monkeypatch.setitem(
        yaml_io._StrictUniqueKeySafeLoader.yaml_constructors,
        "tag:yaml.org,2002:int",
        forbidden_integer_constructor,
    )
    value = b"1:" * 64_000 + b"1"

    assert safe_load_unique_bytes(b"value: " + value + b"\n") == {"value": value.decode()}


@pytest.mark.parametrize("tail", [b"1", b"99"])
def test_strict_yaml_bytes_rejects_explicit_sexagesimal_integer_before_compose(
    tail: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import yaml_io

    def forbidden_compose(*args: object, **kwargs: object) -> object:
        raise AssertionError("sexagesimal scalar must fail before compose")

    def forbidden_construction(text: str) -> object:
        raise AssertionError("sexagesimal scalar must fail before construction")

    monkeypatch.setattr(yaml_io.yaml, "compose", forbidden_compose)
    monkeypatch.setattr(yaml_io, "_construct_strict_yaml", forbidden_construction)
    document = b"value: !!int " + b"1:" * 64_000 + tail + b"\n"

    with pytest.raises(StrictYamlError) as caught:
        safe_load_unique_bytes(document)

    assert caught.value.code == "yaml_sexagesimal_number"
    assert "1:1" not in str(caught.value)


def test_strict_yaml_bytes_retains_ordinary_implicit_scalars() -> None:
    assert safe_load_unique_bytes(
        b"decimal: 123\nnegative: -42\nfloat: 1.5\n"
        b"truth: true\nfalsehood: false\nnothing: null\n"
        b"plain_sexagesimal: 1:1\nquoted: '1:1'\nexplicit: !!str 1:1\n"
    ) == {
        "decimal": 123,
        "negative": -42,
        "float": 1.5,
        "truth": True,
        "falsehood": False,
        "nothing": None,
        "plain_sexagesimal": "1:1",
        "quoted": "1:1",
        "explicit": "1:1",
    }


def test_strict_yaml_bytes_rejects_cumulative_nodes_before_compose_or_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import yaml_io

    def forbidden_compose(*args: object, **kwargs: object) -> object:
        raise AssertionError("cumulative node limit must fail before compose")

    def forbidden_construction(text: str) -> object:
        raise AssertionError("cumulative node limit must fail before construction")

    monkeypatch.setattr(yaml_io.yaml, "compose", forbidden_compose)
    monkeypatch.setattr(yaml_io, "_construct_strict_yaml", forbidden_construction)
    row = b"  - [" + b",".join(b"0" for _ in range(100)) + b"]\n"
    document = b"values:\n" + row * 100

    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(
            document,
            collection_limit=100,
            collection_code="test_collection_limit",
        )

    assert caught.value.code == "yaml_nodes_limit"


def test_strict_yaml_bytes_counts_collection_nodes_in_cumulative_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import yaml_io

    def forbidden_compose(*args: object, **kwargs: object) -> object:
        raise AssertionError("cumulative node limit must fail before compose")

    def forbidden_construction(text: str) -> object:
        raise AssertionError("cumulative node limit must fail before construction")

    monkeypatch.setattr(yaml_io.yaml, "compose", forbidden_compose)
    monkeypatch.setattr(yaml_io, "_construct_strict_yaml", forbidden_construction)
    row = b"  - [" + b",".join(b"{}" for _ in range(10)) + b"]\n"
    document = b"values:\n" + row * 10

    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(
            document,
            collection_limit=10,
            collection_code="test_collection_limit",
            node_limit=111,
        )

    assert caught.value.code == "yaml_nodes_limit"


def test_strict_yaml_bytes_applies_node_budget_when_collection_limit_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval import yaml_io

    def forbidden_compose(*args: object, **kwargs: object) -> object:
        raise AssertionError("default cumulative node limit must fail before compose")

    def forbidden_construction(text: str) -> object:
        raise AssertionError("default cumulative node limit must fail before construction")

    monkeypatch.setattr(
        yaml_io,
        "RESOURCE_LIMITS_V1",
        replace(yaml_io.RESOURCE_LIMITS_V1, case_records=2),
    )
    monkeypatch.setattr(yaml_io.yaml, "compose", forbidden_compose)
    monkeypatch.setattr(yaml_io, "_construct_strict_yaml", forbidden_construction)
    document = b"values: [" + b",".join(b"{}" for _ in range(126)) + b"]\n"

    with pytest.raises(ResourceLimitError) as caught:
        safe_load_unique_bytes(document)

    assert caught.value.code == "yaml_nodes_limit"


def test_strict_yaml_cumulative_budget_allows_exact_collection_limit() -> None:
    document = b"values: [" + b",".join(b"{}" for _ in range(10_000)) + b"]\n"

    loaded = safe_load_unique_bytes(
        document,
        collection_limit=10_000,
        collection_code="test_collection_limit",
    )

    assert isinstance(loaded, dict)
    assert len(loaded["values"]) == 10_000
