"""
Agent 3 — Regression Screener (lightweight)

Quickly checks whether a candidate fix is likely to break currently-passing
tests before spending money on a full eval run.
Uses Haiku — cheap and fast.
"""
from __future__ import annotations

import json

import anthropic
from flask import current_app

from .types import CandidateFix, RegressionScreen

SYSTEM = """\
You are a prompt regression analyst. Given a proposed prompt change and a set
of test cases that currently pass, predict which tests (if any) are at risk.

Be conservative: only flag tests you are reasonably confident will break.
Do not flag tests just because the prompt changed — only flag them if the
specific change conflicts with what that test requires.

Respond with valid JSON only, no markdown fences:
{
  "likely_regressions": ["test_id_1", "test_id_2"],
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}"""

# Only block if screener is this confident regressions will occur
CONFIDENCE_THRESHOLD = 0.75


def screen(
    candidate: CandidateFix,
    passing_tests: list,        # list of TestCase currently passing
    model: str = "claude-haiku-4-5-20251001",
) -> RegressionScreen:

    # Nothing to screen against
    if not passing_tests:
        return RegressionScreen(likely_regressions=[], confidence=0.0)

    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])

    user_message = _build_message(candidate, passing_tests)

    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    return _parse(response.content[0].text)


def should_block(screen_result: RegressionScreen) -> bool:
    """Return True if the screener is confident enough to block the eval run."""
    return (
        bool(screen_result.likely_regressions)
        and screen_result.confidence >= CONFIDENCE_THRESHOLD
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_message(candidate: CandidateFix, passing_tests: list) -> str:
    tests_text = "\n".join(
        f"  [{tc.name}]  "
        f"input: {(tc.input_variables or {}).get('input', '')}  "
        f"expected: {tc.expected_output or tc.description or ''}"
        for tc in passing_tests
    )

    return (
        f"PROPOSED PROMPT CHANGE:\n{candidate.changes_summary}\n\n"
        f"FULL NEW PROMPT:\n\"\"\"\n{candidate.improved_prompt}\n\"\"\"\n\n"
        f"CURRENTLY PASSING TESTS:\n{tests_text}"
    )


def _parse(raw: str) -> RegressionScreen:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        if inner and inner[0].strip().lower() in ("json", ""):
            inner = inner[1:]
        raw = "\n".join(inner).strip()

    data = json.loads(raw)
    return RegressionScreen(
        likely_regressions=data.get("likely_regressions", []),
        confidence=float(data.get("confidence", 0.0)),
    )
