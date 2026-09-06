"""Owned offline publication rollback at descriptor-acquisition failures."""

from __future__ import annotations

import errno
import os

import pytest

from laconian_eval.replay import benchmark
from laconian_eval.replay._inputs import Inputs


@pytest.mark.parametrize("race", ("none", "replacement", "unexpected-member"))
def test_stage_open_failure_cleans_only_the_exact_owned_empty_directory(
    tmp_path, monkeypatch, race
):
    original_open = os.open
    descriptors = []
    stage_names = []

    def fail_stage_open(path, flags, *args, **kwargs):
        if isinstance(path, str) and path.startswith(".offline-") and path.endswith(".tmp"):
            stage_names.append(path)
            stage = tmp_path / path
            if race == "replacement":
                stage.rename(tmp_path / "retained-original")
                stage.mkdir()
                (stage / "external-owner").write_bytes(b"preserve")
            elif race == "unexpected-member":
                (stage / "external-owner").write_bytes(b"preserve")
            raise OSError(errno.EMFILE, "canary-model-prompt-label")
        descriptor = original_open(path, flags, *args, **kwargs)
        descriptors.append(descriptor)
        return descriptor

    report = benchmark._report("hard-score", "0" * 64, ())
    with monkeypatch.context() as fault:
        fault.setattr(os, "open", fail_stage_open)
        with (
            Inputs() as inputs,
            pytest.raises(OSError),
            benchmark._publish_report(tmp_path / "offline", report, inputs),
        ):
            pytest.fail("publication must not succeed after stage open fails")
    assert len(stage_names) == 1
    assert not (tmp_path / "offline").exists()
    if race == "none":
        assert list(tmp_path.iterdir()) == []
    else:
        assert (tmp_path / stage_names[0] / "external-owner").read_bytes() == b"preserve"
    for descriptor in descriptors:
        with pytest.raises(OSError) as error:
            os.fstat(descriptor)
        assert error.value.errno == errno.EBADF
