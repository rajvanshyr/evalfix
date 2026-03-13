from flask import Blueprint, render_template, request, abort
from ..extensions import db
from ..models.project import Project
from ..models.prompt import Prompt

bp = Blueprint("ui_projects", __name__)


@bp.route("/")
def index():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    projects_with_counts = []
    for project in projects:
        prompt_count = Prompt.query.filter_by(project_id=project.id).count()
        projects_with_counts.append({
            "project": project,
            "prompt_count": prompt_count,
        })
    return render_template("projects/index.html", projects_with_counts=projects_with_counts)


@bp.route("/projects/<project_id>")
def detail(project_id):
    project = Project.query.get_or_404(project_id)
    prompts = Prompt.query.filter_by(project_id=project_id).order_by(Prompt.created_at.desc()).all()

    from ..models.prompt_version import PromptVersion
    from ..models.failure import Failure
    from ..models.test_case import TestCase

    prompts_with_counts = []
    for prompt in prompts:
        version_count = PromptVersion.query.filter_by(prompt_id=prompt.id).count()
        failure_count = Failure.query.filter_by(prompt_id=prompt.id).count()
        test_case_count = TestCase.query.filter_by(prompt_id=prompt.id).count()
        prompts_with_counts.append({
            "prompt": prompt,
            "version_count": version_count,
            "failure_count": failure_count,
            "test_case_count": test_case_count,
        })

    return render_template("projects/detail.html", project=project, prompts_with_counts=prompts_with_counts)


@bp.route("/projects", methods=["POST"])
def create_project():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        abort(400, "name is required")

    project = Project(name=name, description=description or None)
    db.session.add(project)
    db.session.commit()

    prompt_count = 0
    return render_template("projects/_card.html", project=project, prompt_count=prompt_count)


@bp.route("/projects/<project_id>/prompts", methods=["POST"])
def create_prompt(project_id):
    project = Project.query.get_or_404(project_id)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        abort(400, "name is required")

    from ..models.prompt import Prompt
    prompt = Prompt(
        project_id=project_id,
        name=name,
        description=description or None,
    )
    db.session.add(prompt)
    db.session.commit()

    from ..models.prompt_version import PromptVersion
    from ..models.failure import Failure
    from ..models.test_case import TestCase

    version_count = 0
    failure_count = 0
    test_case_count = 0

    return render_template(
        "projects/_prompt_row.html",
        prompt=prompt,
        version_count=version_count,
        failure_count=failure_count,
        test_case_count=test_case_count,
    )
