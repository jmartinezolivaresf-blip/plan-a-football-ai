"""Deterministic text verifier: the LLM never writes numbers; claims do.

Rules (v6 §9.14 and the H1 brief):
1. No digits outside `{claim_id.field}` placeholders (player ids such as HAR-5 are identifiers, not numbers).
2. Every placeholder references an existing claim and an allowed field.
3. Every sentence cites at least one claim (placeholder or `[claim_id]` tag).
4. A claim with `status == "insufficient"` cannot back a definitive statement: the sentence must hedge.
5. Causal wording requires an `observed_mechanism` claim in the same sentence.
6. Casual mode: no intervals.
Invalid text is rejected; callers regenerate at most twice, then use a fixed template (`with_fallback`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from contracts import Claim
from contracts.claim import PLACEHOLDER_FIELDS

PLACEHOLDER = re.compile(r"\{(c[\w-]+)\.(\w+)\}")
TAG = re.compile(r"\[(c[\w-]+)\]")
PLAYER_ID = re.compile(r"\b[A-Z]{3}-\d{1,2}\b")  # identifiers such as HAR-5 are names, not statistics
SENTENCE = re.compile(r"(?<=[.!?])\s+")
CAUSAL = re.compile(r"\b(because|caused|causes|due to|leads to|led to|results in|therefore|so that|"
                    r"porque|debido a|provoca|provocó|causa|por lo tanto)\b", re.IGNORECASE)
HEDGE = re.compile(r"\b(may|might|could|possible|possibly|suggests?|early sign|too early|limited evidence|"
                   r"puede|podría|posible|posiblemente|sugiere|indicio|muestra pequeña|poca evidencia)\b",
                   re.IGNORECASE)
INTERVAL_FIELDS = {"interval_low", "interval_high"}
MAX_ATTEMPTS = 3  # first try + two corrections


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE.split(text.strip()) if s.strip()]


def verify(text: str, claims: Mapping[str, Claim], mode: str = "analyst") -> list[str]:
    errors: list[str] = []
    if not text.strip():
        return ["empty text"]
    if re.search(r"\d", PLAYER_ID.sub("", PLACEHOLDER.sub("", TAG.sub("", text)))):
        errors.append("contains numbers that do not come from a claim placeholder")
    for cid, fld in PLACEHOLDER.findall(text):
        if cid not in claims:
            errors.append(f"unknown claim {cid}")
        elif fld not in PLACEHOLDER_FIELDS:
            errors.append(f"field {fld} is not allowed in placeholders")
        elif getattr(claims[cid], fld) is None:
            errors.append(f"claim {cid} has no {fld}")
        if mode == "casual" and fld in INTERVAL_FIELDS:
            errors.append("casual mode must not show intervals")
    for cid in TAG.findall(text):
        if cid not in claims:
            errors.append(f"unknown claim {cid}")
    for sentence in _sentences(text):
        cited = [c for c, _ in PLACEHOLDER.findall(sentence)] + TAG.findall(sentence)
        known = [claims[c] for c in cited if c in claims]
        if not cited:
            errors.append(f"sentence cites no claim: {sentence[:60]!r}")
            continue
        if any(c.status == "insufficient" for c in known) and not HEDGE.search(sentence):
            errors.append(f"insufficient evidence stated as a conclusion: {sentence[:60]!r}")
        if CAUSAL.search(sentence) and not any(c.type == "observed_mechanism" for c in known):
            errors.append(f"causal claim without an observed_mechanism claim: {sentence[:60]!r}")
    return errors


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.0%}" if 0 < abs(value) < 1 else f"{value:g}"
    return str(value)


def fill(text: str, claims: Mapping[str, Claim]) -> str:
    """Replace placeholders with claim values and drop [claim] tags. Call only on verified text."""
    out = PLACEHOLDER.sub(lambda m: _fmt(getattr(claims[m.group(1)], m.group(2))), text)
    return re.sub(r"\s*\[c[\w-]+\]", "", out)


def with_fallback(generate: Callable[[list[str]], str], claims: Mapping[str, Claim], fallback: str,
                  mode: str = "analyst") -> tuple[str, list[list[str]], bool]:
    """Ask `generate(previous_errors)` up to MAX_ATTEMPTS times; return (text, errors per attempt, used_fallback).

    The fallback must itself verify (it is built from claims by code); otherwise this raises.
    """
    history: list[list[str]] = []
    errors: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        text = generate(errors)
        errors = verify(text, claims, mode)
        history.append(errors)
        if not errors:
            return text, history, False
    fb_errors = verify(fallback, claims, mode)
    if fb_errors:
        raise ValueError(f"fallback template does not verify: {fb_errors}")
    return fallback, history, True
