from pathlib import Path
import tempfile, textwrap
from cli.project import ProjectSpec, ProjectSpecError

tmp = Path(tempfile.mkdtemp())
(tmp / "prompt.txt").write_text("You are a helpful assistant.")
(tmp / "evals.yaml").write_text(textwrap.dedent("""
    tests:
      - id: basic_greeting
        input: "Hello!"
        expected: "Assistant should respond warmly"
        grader: semantic

      - id: exact_match
        input: "What is 2+2?"
        expected: "Should answer 4"
        grader: exact
        expected_output: "4"
"""))
(tmp / "config.yaml").write_text("model: claude-sonnet-4-6\ntemperature: 0.7")

spec = ProjectSpec.load(tmp)
print(f"model:  {spec.model}")
print(f"tests:  {len(spec.tests)}")
for t in spec.tests:
    print(f"  {t.id}  ->  eval_method={t.eval_method}")

spec.write_prompt("Updated prompt.")
assert ProjectSpec.load(tmp).prompt == "Updated prompt."
print("write_prompt: OK")
