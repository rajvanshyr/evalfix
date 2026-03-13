from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so config.py is importable.
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cli.output import console, print_error, print_success


def run(directory: str, model_override: str | None, auto_accept: bool) -> None:
    from cli.project import ProjectSpec, ProjectSpecError

    try:
        spec = ProjectSpec.load(directory)
    except ProjectSpecError as e:
        print_error(str(e))
        sys.exit(1)

    if model_override:
        spec.config["model"] = model_override

    from app import create_app
    app = create_app()

    with app.app_context():
        from app.extensions import db
        from app.models.test_run import TestRun
        from app.models.test_result import TestResult
        from app.models.test_case import TestCase
        from app.models.prompt_version import PromptVersion
        from app.models.optimization_run import OptimizationRun
        from app.models.failure import Failure
        from app.services.evaluator import run_test_run
        from app.services.optimizer import run_optimization
        from cli.sync import sync_project
        from cli.output import print_run_summary, print_diff, print_fix_summary

        # ── 1. Sync folder → DB ───────────────────────────────────────────────
        console.print(f"[dim]Syncing {spec.name}...[/dim]")
        sync_result = sync_project(spec)

        # ── 2. Run evals ──────────────────────────────────────────────────────
        console.print(
            f"[dim]Running {len(sync_result.test_case_ids)} test"
            f"{'s' if len(sync_result.test_case_ids) != 1 else ''}...[/dim]"
        )

        test_run = TestRun(
            prompt_version_id=sync_result.version_id,
            triggered_by="cli",
        )
        db.session.add(test_run)
        db.session.commit()

        try:
            run_test_run(test_run.id)
        except Exception as e:
            print_error(f"Evaluator failed: {e}")
            sys.exit(1)

        db.session.refresh(test_run)

        results = TestResult.query.filter_by(test_run_id=test_run.id).all()
        test_cases_by_id = {
            tc.id: tc
            for tc in TestCase.query.filter_by(prompt_id=sync_result.prompt_id).all()
        }
        result_rows = [
            (r, test_cases_by_id[r.test_case_id])
            for r in results
            if r.test_case_id in test_cases_by_id
        ]

        print_run_summary(spec, sync_result, test_run, result_rows)

        # ── 3. Nothing to fix? ────────────────────────────────────────────────
        if test_run.fail_count == 0:
            print_success("All tests passing — nothing to fix.")
            return

        # ── 4. Build failure records from failed test results ─────────────────
        # The optimizer expects Failure DB records, so we create transient ones
        # from the TestResult rows that didn't pass.
        failed_rows = [(r, tc) for r, tc in result_rows if not r.passed]
        console.print(
            f"[dim]Creating {len(failed_rows)} failure record"
            f"{'s' if len(failed_rows) != 1 else ''} for the optimizer...[/dim]"
        )

        failure_ids: list[str] = []
        for result, tc in failed_rows:
            failure = Failure(
                prompt_id=sync_result.prompt_id,
                input_variables=tc.input_variables,
                expected_output=tc.expected_output,
                actual_output=result.actual_output or "",
                failure_reason=result.judge_reasoning or result.error or "eval failed",
                source="cli",
            )
            db.session.add(failure)
            db.session.flush()
            failure_ids.append(failure.id)

        db.session.commit()

        # ── 5. Run optimizer ──────────────────────────────────────────────────
        console.print("[dim]Running AI optimizer...[/dim]")

        opt_run = OptimizationRun(
            prompt_id=sync_result.prompt_id,
            base_version_id=sync_result.version_id,
            failure_ids=failure_ids,
            test_case_ids=sync_result.test_case_ids,
            optimizer_model=spec.model,
        )
        db.session.add(opt_run)
        db.session.commit()

        try:
            run_optimization(opt_run.id)
        except Exception as e:
            print_error(f"Optimizer failed: {e}")
            sys.exit(1)

        db.session.refresh(opt_run)

        if opt_run.status == "failed":
            print_error(f"Optimizer returned an error: {opt_run.error}")
            sys.exit(1)

        # ── 6. Show diff ──────────────────────────────────────────────────────
        base_version   = db.session.get(PromptVersion, sync_result.version_id)
        result_version = db.session.get(PromptVersion, opt_run.result_version_id)

        old_prompt = _extract_system_prompt(base_version)
        new_prompt = _extract_system_prompt(result_version)

        print_diff(opt_run, old_prompt, new_prompt)

        # ── 7. Accept / reject ────────────────────────────────────────────────
        if auto_accept:
            accept = True
        else:
            try:
                answer = input("Accept this change? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            accept = answer in ("y", "yes")

        if not accept:
            console.print("[dim]Change discarded. prompt.txt unchanged.[/dim]\n")
            return

        # ── 8. Write new prompt + re-run evals ───────────────────────────────
        spec.write_prompt(new_prompt)
        print_success(f"prompt.txt updated.")

        # Mark the result version as active
        result_version.status = "active"
        if base_version:
            base_version.status = "archived"
        from app.models.prompt import Prompt
        prompt = db.session.get(Prompt, sync_result.prompt_id)
        if prompt:
            prompt.current_version_id = result_version.id
        db.session.commit()

        # Re-run to show the before/after comparison
        console.print("[dim]Re-running evals on improved prompt...[/dim]")

        sync_result2 = sync_project(spec)
        test_run2 = TestRun(
            prompt_version_id=sync_result2.version_id,
            triggered_by="cli",
            optimization_run_id=opt_run.id,
        )
        db.session.add(test_run2)
        db.session.commit()

        try:
            run_test_run(test_run2.id)
        except Exception as e:
            print_error(f"Re-run failed: {e}")
            sys.exit(1)

        db.session.refresh(test_run2)

        results2 = TestResult.query.filter_by(test_run_id=test_run2.id).all()
        result_rows2 = [
            (r, test_cases_by_id[r.test_case_id])
            for r in results2
            if r.test_case_id in test_cases_by_id
        ]

        print_run_summary(spec, sync_result2, test_run2, result_rows2)
        print_fix_summary(
            before_score=test_run.avg_score,
            after_score=test_run2.avg_score,
            before_fails=test_run.fail_count,
            after_fails=test_run2.fail_count,
        )

        # Persist state
        from cli.commands.run import _write_state
        _write_state(directory, test_run2, sync_result2)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extract_system_prompt(version: "PromptVersion") -> str:
    """Pull the system message text out of a chat-format PromptVersion."""
    if version.content_type == "chat":
        try:
            messages = json.loads(version.content)
            for msg in messages:
                if msg.get("role") == "system":
                    return msg["content"]
        except (json.JSONDecodeError, KeyError):
            pass
    return version.content
