"""
Agent 1 — Root Cause Analyst

Given the current prompt, observed failures, and passing test cases, diagnoses
WHY the prompt is producing bad outputs.  Does not suggest fixes.
"""
from __future__ import annotations

import json

import anthropic
from flask import current_app

from .types import RootCauseReport, IterationResult

SYSTEM = """\
You are an expert at diagnosing why LLM prompts produce incorrect outputs.

Your ONLY job is to identify the root cause of failures — not to suggest fixes.
Analyse the evidence carefully. Look for patterns across multiple failures rather
than treating each one in isolation.

Be specific: vague diagnoses like "the prompt is unclear" are not useful.
Point to the exact instruction (or missing instruction) that is causing each failure.

Respond with valid JSON only, no markdown fences:
{
  "failure_patterns": ["pattern observed across failures"],
  "prompt_issues": ["specific issue in the prompt causing each pattern"],
  "confidence": 0.0-1.0,
  "reasoning": "detailed step-by-step explanation of your diagnosis"
}"""


def analyze(
    prompt: str,
    failures: list,           # list of (TestResult, TestCase)
    passing_tests: list,      # list of TestCase
    history: list[IterationResult],
    model: str = "claude-sonnet-4-6",
) -> RootCauseReport:

    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])

    user_message = _build_message(prompt, failures, passing_tests, history)

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    return _parse(response.content[0].text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_message(
    prompt: str,
    failures: list,
    passing_tests: list,
    history: list[IterationResult],
) -> str:
    parts = []

    parts.append(f"CURRENT PROMPT:\n\"\"\"\n{prompt}\n\"\"\"")

    parts.append("FAILURES (inputs where the prompt produced wrong output):\n" +
                 _format_failures(failures))

    if passing_tests:
        parts.append("PASSING TESTS (cases the prompt handles correctly — context only):\n" +
                     _format_passing(passing_tests))

    if history:
        parts.append("PREVIOUS FIX ATTEMPTS (do not repeat these approaches):\n" +
                     _format_history(history))
        parts.append(
            "Your previous diagnosis led to a fix that did not fully resolve the failures.\n"
            "Refine your analysis. Consider a fundamentally different root cause."
            if len(history) >= 2 else
            "Your previous diagnosis led to a fix that did not fully resolve the failures.\n"
            "Refine your analysis based on what still fails."
        )

    return "\n\n".join(parts)


def _format_failures(failures: list) -> str:
    lines = []
    for i, (result, tc) in enumerate(failures, 1):
        inp = (tc.input_variables or {}).get("input", "")
        lines.append(
            f"Failure {i}  [{tc.name}]\n"
            f"  Input:    {inp}\n"
            f"  Expected: {tc.expected_output or tc.description or ''}\n"
            f"  Actual:   {result.actual_output or ''}\n"
            + (f"  Judge:    {result.judge_reasoning}\n" if result.judge_reasoning else "")
            + (f"  Error:    {result.error}\n" if result.error else "")
        )
    return "\n".join(lines) if lines else "None."


def _format_passing(passing_tests: list) -> str:
    lines = []
    for tc in passing_tests:
        inp = (tc.input_variables or {}).get("input", "")
        lines.append(f"  [{tc.name}]  input: {inp}  expected: {tc.expected_output or ''}")
    return "\n".join(lines) if lines else "None."


def _format_history(history: list[IterationResult]) -> str:
    lines = []
    for it in history:
        lines.append(
            f"Iteration {it.iteration}:\n"
            f"  Root cause diagnosed: {'; '.join(it.root_cause.prompt_issues)}\n"
            f"  Fix applied: {it.candidate_fix.changes_summary}\n"
            f"  Result: {it.pass_count} passed, {it.fail_count} failed\n"
            f"  Still failing: {[tc.name for _, tc in it.remaining_failures]}"
        )
    return "\n".join(lines)


def _parse(raw: str) -> RootCauseReport:
    raw = _strip_fences(raw)
    data = json.loads(raw)
    return RootCauseReport(
        failure_patterns=data.get("failure_patterns", []),
        prompt_issues=data.get("prompt_issues", []),
        confidence=float(data.get("confidence", 0.5)),
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
