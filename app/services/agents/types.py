"""
Shared dataclasses for the multi-agent optimizer.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RootCauseReport:
    failure_patterns: list[str]   # patterns observed across failures
    prompt_issues: list[str]      # what in the prompt causes them
    confidence: float             # 0–1
    reasoning: str                # full explanation


@dataclass
class CandidateFix:
    improved_prompt: str              # new system prompt text
    changes_summary: str              # one-line: what changed and why
    predicted_regressions: list[str]  # test IDs likely to break
    reasoning: str


@dataclass
class RegressionScreen:
    likely_regressions: list[str]  # test IDs at risk
    confidence: float              # 0–1


@dataclass
class IterationResult:
    iteration: int
    root_cause: RootCauseReport
    candidate_fix: CandidateFix
    passed: bool
    pass_count: int
    fail_count: int
    avg_score: float | None
    remaining_failures: list       # (TestResult, TestCase) still failing
    screened_out: bool = False     # True if regression screener blocked eval


@dataclass
class MultiAgentResult:
    success: bool
    iterations: int
    final_prompt: str | None       # None if all iterations failed
    original_prompt: str
    history: list[IterationResult] = field(default_factory=list)
    diff: str = ""
