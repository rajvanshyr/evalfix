"""
app/services/multi_agent_optimizer.py

Three-agent optimization loop:

  Agent 1 (root_cause)          — diagnose why the prompt fails
  Agent 2 (fix_generator)       — generate a targeted fix
  Agent 3 (regression_screener) — cheap check before running full evals

Loops up to max_iterations (default 3).  Returns a MultiAgentResult whether
or not all tests pass — the caller decides what to do with it.

Must be called inside a Flask app context.
"""
from __future__ import annotations

import difflib
import json
from datetime import datetime

from app.extensions import db
from app.models.prompt_version import PromptVersion
from app.models.test_run import TestRun
from app.models.test_result import TestResult
from app.models.test_case import TestCase
from app.services.evaluator import run_test_run

from .agents import root_cause, fix_generator, regression_screener
from .agents.types import IterationResult, MultiAgentResult


def run(
    prompt: str,                  # current system prompt text
    failed_rows: list,            # (TestResult, TestCase) that are failing
    all_test_cases: list,         # all TestCase objects for this prompt
    prompt_id: str,               # DB prompt ID
    base_version_id: str,         # DB version ID being improved
    model: str = "claude-sonnet-4-6",
    max_iterations: int = 3,
) -> MultiAgentResult:

    history: list[IterationResult] = []
    current_prompt = prompt
    current_failures = failed_rows

    # Test cases that are currently passing (used by regression screener)
    failing_tc_ids = {tc.id for _, tc in failed_rows}
    passing_tests  = [tc for tc in all_test_cases if tc.id not in failing_tc_ids]

    for i in range(1, max_iterations + 1):

        # ── Agent 1: root cause ───────────────────────────────────────────
        root_cause_report = root_cause.analyze(
            prompt=current_prompt,
            failures=current_failures,
            passing_tests=passing_tests,
            history=history,
            model=model,
        )

        # ── Agent 2: fix ──────────────────────────────────────────────────
        candidate = fix_generator.generate(
            prompt=current_prompt,
            root_cause=root_cause_report,
            all_test_cases=all_test_cases,
            history=history,
            model=model,
        )

        # ── Agent 3: regression screen ────────────────────────────────────
        screen = regression_screener.screen(
            candidate=candidate,
            passing_tests=passing_tests,
            model="claude-haiku-4-5-20251001",
        )

        if regression_screener.should_block(screen):
            # High-confidence regression predicted — skip eval, loop back
            history.append(IterationResult(
                iteration=i,
                root_cause=root_cause_report,
                candidate_fix=candidate,
                passed=False,
                pass_count=0,
                fail_count=len(current_failures),
                avg_score=None,
                remaining_failures=current_failures,
                screened_out=True,
            ))
            # Feed the regression warning back to the next iteration
            candidate.changes_summary += (
                f" [blocked: screener predicted regressions on "
                f"{screen.likely_regressions}]"
            )
            continue

        # ── Run full evals against the candidate prompt ───────────────────
        eval_pass, eval_fail, avg_score, remaining = _run_evals(
            candidate.improved_prompt,
            prompt_id,
            base_version_id,
            all_test_cases,
            model,
        )

        iteration = IterationResult(
            iteration=i,
            root_cause=root_cause_report,
            candidate_fix=candidate,
            passed=eval_fail == 0,
            pass_count=eval_pass,
            fail_count=eval_fail,
            avg_score=avg_score,
            remaining_failures=remaining,
        )
        history.append(iteration)

        if eval_fail == 0:
            return MultiAgentResult(
                success=True,
                iterations=i,
                final_prompt=candidate.improved_prompt,
                original_prompt=prompt,
                history=history,
                diff=_diff(prompt, candidate.improved_prompt),
            )

        # Update for next iteration
        current_prompt   = candidate.improved_prompt
        current_failures = remaining
        failing_tc_ids   = {tc.id for _, tc in remaining}
        passing_tests    = [tc for tc in all_test_cases if tc.id not in failing_tc_ids]

    # Exhausted all iterations
    # Return the best candidate (last iteration's prompt)
    best = history[-1].candidate_fix.improved_prompt if history else prompt
    return MultiAgentResult(
        success=False,
        iterations=max_iterations,
        final_prompt=None,
        original_prompt=prompt,
        history=history,
        diff=_diff(prompt, best),
    )


# ---------------------------------------------------------------------------
# Eval helper — creates a draft PromptVersion and runs test cases against it
# ---------------------------------------------------------------------------

def _run_evals(
    candidate_prompt: str,
    prompt_id: str,
    base_version_id: str,
    all_test_cases: list,
    model: str,
) -> tuple[int, int, float | None, list]:
    """
    Create a draft PromptVersion for the candidate prompt, run all test cases,
    and return (pass_count, fail_count, avg_score, remaining_failures).
    """
    from cli.sync import _to_chat_content  # reuse the same chat wrapping

    # Determine next version number
    base = db.session.get(PromptVersion, base_version_id)
    existing_count = PromptVersion.query.filter_by(prompt_id=prompt_id).count()

    version = PromptVersion(
        prompt_id=prompt_id,
        version_number=existing_count + 1,
        content_type="chat",
        content=_to_chat_content(candidate_prompt),
        model=base.model if base else model,
        parameters=base.parameters if base else {},
        parent_version_id=base_version_id,
        source="ai_generated",
        status="draft",
    )
    db.session.add(version)
    db.session.commit()

    test_run = TestRun(
        prompt_version_id=version.id,
        triggered_by="cli",
    )
    db.session.add(test_run)
    db.session.commit()

    run_test_run(test_run.id)
    db.session.refresh(test_run)

    results = TestResult.query.filter_by(test_run_id=test_run.id).all()
    tc_by_id = {tc.id: tc for tc in all_test_cases}
    result_rows = [
        (r, tc_by_id[r.test_case_id])
        for r in results
        if r.test_case_id in tc_by_id
    ]
    remaining = [(r, tc) for r, tc in result_rows if not r.passed]

    return (
        test_run.pass_count,
        test_run.fail_count,
        test_run.avg_score,
        remaining,
    )


def _diff(old: str, new: str) -> str:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        old_lines, new_lines, fromfile="original", tofile="improved"
    ))
