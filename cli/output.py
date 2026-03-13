"""
cli/output.py

All terminal formatting lives here.  Nothing else should print directly.
"""

from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Run summary — main output for `evalfix run`
# ---------------------------------------------------------------------------

def print_run_summary(spec, sync_result, test_run, result_rows, as_json: bool = False):
    """Print the full run result.

    result_rows: list of (TestResult, TestCase) tuples, one per test.
    """
    if as_json:
        _print_json(test_run, result_rows)
        return

    _print_header(spec, sync_result, test_run)
    _print_table(result_rows)
    _print_footer(test_run)


# ---------------------------------------------------------------------------
# Individual sections
# ---------------------------------------------------------------------------

def _print_header(spec, sync_result, test_run):
    from app.models.prompt_version import PromptVersion
    from app.extensions import db
    version = db.session.get(PromptVersion, sync_result.version_id)
    v_num   = version.version_number if version else "?"

    all_pass = test_run.fail_count == 0
    status   = "[bold green]✓ PASSED[/bold green]" if all_pass else "[bold red]✗ FAILED[/bold red]"
    score    = f"{test_run.avg_score:.2f}" if test_run.avg_score is not None else "—"

    elapsed = ""
    if test_run.started_at and test_run.completed_at:
        secs = (test_run.completed_at - test_run.started_at).total_seconds()
        elapsed = f"  ·  {secs:.1f}s"

    title = (
        f"[bold]{spec.name}[/bold]  ·  v{v_num}  ·  "
        f"[dim]{spec.model}[/dim]{elapsed}"
    )
    subtitle = (
        f"{status}  "
        f"[green]{test_run.pass_count} passed[/green]  ·  "
        f"[red]{test_run.fail_count} failed[/red]  ·  "
        f"avg score [bold]{score}[/bold]"
    )

    console.print()
    console.print(Panel(f"{title}\n{subtitle}", box=box.ROUNDED, padding=(0, 1)))


def _print_table(result_rows):
    table = Table(
        box=box.SIMPLE_HEAD,
        show_edge=False,
        pad_edge=False,
        header_style="dim",
    )

    table.add_column("Test",     style="bold",       max_width=22, no_wrap=True)
    table.add_column("Input",    style="dim",         max_width=30, no_wrap=True)
    table.add_column("Expected", style="dim",         max_width=30, no_wrap=True)
    table.add_column("Result",   justify="center",    min_width=8)
    table.add_column("Score",    justify="right",     min_width=5)
    table.add_column("Latency",  justify="right",     min_width=7, style="dim")

    for result, tc in result_rows:
        passed  = result.passed
        score   = result.score

        result_cell  = "[green]✓ pass[/green]" if passed else "[red]✗ FAIL[/red]"
        score_cell   = (
            f"[green]{score:.2f}[/green]" if passed
            else f"[red]{score:.2f}[/red]"
        ) if score is not None else "—"
        latency_cell = f"{result.latency_ms}ms" if result.latency_ms else "—"

        input_text    = _truncate(tc.input_variables.get("input", "") if tc.input_variables else "", 28)
        expected_text = _truncate(tc.expected_output or tc.description or "", 28)

        table.add_row(
            tc.name or tc.id,
            input_text,
            expected_text,
            result_cell,
            score_cell,
            latency_cell,
        )

        # If failed, show actual output underneath as a dim sub-row
        if not passed and result.actual_output:
            actual = _truncate(result.actual_output, 80)
            table.add_row("", f"[dim]got: {actual}[/dim]", "", "", "", "")

        if not passed and result.judge_reasoning:
            table.add_row("", f"[dim italic]{result.judge_reasoning}[/dim italic]", "", "", "", "")

        if not passed and result.error:
            table.add_row("", f"[red]error: {result.error}[/red]", "", "", "", "")

    console.print(table)


def _print_footer(test_run):
    if test_run.fail_count > 0:
        console.print(
            f"  [dim]Run [bold]evalfix fix[/bold] to generate an AI-powered patch.[/dim]\n"
        )
    else:
        console.print()


# ---------------------------------------------------------------------------
# JSON output (for --json / CI piping)
# ---------------------------------------------------------------------------

