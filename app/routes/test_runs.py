from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.test_run import TestRun
from ..models.prompt_version import PromptVersion
from ..services.evaluator import run_test_run

bp = Blueprint("test_runs", __name__)


@bp.route("/versions/<version_id>/test-runs", methods=["POST"])
def create_test_run(version_id):
    """
    Kick off a test run against a specific PromptVersion.
    Body (optional): { "triggered_by": "manual" }
    """
    PromptVersion.query.get_or_404(version_id)
    data = request.get_json(silent=True) or {}

    test_run = TestRun(
        prompt_version_id=version_id,
        optimization_run_id=data.get("optimization_run_id"),
        triggered_by=data.get("triggered_by", "manual"),
    )
    db.session.add(test_run)
    db.session.commit()

    # Run synchronously — in production, move this to a background worker
    run_test_run(test_run.id)

    return jsonify(TestRun.query.get(test_run.id).to_dict(include_results=True)), 201


@bp.route("/test-runs/<run_id>", methods=["GET"])
def get_test_run(run_id):
    test_run = TestRun.query.get_or_404(run_id)
    return jsonify(test_run.to_dict(include_results=True))


@bp.route("/versions/<version_id>/test-runs", methods=["GET"])
def list_test_runs(version_id):
    PromptVersion.query.get_or_404(version_id)
    runs = (
        TestRun.query
        .filter_by(prompt_version_id=version_id)
        .order_by(TestRun.created_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in runs])
