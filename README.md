# evalfix

**Shorten the time between red CI and green CI for LLM agents.**

evalfix is a CLI tool that runs evals against your prompt, identifies failures, and uses an AI optimizer to fix them — automatically.

---

## How it works

```
evalfix init     →  generate a starter eval suite from your prompt
evalfix run      →  run all evals, see pass/fail
evalfix fix      →  find what's failing, AI-generate a fix, apply it
evalfix report   →  view last run in the terminal or as HTML
evalfix history  →  see score trends across all runs
```

---

## Installation

**Prerequisites:** Python 3.11+, an [Anthropic API key](https://console.anthropic.com/)

```bash
git clone https://github.com/your-org/evalfix
cd evalfix
pip install -e .
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Quickstart

### 1. Create a project folder with your prompt

```bash
mkdir my-agent
echo "You are a helpful assistant that answers questions clearly and concisely." > my-agent/prompt.txt
```

### 2. Generate an eval suite

```bash
evalfix init my-agent/
```

This calls Claude to read your prompt and auto-generate `evals.yaml` — a set of test cases that check whether your prompt behaves as intended. It also creates `config.yaml` for model settings.

Your project folder will look like this:

```
my-agent/
├── prompt.txt      ← your system prompt
├── evals.yaml      ← test cases
└── config.yaml     ← model, temperature, max_tokens
```

### 3. Run evals

```bash
evalfix run my-agent/
```

```
Syncing my-agent...
Running 8 tests...

 Test                     Result   Score
 basic_greeting           ✓ pass   0.95
 respond_in_haiku         ✗ fail   0.20
 json_only_output         ✗ fail   0.10
 ...

 5 passed  3 failed  avg score 0.61
```

Exits with code `1` if any tests fail — safe to use in CI.

### 4. Fix failures automatically

```bash
evalfix fix my-agent/
```

evalfix runs a multi-agent loop (up to 3 iterations):
1. **Root cause agent** — diagnoses *why* the prompt is failing
2. **Fix generator** — writes a minimal targeted patch
3. **Regression screener** — quickly checks the fix won't break passing tests
4. **Eval run** — validates the fix against all test cases

At the end it shows you a diff and asks to accept:

```
✓ Fixed in 2 iterations

  Prompt diff:
  - You are a helpful assistant that answers questions clearly and concisely.
  + You are a helpful assistant. When asked for structured output (JSON, haiku,
  + numbered lists), follow the format exactly. Otherwise answer clearly and concisely.

  Accept this change? [y/N]
```

Type `y` to write the improved prompt back to `prompt.txt`. Use `--yes` to skip the prompt in CI.

---

## Eval suite format

`evals.yaml` — one entry per test case:

```yaml
tests:
  - id: json_only_output
    input: "Give me a fun fact about penguins"
    expected: "Must respond with ONLY a JSON object like {\"fact\": \"...\"} and nothing else"
    grader: semantic

  - id: capital_city
    input: "What is the capital of France?"
    expected: "Should say Paris"
    grader: contains
    expected_output: "Paris"

  - id: numbered_steps
    input: "Walk me through making coffee"
    expected: "Must use numbered steps"
    grader: regex
    expected_output: "1\\."

  - id: exact_match
    input: "Reply with the word OK and nothing else"
    expected: "OK"
    grader: exact
    expected_output: "OK"
```

**Graders:**

| Grader | How it works |
|--------|-------------|
| `semantic` | Claude judges whether the output satisfies the `expected` description |
| `contains` | Checks that `expected_output` appears anywhere in the response |
| `exact` | Response must exactly match `expected_output` |
| `regex` | Response must match the regex in `expected_output` |

`config.yaml` — model settings:

```yaml
model: claude-haiku-4-5-20251001
temperature: 1.0
max_tokens: 256
```

---

## All commands

```bash
# Generate eval suite from prompt.txt
evalfix init my-agent/

# Run evals (exits 1 if any fail)
evalfix run my-agent/

# Run evals and auto-fix failures
evalfix fix my-agent/

# Auto-accept the fix without prompting
evalfix fix my-agent/ --yes

# Override model for a single run
evalfix run my-agent/ --model claude-opus-4-6

# Print results as JSON (for piping / CI)
evalfix run my-agent/ --json

# Show last run results in terminal
evalfix report my-agent/

# Generate HTML report
evalfix report my-agent/ --html

# Show score history across all runs
evalfix history my-agent/

# Show only last 10 runs
evalfix history my-agent/ --last 10

# Generate HTML score chart
evalfix history my-agent/ --html
```

---

## CI integration

```yaml
# .github/workflows/eval.yml
- name: Run evals
  run: evalfix run my-agent/
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

evalfix exits `0` if all tests pass, `1` if any fail.

---

## evalfix-sdk

If your LLM is in production, you can capture real failures and automatically add them to your eval suite.

**Install:**

```bash
pip install evalfix-sdk
```

**Usage — drop this anywhere you detect a bad response:**

```python
from evalfix_sdk import capture

response = my_llm_call(user_input)

if quality_score < 0.7:
    capture(
        input=user_input,
        output=response,
        expected="What the response should have said",  # optional
        score=quality_score,                            # optional, 0–1
        tags=["production", "customer-facing"],         # optional
        metadata={"user_id": user_id},                  # optional
    )
```

`capture()` is safe to call in hot paths — it **never raises an exception** and **returns immediately** (writes happen on a background thread).

Failures are written to `.evalfix/failures.jsonl` in your project directory.

**Ingesting failures:**

The next time you run `evalfix run` or `evalfix fix`, evalfix automatically picks up the captured failures and adds them as test cases before running evals:

```bash
evalfix fix my-agent/
# Ingested 3 production failures from evalfix-sdk.
# Running 11 tests...
```

**Pointing the SDK at your project directory:**

By default the SDK auto-detects the nearest `.evalfix/` folder. You can also configure it explicitly:

```python
import evalfix_sdk

evalfix_sdk.configure(
    queue_file="/path/to/my-agent/.evalfix/failures.jsonl"
)
```

Or via environment variable:

```bash
EVALFIX_QUEUE_FILE=/path/to/my-agent/.evalfix/failures.jsonl
```

**Full configure options:**

```python
evalfix_sdk.configure(
    backend="file",      # "file" (default) or "http"
    queue_file="...",    # path to failures.jsonl
    enabled=True,        # set False to disable in tests
    # HTTP backend (optional):
    api_url="https://...",
    api_key="...",
)
```

---

## Project structure

```
evalfix/
├── app/                    ← Flask app (DB models, evaluator, optimizer)
│   ├── models/
│   ├── services/
│   │   ├── evaluator.py
│   │   ├── multi_agent_optimizer.py
│   │   └── agents/         ← root_cause, fix_generator, regression_screener
│   └── templates/
├── cli/                    ← CLI layer
│   ├── main.py             ← Click entry point
│   ├── project.py          ← ProjectSpec (reads prompt.txt, evals.yaml, config.yaml)
│   ├── sync.py             ← bridges folder → DB records
│   ├── output.py           ← Rich terminal formatting
│   └── commands/           ← init, run, fix, report, history
├── evalfix-sdk/            ← separate pip package
│   └── evalfix_sdk/
├── .env                    ← ANTHROPIC_API_KEY (never committed)
└── setup.py
```
