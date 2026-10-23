"""Zone-based vectorised football simulator (person A). Public API: simulate, fork, bind."""

from .api import BoundWorld, bind, fork, fork_detailed, simulate
from .world import PlanError

__all__ = ["BoundWorld", "PlanError", "bind", "fork", "fork_detailed", "simulate"]
