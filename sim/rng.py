"""Counter-based uniforms: u = hash(replica_seed, step, use).

Why not np.random.Generator per replica: two forks that take different decisions would consume draws in a
different order and lose common random numbers. With a stateless hash, the draw for (replica, step, use) is the
same whatever happened before, and replica r of a vectorised run equals a single run with that replica seed.
"""

from __future__ import annotations

import numpy as np

_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_GOLDEN = np.uint64(0x9E3779B97F4A7C15)
_STEP_MUL = np.uint64(0xD1B54A32D192ED03)
_USE_MUL = np.uint64(0x8CB92BA72F3D8DD7)

N_USES = 16  # uniforms drawn per replica per step (see sim/core.py U_* slots)


def _mix(z: np.ndarray) -> np.ndarray:
    """splitmix64 finaliser (vectorised, uint64 wrap-around arithmetic)."""
    with np.errstate(over="ignore"):
        z = (z ^ (z >> np.uint64(30))) * _M1
        z = (z ^ (z >> np.uint64(27))) * _M2
        return z ^ (z >> np.uint64(31))


def replica_seeds(seed: int, replicas: np.ndarray) -> np.ndarray:
    """Per-replica seed h(seed, r). Replica 0 of any R uses the same seed as an R=1 run."""
    with np.errstate(over="ignore"):
        base = np.uint64(seed & 0xFFFFFFFFFFFFFFFF) * _GOLDEN
        return _mix(base + replicas.astype(np.uint64) * _GOLDEN + np.uint64(1))


def uniforms(seeds: np.ndarray, step: int) -> np.ndarray:
    """(R, N_USES) uniforms in [0, 1) for this step."""
    with np.errstate(over="ignore"):
        s = seeds[:, None] ^ (np.uint64(step + 1) * _STEP_MUL)
        z = _mix(s + np.arange(1, N_USES + 1, dtype=np.uint64)[None, :] * _USE_MUL)
    return (z >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)
