"""One genuine portable campaign build shared by all offline replay contract tests."""

from __future__ import annotations

import shutil

import pytest

from laconian_eval.capsule.canonical import canonical_json
from tests.benchmark import helpers


@pytest.fixture(scope="session")
def replay_campaign(tmp_path_factory):
    campaign = helpers.build_synthetic_public_campaign(tmp_path_factory.mktemp("offline-cli"))
    authority = campaign.workspace_root / "GENERATION_COMPLETE"
    authority.mkdir()
    expectation = campaign.provider_fixture.expectation.expectation
    (authority / "generation-context-expectation.json").write_bytes(
        canonical_json(expectation.model_dump(mode="json")) + b"\n"
    )
    review = campaign.workspace_root / "REVIEWS"
    shutil.copytree(campaign.audit_root, review)
    (review / "audit/audit-evidence.json").unlink()
    (review / "audit/metrics.json").unlink()
    return campaign
