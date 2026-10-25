"""Local settings: load the repository's .env (never committed) without overriding variables already set."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> bool:
    """True if a .env file was found and loaded. Values already in the environment win."""
    from dotenv import load_dotenv

    path = ROOT / ".env"
    return load_dotenv(path, override=False) if path.exists() else False
