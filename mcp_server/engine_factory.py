"""ENGINE=mock|real selects the EngineAPI implementation without touching the tools."""

from __future__ import annotations

import os

from contracts.engine_api import EngineAPI

from .mock_engine import MockEngine


def get_engine(name: str | None = None) -> EngineAPI:
    name = (name or os.environ.get("ENGINE", "mock")).lower()
    if name == "mock":
        return MockEngine()
    if name == "real":
        try:
            from engine.api import RealEngine  # provided by person A at I1 (Saturday 13:00)
        except ImportError as exc:
            raise RuntimeError("ENGINE=real needs engine.api.RealEngine (person A, I1)") from exc
        engine = RealEngine()
        if not isinstance(engine, EngineAPI):
            raise TypeError("engine.api.RealEngine does not implement contracts.engine_api.EngineAPI")
        return engine
    raise ValueError(f"unknown ENGINE={name!r} (mock|real)")
