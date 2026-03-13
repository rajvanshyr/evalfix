"""
Executes a TestRun: renders each TestCase against a PromptVersion, calls the
LLM, evaluates the output, and persists TestResult rows.
"""
import json
import re
import time
from datetime import datetime

import anthropic
from flask import current_app

from ..extensions import db
from ..models.test_run import TestRun
from ..models.test_result import TestResult
from ..models.prompt_version import PromptVersion
from ..models.test_case import TestCase


def run_test_run(test_run_id: str):
    """Execute a test run synchronously. Called from the route."""
    test_run = TestRun.query.get(test_run_id)
    if not test_run:
        return

    test_run.status = "running"
    test_run.started_at = datetime.utcnow()
    db.session.commit()

    try:
        version = PromptVersion.query.get(test_run.prompt_version_id)
        # Run all test cases for this prompt
        test_cases = TestCase.query.filter_by(prompt_id=version.prompt_id).all()

        results = []
        for tc in test_cases:
            result = _run_single_test(version, tc, test_run.id)
            results.append(result)
            db.session.add(result)

        db.session.flush()

        # Summarize
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        scores = [r.score for r in results if r.score is not None]
        avg_score = sum(scores) / len(scores) if scores else None

        test_run.total_count = total
        test_run.pass_count = passed
        test_run.fail_count = total - passed
        test_run.avg_score = avg_score
        test_run.status = "completed"
        test_run.completed_at = datetime.utcnow()
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        test_run.status = "failed"
        test_run.completed_at = datetime.utcnow()
        db.session.commit()
        raise


def _run_single_test(version: PromptVersion, tc: TestCase, test_run_id: str) -> TestResult:
    result = TestResult(test_run_id=test_run_id, test_case_id=tc.id)
    try:
        start = time.time()
        actual_output, tokens_used = _call_llm(version, tc.input_variables or {})
        result.latency_ms = int((time.time() - start) * 1000)
        result.tokens_used = tokens_used
        result.actual_output = actual_output

        passed, score, judge_reasoning = _evaluate(tc, actual_output)
        result.passed = passed
        result.score = score
        result.judge_reasoning = judge_reasoning

    except Exception as e:
        result.passed = False
        result.score = 0.0
        result.error = str(e)

    return result


def _call_llm(version: PromptVersion, variables: dict):
    """Render the prompt with variables and call the configured model."""
    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
    model = version.model or "claude-haiku-4-5-20251001"
    params = version.parameters or {}

    if version.content_type == "chat":
        messages_template = json.loads(version.content)
        # Render {variables} in each message's content
        messages = []
        system = None
        for msg in messages_template:
            rendered_content = msg["content"].format(**variables)
            if msg["role"] == "system":
                system = rendered_content
            else:
                messages.append({"role": msg["role"], "content": rendered_content})

        kwargs = dict(
            model=model,
            max_tokens=params.get("max_tokens", 1024),
            messages=messages,
            **{k: v for k, v in params.items() if k not in ("max_tokens",)},
        )
        if system:
            kwargs["system"] = system
    else:
        rendered = version.content.format(**variables)
        kwargs = dict(
            model=model,
            max_tokens=params.get("max_tokens", 1024),
            messages=[{"role": "user", "content": rendered}],
            **{k: v for k, v in params.items() if k not in ("max_tokens",)},
        )

    response = client.messages.create(**kwargs)
    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return text, tokens


def _evaluate(tc: TestCase, actual_output: str):
    """Return (passed, score, judge_reasoning)."""
    method = tc.eval_method or "contains"
    expected = tc.expected_output or ""
    config = tc.eval_config or {}

    if method == "exact":
        passed = actual_output.strip() == expected.strip()
        return passed, 1.0 if passed else 0.0, None

    elif method == "contains":
        passed = expected.lower() in actual_output.lower()
        return passed, 1.0 if passed else 0.0, None

    elif method == "regex":
        pattern = config.get("pattern", expected)
        passed = bool(re.search(pattern, actual_output))
        return passed, 1.0 if passed else 0.0, None

    elif method == "llm_judge":
        return _llm_judge(actual_output, expected, config)

    return False, 0.0, None


def _llm_judge(actual_output: str, expected_output: str, config: dict):
    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
    judge_prompt = config.get(
        "judge_prompt",
        "Does the actual output correctly answer or match the expected output? "
        "Be strict but fair.",
    )

    prompt = f"""{judge_prompt}

Expected: {expected_output}
Actual:   {actual_output}

Respond with valid JSON only:
{{"passed": true/false, "score": 0.0-1.0, "reasoning": "brief explanation"}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw)
    return result["passed"], result.get("score", 1.0 if result["passed"] else 0.0), result.get("reasoning")
