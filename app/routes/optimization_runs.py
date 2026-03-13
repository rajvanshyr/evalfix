from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.optimization_run import OptimizationRun
from ..models.prompt import Prompt
from ..models.prompt_version import PromptVersion
from ..services.optimizer import run_optimization

bp = Blueprint("optimization_runs", __name__)


@bp.route("/prompts/<prompt_id>/optimizations", methods=["POST"])
def create_optimization(prompt_id):
    """
    Start an optimization run.
    Body:
    {
      "failure_ids": ["id1", "id2"],
      "test_case_ids": ["id3", "id4"],
      "optimizer_model": "claude-sonnet-4-6"   // optional
    }
    Uses the prompt's current_version_id as the base unless overridden.
    """
    prompt = Prompt.query.get_or_404(prompt_id)
    data = request.get_json() or {}

    base_version_id = data.get("base_version_id", prompt.current_version_id)
    if not base_version_id:
        return jsonify({"error": "prompt has no current version — create one first"}), 400

    PromptVersion.query.get_or_404(base_version_id)

    opt_run = OptimizationRun(
        prompt_id=prompt_id,
        base_version_id=base_version_id,
        failure_ids=data.get("failure_ids", []),
        test_case_ids=data.get("test_case_ids", []),
        optimizer_model=data.get("optimizer_model", "claude-sonnet-4-6"),
    )
    db.session.add(opt_run)
    db.session.commit()

    # Run synchronously — in production, move this to a background worker
    run_optimization(opt_run.id)

    return jsonify(OptimizationRun.query.get(opt_run.id).to_dict()), 201


@bp.route("/prompts/<prompt_id>/optimizations", methods=["GET"])
def list_optimizations(prompt_id):
    Prompt.query.get_or_404(prompt_id)
    runs = (
        OptimizationRun.query
        .filter_by(prompt_id=prompt_id)
        .order_by(OptimizationRun.created_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in runs])


@bp.route("/optimizations/<run_id>", methods=["GET"])
def get_optimization(run_id):
    return jsonify(OptimizationRun.query.get_or_404(run_id).to_dict())


@bp.route("/optimizations/<run_id>/accept", methods=["POST"])
def accept_optimization(run_id):
    """
    Accept the AI-suggested version:
    - Sets it as active
    - Sets it as the prompt's current_version_id
    """
    opt_run = OptimizationRun.query.get_or_404(run_id)
    if opt_run.status != "completed":
        return jsonify({"error": "optimization has not completed successfully"}), 400
    if not opt_run.result_version_id:
        return jsonify({"error": "no result version found"}), 400

    result_version = PromptVersion.query.get_or_404(opt_run.result_version_id)
    prompt = Prompt.query.get_or_404(opt_run.prompt_id)

    result_version.status = "active"
    prompt.current_version_id = result_version.id
    db.session.commit()

    return jsonify({
        "accepted_version": result_version.to_dict(),
        "prompt": prompt.to_dict(),
    })


@bp.route("/optimizations/<run_id>/reject", methods=["POST"])
def reject_optimization(run_id):
    """Discard the suggested version by archiving it."""
    opt_run = OptimizationRun.query.get_or_404(run_id)
    if opt_run.result_version_id:
        result_version = PromptVersion.query.get(opt_run.result_version_id)
        if result_version:
            result_version.status = "archived"
            db.session.commit()
    return jsonify({"rejected": run_id})
