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
        # Public season only (data/season/public.json): scouting and pre-match valuation. The real world (hidden
        # truth) never enters this process; the demo match is played by the pipeline (D-034).
        from pipeline.season_io import load_public_engine

        engine = load_public_engine()
        if not isinstance(engine, EngineAPI):
            raise TypeError("engine.api.RealEngine does not implement contracts.engine_api.EngineAPI")
        return engine
    raise ValueError(f"unknown ENGINE={name!r} (mock|real)")
