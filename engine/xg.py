"""Engine xG: a logistic model on distance, angle and header, fitted on the season's shots.

The simulator never publishes its internal goal probabilities; the engine estimates xG from observable shot
locations exactly as it would with a real data provider.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from contracts import Event

from .eventsx import rel_x


def features(e: Event, home: str) -> np.ndarray:
    x = rel_x(e, e.team, home)
    dx, dy = 105.0 - x, abs(e.y - 34.0)
    dist = math.hypot(dx, dy)
    a1, a2 = math.atan2(37.66 - e.y, dx), math.atan2(30.34 - e.y, dx)
    angle = abs(a1 - a2)
    return np.array([1.0, dist, angle, 1.0 if e.body_part == "head" else 0.0])


@dataclass
class XGModel:
    w: np.ndarray

    def __call__(self, e: Event, home: str) -> float:
        return float(1.0 / (1.0 + np.exp(-features(e, home) @ self.w)))

    @classmethod
    def fit(cls, shots: list[tuple[Event, str, bool]], l2: float = 1.0, iters: int = 25) -> XGModel:
        """IRLS logistic regression. shots: (event, home, is_goal)."""
        if len(shots) < 20:
            return cls(np.array([-1.2, -0.12, 1.0, -0.6]))
        X = np.stack([features(e, h) for e, h, _ in shots])
        y = np.array([1.0 if g else 0.0 for *_, g in shots])
        w = np.zeros(X.shape[1])
        reg = l2 * np.eye(X.shape[1])
        reg[0, 0] = 0.0
        for _ in range(iters):
            p = 1.0 / (1.0 + np.exp(-X @ w))
            W = p * (1 - p) + 1e-9
            H = X.T @ (X * W[:, None]) + reg
            g = X.T @ (y - p) - reg @ w
            w = w + np.linalg.solve(H, g)
        return cls(w)
