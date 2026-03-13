import json
from flask import Blueprint, render_template, request, abort, make_response
from ..extensions import db
from ..models.prompt import Prompt
from ..models.prompt_version import PromptVersion
from ..models.failure import Failure
from ..models.test_case import TestCase
from ..models.optimization_run import OptimizationRun

bp = Blueprint("ui_prompts", __name__)


def parse_diff(diff_str):
    if not diff_str:
        return []
    lines = []
    for line in diff_str.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            lines.append({'type': 'file_header', 'content': line})
        elif line.startswith('+'):
            lines.append({'type': 'add', 'content': line[1:]})
        elif line.startswith('-'):
            lines.append({'type': 'remove', 'content': line[1:]})
        elif line.startswith('@@'):
            lines.append({'type': 'hunk_header', 'content': line})
        elif line.startswith('\\'):
            pass
        else:
            lines.append({'type': 'context', 'content': line})
    return lines


@bp.route("/prompts/<prompt_id>")
def detail(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    project = prompt.project

    current_version = None
    if prompt.current_version_id:
        current_version = PromptVersion.query.get(prompt.current_version_id)

    versions = (
        PromptVersion.query
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .all()
    )

    failures = (
        Failure.query
        .filter_by(prompt_id=prompt_id)
        .order_by(Failure.created_at.desc())
        .all()
    )

    test_cases = (
        TestCase.query
        .filter_by(prompt_id=prompt_id)
        .order_by(TestCase.created_at.desc())
        .all()
    )

    optimizations = (
        OptimizationRun.query
        .filter_by(prompt_id=prompt_id)
        .order_by(OptimizationRun.created_at.desc())
        .all()
    )

    result_versions = {}
    for opt_run in optimizations:
        if opt_run.result_version_id:
            rv = PromptVersion.query.get(opt_run.result_version_id)
            if rv:
                result_versions[opt_run.id] = rv

    diff_data = {}
    for opt_run in optimizations:
        diff_data[opt_run.id] = parse_diff(opt_run.diff)

    return render_template(
        "prompts/detail.html",
        prompt=prompt,
        project=project,
        current_version=current_version,
        versions=versions,
        failures=failures,
        test_cases=test_cases,
        optimizations=optimizations,
        result_versions=result_versions,
        diff_data=diff_data,
    )


@bp.route("/prompts/<prompt_id>/versions", methods=["POST"])
def create_version(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)

    content = request.form.get("content", "").strip()
    if not content:
        abort(400, "content is required")

    content_type = request.form.get("content_type", "text")
    model = request.form.get("model", "").strip() or None
    parameters_raw = request.form.get("parameters", "").strip()
    parameters = None
    if parameters_raw:
        try:
            parameters = json.loads(parameters_raw)
        except json.JSONDecodeError:
            parameters = None

    latest = (
        PromptVersion.query
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .first()
    )
    next_num = (latest.version_number + 1) if latest else 1

    version = PromptVersion(
        prompt_id=prompt_id,
        version_number=next_num,
        content_type=content_type,
        content=content,
        model=model,
        parameters=parameters,
        parent_version_id=latest.id if latest else None,
        source="manual",
        status="active",
    )
    db.session.add(version)
    db.session.flush()

    if not prompt.current_version_id or version.status == "active":
        prompt.current_version_id = version.id

    db.session.commit()

    is_current = (prompt.current_version_id == version.id)
    return render_template("versions/_card.html", version=version, is_current=is_current)


@bp.route("/prompts/<prompt_id>/failures", methods=["POST"])
def create_failure(prompt_id):
    Prompt.query.get_or_404(prompt_id)

    actual_output = request.form.get("actual_output", "").strip()
    if not actual_output:
        abort(400, "actual_output is required")

    input_variables_raw = request.form.get("input_variables", "").strip()
    input_variables = None
    if input_variables_raw:
        try:
            input_variables = json.loads(input_variables_raw)
        except json.JSONDecodeError:
            input_variables = None

    failure = Failure(
        prompt_id=prompt_id,
        actual_output=actual_output,
        expected_output=request.form.get("expected_output", "").strip() or None,
        failure_reason=request.form.get("failure_reason", "").strip() or None,
        failure_category=request.form.get("failure_category") or None,
        input_variables=input_variables,
        source="ui",
    )
    db.session.add(failure)
    db.session.commit()

    return render_template("failures/_card.html", failure=failure)


@bp.route("/prompts/<prompt_id>/test-cases", methods=["POST"])
def create_test_case(prompt_id):
    Prompt.query.get_or_404(prompt_id)

    input_variables_raw = request.form.get("input_variables", "").strip()
    input_variables = None
    if input_variables_raw:
        try:
            input_variables = json.loads(input_variables_raw)
        except json.JSONDecodeError:
            input_variables = None

    tc = TestCase(
        prompt_id=prompt_id,
        name=request.form.get("name", "").strip() or None,
        input_variables=input_variables,
        expected_output=request.form.get("expected_output", "").strip() or None,
        eval_method=request.form.get("eval_method", "contains"),
        source="manual",
    )
    db.session.add(tc)
    db.session.commit()

    return render_template("test_cases/_card.html", tc=tc)


@bp.route("/prompts/<prompt_id>/optimizations", methods=["POST"])
def create_optimization(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)

    if not prompt.current_version_id:
        abort(400, "prompt has no current version — create one first")

    failure_ids = request.form.getlist("failure_ids")
    test_case_ids = request.form.getlist("test_case_ids")
    optimizer_model = request.form.get("optimizer_model", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"

    opt_run = OptimizationRun(
        prompt_id=prompt_id,
        base_version_id=prompt.current_version_id,
        failure_ids=failure_ids,
        test_case_ids=test_case_ids,
        optimizer_model=optimizer_model,
    )
    db.session.add(opt_run)
    db.session.commit()

    from ..services.optimizer import run_optimization
    run_optimization(opt_run.id)

    opt_run = OptimizationRun.query.get(opt_run.id)

    result_version = None
    if opt_run.result_version_id:
        result_version = PromptVersion.query.get(opt_run.result_version_id)

    diff_lines = parse_diff(opt_run.diff)

    resp = make_response(render_template(
        "optimizations/_card.html",
        opt_run=opt_run,
        result_version=result_version,
        diff_lines=diff_lines,
        accepted=False,
        rejected=False,
    ))
    resp.headers["HX-Trigger"] = "closeOptModal"
    return resp


@bp.route("/optimizations/<run_id>/accept", methods=["POST"])
def accept_optimization(run_id):
    opt_run = OptimizationRun.query.get_or_404(run_id)

    result_version = None
    if opt_run.result_version_id:
        result_version = PromptVersion.query.get(opt_run.result_version_id)

    if result_version:
        result_version.status = "active"
        prompt = Prompt.query.get(opt_run.prompt_id)
        if prompt:
            prompt.current_version_id = result_version.id
        db.session.commit()

    diff_lines = parse_diff(opt_run.diff)

    return render_template(
        "optimizations/_card.html",
        opt_run=opt_run,
        result_version=result_version,
        diff_lines=diff_lines,
        accepted=True,
        rejected=False,
    )


@bp.route("/optimizations/<run_id>/reject", methods=["POST"])
def reject_optimization(run_id):
    opt_run = OptimizationRun.query.get_or_404(run_id)

    result_version = None
    if opt_run.result_version_id:
        result_version = PromptVersion.query.get(opt_run.result_version_id)
        if result_version:
            result_version.status = "archived"
            db.session.commit()

    diff_lines = parse_diff(opt_run.diff)

    return render_template(
        "optimizations/_card.html",
        opt_run=opt_run,
        result_version=result_version,
        diff_lines=diff_lines,
        accepted=False,
        rejected=True,
    )


@bp.route("/failures/<failure_id>/promote", methods=["POST"])
def promote_failure(failure_id):
    failure = Failure.query.get_or_404(failure_id)

    tc = TestCase(
        prompt_id=failure.prompt_id,
        name=f"Promoted from failure {failure.id[:8]}",
        description=failure.failure_reason,
        input_variables=failure.input_variables,
        expected_output=failure.expected_output,
        eval_method="contains",
        source="manual",
    )
    db.session.add(tc)
    db.session.flush()

    failure.promoted_test_case_id = tc.id
    failure.status = "resolved"
    db.session.commit()

    return render_template("failures/_card.html", failure=failure)
