"""
Parses a source file and extracts prompt-like string variables as Prompt objects.
Currently supports Python files. Extend _parse_* functions for other languages.
"""
import re
from datetime import datetime

from ..extensions import db
from ..models.prompt import Prompt
from ..models.prompt_version import PromptVersion
from ..models.prompt_file import PromptFile


def parse_prompt_file(prompt_file_id: str) -> list[dict]:
    """
    Parse a PromptFile's raw_content, create/update Prompt + PromptVersion
    records for each detected prompt, and return a summary list.
    """
    pf = PromptFile.query.get(prompt_file_id)
    if not pf or not pf.raw_content:
        return []

    if pf.language == "python":
        extracted = _parse_python(pf.raw_content)
    else:
        # Fallback: treat entire content as a single prompt
        extracted = [{"name": pf.file_path.split("/")[-1], "content": pf.raw_content, "content_type": "text"}]

    created = []
    for item in extracted:
        # Check if a prompt with this name already exists in the project
        existing = Prompt.query.filter_by(
            project_id=pf.project_id,
            name=item["name"],
        ).first()

        if existing:
            prompt = existing
        else:
            prompt = Prompt(
                project_id=pf.project_id,
                prompt_file_id=pf.id,
                name=item["name"],
            )
            db.session.add(prompt)
            db.session.flush()

        # Determine the next version number
        latest = (
            PromptVersion.query
            .filter_by(prompt_id=prompt.id)
            .order_by(PromptVersion.version_number.desc())
            .first()
        )

        # Skip if the content hasn't changed
        if latest and latest.content == item["content"]:
            created.append({"prompt_id": prompt.id, "name": prompt.name, "action": "unchanged"})
            continue

        next_num = (latest.version_number + 1) if latest else 1
        version = PromptVersion(
            prompt_id=prompt.id,
            version_number=next_num,
            content_type=item.get("content_type", "text"),
            content=item["content"],
            parent_version_id=latest.id if latest else None,
            source="file_import",
            status="active",
        )
        db.session.add(version)
        db.session.flush()

        prompt.current_version_id = version.id
        created.append({"prompt_id": prompt.id, "name": prompt.name, "action": "created" if not latest else "updated"})

    pf.last_parsed_at = datetime.utcnow()
    db.session.commit()
    return created


# ---------------------------------------------------------------------------
# Language-specific parsers
# ---------------------------------------------------------------------------

# Matches: VARIABLE_NAME = """..."""  or  VARIABLE_NAME = '''...'''  or  VARIABLE_NAME = "..."
_PYTHON_MULTILINE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)\s*=\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')',
    re.DOTALL | re.MULTILINE,
)
_PYTHON_SINGLE = re.compile(
    r'^([A-Z_][A-Z0-9_]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')$',
    re.MULTILINE,
)

# Heuristic: consider a string a "prompt" if it's long enough or contains {variables}
_MIN_PROMPT_LENGTH = 30
_HAS_PLACEHOLDER = re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}')


def _looks_like_prompt(text: str) -> bool:
    return len(text.strip()) >= _MIN_PROMPT_LENGTH or bool(_HAS_PLACEHOLDER.search(text))


def _parse_python(source: str) -> list[dict]:
    results = []
    seen = set()

    for match in _PYTHON_MULTILINE.finditer(source):
        name = match.group(1)
        content = (match.group(2) or match.group(3) or "").strip()
        if name not in seen and _looks_like_prompt(content):
            results.append({"name": name, "content": content, "content_type": "text"})
            seen.add(name)

    for match in _PYTHON_SINGLE.finditer(source):
        name = match.group(1)
        content = (match.group(2) or match.group(3) or "").strip()
        if name not in seen and _looks_like_prompt(content):
            results.append({"name": name, "content": content, "content_type": "text"})
            seen.add(name)

    return results
