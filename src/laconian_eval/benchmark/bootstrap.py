"""Frozen scenario-cluster bootstrap vectors and percentile intervals."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from typing import Literal, Self

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from laconian_eval.benchmark.aggregation import (
    PlannedObservationV1,
    _validate_population,
    _validated_exact_rows,
)

BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_CLUSTER_COUNT = 12
BOOTSTRAP_MIN_VALID = 9_990

_VECTOR_DIGEST_DOMAIN = b"laconian-bootstrap-vectors-v1"


class BootstrapVectorsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = Field(ge=0, lt=2**128)
    scenario_uids: tuple[str, ...]
    replicates: Literal[10_000] = 10_000
    index_dtype: Literal["uint8"] = "uint8"
    indices_sha256: str


class BootstrapIntervalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    point: float | None
    lower: float | None
    upper: float | None
    valid_replicates: int = Field(ge=0, le=10_000)
    total_replicates: Literal[10_000] = 10_000
    available: bool
    inferential_target: Literal[
        "scenario-superpopulation-conditional-on-fixed-campaign"
    ] = "scenario-superpopulation-conditional-on-fixed-campaign"
    coverage: Literal[
        "nominal-95-percent-approximate-12-cluster-percentile"
    ] = "nominal-95-percent-approximate-12-cluster-percentile"

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        for value in (self.point, self.lower, self.upper):
            if value is not None and not math.isfinite(value):
                raise ValueError("bootstrap interval values must be finite when present")
        if self.available:
            if (
                self.valid_replicates < BOOTSTRAP_MIN_VALID
                or self.lower is None
                or self.upper is None
            ):
                raise ValueError(
                    "available interval requires at least 9990 valid replicates and endpoints"
                )
            if self.lower > self.upper:
                raise ValueError("bootstrap lower endpoint exceeds upper endpoint")
        elif (
            self.valid_replicates >= BOOTSTRAP_MIN_VALID
            or self.lower is not None
            or self.upper is not None
        ):
            raise ValueError(
                "unavailable interval requires fewer than 9990 valid replicates and null endpoints"
            )
        return self


def _ordered_scenario_uids(scenario_uids: Sequence[str]) -> tuple[str, ...]:
    projected = tuple(scenario_uids)
    if any(type(value) is not str for value in projected):
        raise ValueError("scenario UIDs must be strings")
    try:
        ordered = tuple(sorted(projected, key=lambda value: value.encode("utf-8")))
    except UnicodeEncodeError as exc:
        raise ValueError("scenario UIDs must be valid UTF-8") from exc
    if len(ordered) != BOOTSTRAP_CLUSTER_COUNT or len(set(ordered)) != len(ordered):
        raise ValueError("exactly twelve distinct scenario UIDs are required")
    return ordered


def _validate_index_matrix(indices: object) -> NDArray[np.uint8]:
    if type(indices) is not np.ndarray:
        raise ValueError("bootstrap indices must be an exact ndarray")
    if indices.dtype != np.dtype(np.uint8):
        raise ValueError("bootstrap indices must have dtype uint8")
    if indices.shape != (BOOTSTRAP_REPLICATES, BOOTSTRAP_CLUSTER_COUNT):
        raise ValueError("bootstrap indices must have shape (10000, 12)")
    if not indices.flags.c_contiguous:
        raise ValueError("bootstrap indices must use canonical C order")
    if np.any(indices >= BOOTSTRAP_CLUSTER_COUNT):
        raise ValueError("bootstrap indices must be in the closed range 0..11")
    return indices


def _indices_digest(
    *, seed: int, scenario_uids: tuple[str, ...], indices: NDArray[np.uint8]
) -> str:
    digest = hashlib.sha256()
    digest.update(_VECTOR_DIGEST_DOMAIN)
    digest.update(b"\0")
    digest.update(seed.to_bytes(16, "big", signed=False))
    for scenario_uid in scenario_uids:
        encoded = scenario_uid.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big", signed=False))
        digest.update(encoded)
    digest.update(b"uint8\0")
    digest.update(BOOTSTRAP_REPLICATES.to_bytes(8, "big", signed=False))
    digest.update(BOOTSTRAP_CLUSTER_COUNT.to_bytes(8, "big", signed=False))
    digest.update(indices.tobytes(order="C"))
    return digest.hexdigest()


def _seal_vector_metadata(
    seed: int,
    scenario_uids: tuple[str, ...],
    indices: NDArray[np.uint8],
) -> BootstrapVectorsV1:
    return BootstrapVectorsV1(
        seed=seed,
        scenario_uids=scenario_uids,
        index_dtype="uint8",
        indices_sha256=_indices_digest(
            seed=seed, scenario_uids=scenario_uids, indices=indices
        ),
    )


def _verify_cluster_vectors(
    metadata: BootstrapVectorsV1, indices: object
) -> NDArray[np.uint8]:
    """Reject any metadata, dtype, shape, range, or matrix substitution."""

    if type(metadata) is not BootstrapVectorsV1:
        raise ValueError("bootstrap metadata must be an exact BootstrapVectorsV1")
    checked_indices = _validate_index_matrix(indices)
    ordered = _ordered_scenario_uids(metadata.scenario_uids)
    if ordered != metadata.scenario_uids:
        raise ValueError("bootstrap scenario UIDs are not in canonical UTF-8 order")
    expected = _indices_digest(
        seed=metadata.seed,
        scenario_uids=ordered,
        indices=checked_indices,
    )
    if metadata.indices_sha256 != expected:
        raise ValueError("bootstrap index digest mismatch")
    return checked_indices


def make_cluster_vectors(
    *, seed: int, scenario_uids: Sequence[str]
) -> tuple[BootstrapVectorsV1, NDArray[np.uint8]]:
    if type(seed) is not int or not 0 <= seed < 2**128:
        raise ValueError("seed must be an integer in the closed 128-bit range")
    ordered = _ordered_scenario_uids(scenario_uids)
    generator = np.random.Generator(np.random.PCG64(seed))
    indices = generator.integers(
        0,
        BOOTSTRAP_CLUSTER_COUNT,
        size=(BOOTSTRAP_REPLICATES, BOOTSTRAP_CLUSTER_COUNT),
        dtype=np.uint8,
    )
    checked_indices = _validate_index_matrix(indices)
    metadata = _seal_vector_metadata(seed, ordered, checked_indices)
    _verify_cluster_vectors(metadata, checked_indices)
    return metadata, checked_indices


def type7_quantile(values: NDArray[np.float64], q: float) -> float:
    projected = np.asarray(values, dtype=np.float64)
    if projected.ndim != 1 or projected.size == 0:
        raise ValueError("type-7 quantile requires a nonempty one-dimensional vector")
    if not np.all(np.isfinite(projected)):
        raise ValueError("type-7 quantile values must all be finite")
    if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q):
        raise ValueError("quantile probability must be finite")
    if not 0.0 <= q <= 1.0:
        raise ValueError("quantile probability must be between zero and one")
    ordered = np.sort(projected)
    h = (len(ordered) - 1) * q
    j = math.floor(h)
    g = h - j
    return float(
        ordered[j]
        + g * (ordered[min(j + 1, len(ordered) - 1)] - ordered[j])
    )


def cluster_percentile_interval(
    *,
    point: float | None,
    rows: Sequence[PlannedObservationV1],
    indices: NDArray[np.uint8],
    estimator: Callable[[Sequence[PlannedObservationV1]], float | None],
) -> BootstrapIntervalV1:
    """Rebuild sampled scenario blocks and return frozen type-7 percentile endpoints."""

    checked_indices = _validate_index_matrix(indices)
    checked_rows = _validated_exact_rows(rows)
    _validate_population(checked_rows)
    scenario_uids = tuple(
        sorted({row.scenario_uid for row in checked_rows}, key=lambda uid: uid.encode())
    )
    blocks = tuple(
        tuple(row for row in checked_rows if row.scenario_uid == scenario_uid)
        for scenario_uid in scenario_uids
    )
    if len(blocks) != BOOTSTRAP_CLUSTER_COUNT or any(
        len(block) != 40 for block in blocks
    ):
        raise ValueError("rows do not form twelve complete 40-row scenario blocks")

    estimates: list[float] = []
    for replicate in checked_indices:
        sampled = tuple(
            row for index in replicate for row in blocks[int(index)]
        )
        estimate = estimator(sampled)
        if estimate is not None and math.isfinite(estimate):
            estimates.append(float(estimate))

    valid_replicates = len(estimates)
    if valid_replicates < BOOTSTRAP_MIN_VALID:
        return BootstrapIntervalV1(
            point=point,
            lower=None,
            upper=None,
            valid_replicates=valid_replicates,
            available=False,
        )
    finite = np.asarray(estimates, dtype=np.float64)
    return BootstrapIntervalV1(
        point=point,
        lower=type7_quantile(finite, 0.025),
        upper=type7_quantile(finite, 0.975),
        valid_replicates=valid_replicates,
        available=True,
    )


__all__ = (
    "BOOTSTRAP_CLUSTER_COUNT",
    "BOOTSTRAP_MIN_VALID",
    "BOOTSTRAP_REPLICATES",
    "BootstrapIntervalV1",
    "BootstrapVectorsV1",
    "cluster_percentile_interval",
    "make_cluster_vectors",
    "type7_quantile",
)
