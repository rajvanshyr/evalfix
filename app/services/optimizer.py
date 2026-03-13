"""
Runs an OptimizationRun: calls the LLM with the current prompt, failures, and
test cases, then creates a new PromptVersion with the improved content.
"""
import json
import difflib
from datetime import datetime

import anthropic
from flask import current_app

from ..extensions import db
from ..models.prompt_version import PromptVersion
from ..models.optimization_run import OptimizationRun


def run_optimization(optimization_run_id: str):
    """Execute an optimization run synchronously. Called from the route."""
    from ..models.failure import Failure
    from ..models.test_case import TestCase
    from ..models.prompt import Prompt

    opt_run = OptimizationRun.query.get(optimization_run_id)
    if not opt_run:
        return

    opt_run.status = "running"
    db.session.commit()

    try:
        base_version = PromptVersion.query.get(opt_run.base_version_id)
        failures = Failure.query.filter(Failure.id.in_(opt_run.failure_ids or [])).all()
        test_cases = TestCase.query.filter(TestCase.id.in_(opt_run.test_case_ids or [])).all()

        improved_content, reasoning, meta_prompt = _call_optimizer(
            base_version, failures, test_cases, opt_run.optimizer_model
        )

        # Claude sometimes returns the chat array as a parsed list rather than
        # a JSON string — serialize it back before storing in the Text column.
        if isinstance(improved_content, list):
            improved_content = json.dumps(improved_content)

        # Determine the next version number for this prompt
        latest = (
            PromptVersion.query
            .filter_by(prompt_id=base_version.prompt_id)
            .order_by(PromptVersion.version_number.desc())
            .first()
        )
        next_version_number = (latest.version_number + 1) if latest else 1

        # Create the new PromptVersion (immutable — never edit, always create)
        new_version = PromptVersion(
            prompt_id=base_version.prompt_id,
            version_number=next_version_number,
            content_type=base_version.content_type,
            content=improved_content,
            system_message=base_version.system_message,
            model=base_version.model,
            parameters=base_version.parameters,
            parent_version_id=base_version.id,
            source="ai_generated",
            status="draft",  # stays draft until user accepts it
        )
        db.session.add(new_version)
        db.session.flush()  # get new_version.id before committing

        # Compute diff between old and new content
        diff = _compute_diff(base_version.content, improved_content)

        opt_run.result_version_id = new_version.id
        opt_run.optimizer_prompt = meta_prompt
        opt_run.reasoning = reasoning
        opt_run.diff = diff
        opt_run.status = "completed"
        opt_run.completed_at = datetime.utcnow()

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        opt_run.status = "failed"
        opt_run.error = str(e)
        opt_run.completed_at = datetime.utcnow()
        db.session.commit()
        raise


def _call_optimizer(base_version, failures, test_cases, model):
    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])

    # Render the current prompt nicely for both content types
    if base_version.content_type == "chat":
        content_repr = json.dumps(json.loads(base_version.content), indent=2)
        format_note = (
            'Return improved_prompt as a JSON array of chat messages: '
            '[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]'
        )
    else:
        content_repr = base_version.content
        format_note = "Return improved_prompt as a plain string."

    failures_text = "\n\n".join([
        f"Failure {i + 1}:\n"
        f"  Input: {json.dumps(f.input_variables)}\n"
        f"  Expected: {f.expected_output or 'Not specified'}\n"
        f"  Actual:   {f.actual_output}\n"
        f"  Reason:   {f.failure_reason or 'Not specified'}"
        for i, f in enumerate(failures)
    ]) or "No failures provided."

    test_cases_text = "\n\n".join([
        f"Test Case {i + 1} ({tc.name or 'unnamed'}):\n"
        f"  Input:    {json.dumps(tc.input_variables)}\n"
        f"  Expected: {tc.expected_output}"
        for i, tc in enumerate(test_cases)
    ]) or "No test cases provided."

    meta_prompt = f"""You are an expert prompt engineer. Improve the prompt below based on observed failures.

CURRENT PROMPT:
{content_repr}

FAILURES (real-world cases where the current prompt produced bad outputs):
{failures_text}

GROUND TRUTH TEST CASES (the improved prompt must still handle these correctly):
{test_cases_text}

Instructions:
1. Diagnose why the current prompt causes the failures.
2. Write an improved prompt that fixes those failures without breaking the test cases.
3. Keep the same structure and {'{variable}'} placeholders — only change the instructions/wording.
4. {format_note}

Respond with valid JSON only, no markdown fences:
{{
  "improved_prompt": "...",
  "reasoning": "Concise explanation of what you changed and why."
}}"""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": meta_prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if the model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw)
    return result["improved_prompt"], result["reasoning"], meta_prompt


def _compute_diff(old_content: str, new_content: str) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="original", tofile="improved")
    return "".join(diff)
