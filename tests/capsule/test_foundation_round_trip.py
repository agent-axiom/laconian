from pathlib import Path

from tests.capsule.foundation_round_trip import run_public_foundation_round_trip


def test_public_foundation_round_trip_from_parent_plan_to_restored_seal(
    tmp_path: Path,
) -> None:
    evidence = run_public_foundation_round_trip(tmp_path=tmp_path)
    assert evidence.provider_call_count == 40
    assert evidence.request_contract_count == 40
    assert evidence.all_request_contracts_exact is True
    assert evidence.all_attempt_evidence_exact is True
    assert evidence.all_visible_token_subtractions_exact is True
    assert evidence.source_seal_sha256 == evidence.restored_seal_sha256
    assert evidence.source_tree_sha256 == evidence.restored_tree_sha256
    assert evidence.source_sidecar_evidence_sha256 == evidence.restored_sidecar_evidence_sha256
