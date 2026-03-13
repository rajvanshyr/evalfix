"""
Test sync.py in isolation — no API calls, no LLM.
Run with:  python test_sync.py
"""

import json
import tempfile
import textwrap
from pathlib import Path

# Bootstrap Flask app context (uses SQLite in-memory for this test)
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app import create_app
app = create_app()

from cli.project import ProjectSpec
from cli.sync import sync_project

EVALS = textwrap.dedent("""
    tests:
      - id: greeting
        input: "Hello!"
        expected: "Assistant should respond warmly"
        grader: semantic

      - id: exact_answer
        input: "What is 2+2?"
        expected: "Should answer 4"
        grader: exact
        expected_output: "4"

      - id: contains_word
        input: "Name a planet"
        expected: "Should mention Mars"
        grader: contains
        expected_output: "Mars"

      - id: regex_date
        input: "What year did WW2 end?"
        expected: "Should contain 1945"
        grader: regex
        expected_output: "194[45]"
""")


def make_project(tmp: Path, prompt_text: str = "You are a helpful assistant.") -> ProjectSpec:
    (tmp / "prompt.txt").write_text(prompt_text)
    (tmp / "evals.yaml").write_text(EVALS)
    (tmp / "config.yaml").write_text("model: claude-sonnet-4-6\ntemperature: 0.5\nmax_tokens: 512")
    return ProjectSpec.load(tmp)


with app.app_context():
    from app.extensions import db
    db.create_all()

    tmp = Path(tempfile.mkdtemp())

    # ── first sync ────────────────────────────────────────────────────────────
    spec   = make_project(tmp)
    result = sync_project(spec)

    assert result.project_id,              "missing project_id"
    assert result.prompt_id,               "missing prompt_id"
    assert result.version_id,              "missing version_id"
    assert len(result.test_case_ids) == 4, f"expected 4 test cases, got {len(result.test_case_ids)}"
    assert result.version_created,         "first sync should create a version"
    print("first sync          : OK")

    # ── DB records look right ─────────────────────────────────────────────────
    from app.models.project import Project
    from app.models.prompt import Prompt
    from app.models.prompt_version import PromptVersion
    from app.models.test_case import TestCase

    project = db.session.get(Project, result.project_id)
    assert project.name == tmp.name,       "project name mismatch"

    version = db.session.get(PromptVersion, result.version_id)
    assert version.content_type == "chat", "version should be chat type"
    assert version.model == "claude-sonnet-4-6"
    assert version.parameters["temperature"] == 0.5
    assert version.status == "active"

    messages = json.loads(version.content)
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."
    assert messages[1]["content"] == "{input}",  "user turn must have {input} placeholder"
    print("version content     : OK")

    # Check each test case's DB fields
    tcs = {tc.name: tc for tc in TestCase.query.filter_by(prompt_id=result.prompt_id).all()}

    assert tcs["greeting"].eval_method     == "llm_judge"
    assert tcs["greeting"].expected_output == "Assistant should respond warmly"
    assert tcs["greeting"].input_variables == {"input": "Hello!"}

    assert tcs["exact_answer"].eval_method     == "exact"
    assert tcs["exact_answer"].expected_output == "4"

    assert tcs["contains_word"].eval_method     == "contains"
    assert tcs["contains_word"].expected_output == "Mars"

    assert tcs["regex_date"].eval_method             == "regex"
    assert tcs["regex_date"].eval_config["pattern"]  == "194[45]"
    print("test case fields    : OK")

    # ── idempotency: same prompt → same version ───────────────────────────────
    result2 = sync_project(spec)
    assert result2.version_id == result.version_id,  "same prompt should reuse version"
    assert not result2.version_created,               "no new version when prompt unchanged"
    print("idempotent sync     : OK")

    # ── prompt change → new version ───────────────────────────────────────────
    spec.write_prompt("You are a concise assistant. Keep answers under 20 words.")
    result3 = sync_project(spec)
    assert result3.version_id != result.version_id, "changed prompt should mint new version"
    assert result3.version_created,                 "version_created should be True"

    old_version = db.session.get(PromptVersion, result.version_id)
    assert old_version.status == "archived",        "old version should be archived"

    new_version = db.session.get(PromptVersion, result3.version_id)
    assert new_version.version_number == 2
    assert new_version.status == "active"
    print("prompt change       : OK")

    # ── test case update ──────────────────────────────────────────────────────
    import yaml
    evals = yaml.safe_load((tmp / "evals.yaml").read_text())
    evals["tests"][0]["input"] = "Hi there, updated!"
    (tmp / "evals.yaml").write_text(yaml.dump(evals))

    spec4  = ProjectSpec.load(tmp)
    result4 = sync_project(spec4)

    tc_updated = db.session.get(TestCase, result4.test_case_ids[0])
    assert tc_updated.input_variables == {"input": "Hi there, updated!"}, "test case should update"
    print("test case update    : OK")

    # ── two different folders stay separate ───────────────────────────────────
    tmp_b = Path(tempfile.mkdtemp())
    spec_b = make_project(tmp_b, "You are a different assistant.")
    result_b = sync_project(spec_b)
    assert result_b.project_id != result.project_id, "different folders = different projects"
    print("project isolation   : OK")

    print("\nAll sync tests passed.")