def _print_json(test_run, result_rows):
    output = {
        "status":      test_run.status,
        "pass_count":  test_run.pass_count,
        "fail_count":  test_run.fail_count,
        "total_count": test_run.total_count,
        "avg_score":   test_run.avg_score,
        "results": [
            {
                "test_id":        tc.name,
                "input":          tc.input_variables.get("input", "") if tc.input_variables else "",
                "expected":       tc.expected_output or "",
                "actual":         result.actual_output or "",
                "passed":         result.passed,
                "score":          result.score,
                "latency_ms":     result.latency_ms,
                "judge_reasoning": result.judge_reasoning,
                "error":          result.error,
            }
            for result, tc in result_rows
        ],
    }
    console.print_json(json.dumps(output))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def print_diff(opt_run, old_prompt: str, new_prompt: str) -> None:
    """Print the optimizer's reasoning and a coloured prompt diff."""
    if opt_run.reasoning:
        console.print()
        console.print(Panel(
            f"[dim]Reasoning[/dim]\n{opt_run.reasoning}",
            box=box.ROUNDED,
            padding=(0, 1),
        ))

    console.print()
    console.print("[dim]Prompt diff[/dim]")
    console.print()

    old_lines = old_prompt.splitlines()
    new_lines = new_prompt.splitlines()

    import difflib
    diff = list(difflib.unified_diff(old_lines, new_lines,
                                     fromfile="current", tofile="improved",
                                     lineterm=""))

    if not diff:
        console.print("[dim]  (no textual changes)[/dim]")
        return

    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[dim]{line}[/dim]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]")
        else:
            console.print(f"[dim]{line}[/dim]")

    console.print()


def print_fix_summary(before_score: float | None, after_score: float | None,
                      before_fails: int, after_fails: int) -> None:
    b = f"{before_score:.2f}" if before_score is not None else "—"
    a = f"{after_score:.2f}" if after_score is not None else "—"

    improved = (after_score or 0) > (before_score or 0)
    arrow    = "[green]↑[/green]" if improved else "[red]↓[/red]"

    console.print(Panel(
        f"Score  [red]{b}[/red]  {arrow}  [green]{a}[/green]    "
        f"Failures  [red]{before_fails}[/red]  →  "
        f"[green]{after_fails}[/green]",
        box=box.ROUNDED,
        padding=(0, 1),
        title="[bold]Result[/bold]",
    ))
    console.print()


def print_iteration_header(i: int, total: int) -> None:
    console.print(f"\n[bold][dim]── Iteration {i}/{total} ──────────────────────────[/dim][/bold]")


def print_root_cause(root_cause) -> None:
    lines = []
    if root_cause.failure_patterns:
        lines.append("[dim]Failure patterns[/dim]")
        for p in root_cause.failure_patterns:
            lines.append(f"  [yellow]·[/yellow] {p}")
    if root_cause.prompt_issues:
        lines.append("[dim]Prompt issues[/dim]")
        for p in root_cause.prompt_issues:
            lines.append(f"  [red]·[/red] {p}")
    confidence_color = "green" if root_cause.confidence >= 0.7 else "yellow"
    lines.append(f"\n[dim]Confidence[/dim]  [{confidence_color}]{root_cause.confidence:.0%}[/{confidence_color}]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Root cause[/bold]",
        box=box.ROUNDED,
        padding=(0, 1),
    ))


def print_multi_agent_failure(result) -> None:
    """Show a summary when all iterations are exhausted without success."""
    console.print()
    console.print(Panel(
        f"[red]Could not auto-fix after {result.iterations} iteration"
        f"{'s' if result.iterations != 1 else ''}.[/red]\n\n"
        "The root cause analysis below may help you fix it manually.",
        box=box.ROUNDED,
        padding=(0, 1),
    ))

    for it in result.history:
        console.print(f"\n[dim]Iteration {it.iteration}[/dim]")
        console.print(f"  Fix attempted: [dim]{it.candidate_fix.changes_summary}[/dim]")
        if it.screened_out:
            console.print("  [yellow]⚠ Blocked by regression screener before eval[/yellow]")
        else:
            score = f"{it.avg_score:.2f}" if it.avg_score is not None else "—"
            console.print(
                f"  Result: [green]{it.pass_count} passed[/green]  "
                f"[red]{it.fail_count} failed[/red]  score {score}"
            )

    # Show root cause from the last iteration
    if result.history:
        last_rc = result.history[-1].root_cause
        console.print()
        print_root_cause(last_rc)


def print_error(message: str):
    console.print(f"\n[bold red]Error:[/bold red] {message}\n")


def print_info(message: str):
    console.print(f"[dim]{message}[/dim]")


def print_success(message: str):
    console.print(f"[bold green]✓[/bold green] {message}")
