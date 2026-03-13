"""
Agent 2 — Fix Generator

Given a root cause report and the current prompt, generates a targeted fix.
Makes the minimum change necessary to address the diagnosed issue.
"""
from __future__ import annotations

import json

import anthropic
from flask import current_app

from .types import RootCauseReport, CandidateFix, IterationResult

SYSTEM = """\
You are an expert prompt engineer specialising in targeted, minimal fixes.

You will be given:
- A system prompt that is producing failures
- A root cause analysis explaining exactly what is wrong
- Test cases the fixed prompt must still handle correctly
- Previous fix attempts to avoid repeating

Your job: write the minimum change to the prompt that addresses the diagnosed
root cause without breaking anything that currently works.

Rules:
- Preserve all existing {variable} placeholders exactly
- Preserve the prompt's overall structure and tone
- Do not add instructions unrelated to the diagnosed issue
- If previous attempts tried the same approach, try something different

Respond with valid JSON only, no markdown fences:
{
  "improved_prompt": "full prompt text with your fix applied",
  "changes_summary": "one sentence: what you changed and why",
  "predicted_regressions": ["test_id_at_risk"],
  "reasoning": "explanation of how this fix addresses the root cause"
}"""


def generate(
    prompt: str,
    root_cause: RootCauseReport,
    all_test_cases: list,          # list of TestCase (passing + failing)
    history: list[IterationResult],
    model: str = "claude-sonnet-4-6",
) -> CandidateFix:

    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])

    user_message = _build_message(prompt, root_cause, all_test_cases, history)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    return _parse(response.content[0].text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_message(
    prompt: str,
    root_cause: RootCauseReport,
    all_test_cases: list,
    history: list[IterationResult],
) -> str:
    parts = []

    parts.append(f"CURRENT PROMPT:\n\"\"\"\n{prompt}\n\"\"\"")

    parts.append(
        "ROOT CAUSE ANALYSIS:\n"
        f"Failure patterns:\n" +
        "\n".join(f"  - {p}" for p in root_cause.failure_patterns) +
        "\n\nPrompt issues:\n" +
        "\n".join(f"  - {p}" for p in root_cause.prompt_issues) +
        f"\n\nAnalyst reasoning: {root_cause.reasoning}"
    )

    parts.append("ALL TEST CASES (your fix must not break these):\n" +
                 _format_test_cases(all_test_cases))

    if history:
        parts.append(
            "PREVIOUS FIX ATTEMPTS (do not repeat these):\n" +
            _format_history(history)
        )

    return "\n\n".join(parts)


def _format_test_cases(test_cases: list) -> str:
    lines = []
    for tc in test_cases:
        inp = (tc.input_variables or {}).get("input", "")
        lines.append(
            f"  [{tc.name}]  "
            f"input: {inp}  "
            f"expected: {tc.expected_output or tc.description or ''}"
        )
    return "\n".join(lines) if lines else "None."


def _format_history(history: list[IterationResult]) -> str:
    lines = []
    for it in history:
        lines.append(
            f"Iteration {it.iteration}:\n"
            f"  Attempted: {it.candidate_fix.changes_summary}\n"
            f"  Result: {it.pass_count} passed, {it.fail_count} still failed"
        )
    return "\n".join(lines)


def _parse(raw: str) -> CandidateFix:
    raw = _strip_fences(raw)
    data = json.loads(raw)
    return CandidateFix(
        improved_prompt=data["improved_prompt"],
        changes_summary=data.get("changes_summary", ""),
        predicted_regressions=data.get("predicted_regressions", []),
        reasoning=data.get("reasoning", ""),
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        if inner and inner[0].strip().lower() in ("json", ""):
            inner = inner[1:]
        text = "\n".join(inner).strip()
    return text
