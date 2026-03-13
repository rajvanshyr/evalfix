from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.failure import Failure
from ..models.test_case import TestCase
from ..models.prompt import Prompt

bp = Blueprint("failures", __name__)


@bp.route("/prompts/<prompt_id>/failures", methods=["GET"])
def list_failures(prompt_id):
    Prompt.query.get_or_404(prompt_id)
    status = request.args.get("status")
    query = Failure.query.filter_by(prompt_id=prompt_id)
    if status:
        query = query.filter_by(status=status)
    failures = query.order_by(Failure.created_at.desc()).all()
    return jsonify([f.to_dict() for f in failures])


@bp.route("/prompts/<prompt_id>/failures", methods=["POST"])
def create_failure(prompt_id):
    """
    Ingest a failure. Body:
    {
      "prompt_version_id": "...",
      "source": "api",
      "source_trace_id": "...",
      "input_variables": {...},
      "actual_output": "...",
      "expected_output": "...",
      "failure_reason": "...",
      "failure_category": "hallucination",
      "raw_metadata": {}
    }
    """
    Prompt.query.get_or_404(prompt_id)
    data = request.get_json()
    if not data or not data.get("actual_output"):
        return jsonify({"error": "actual_output is required"}), 400

    failure = Failure(
        prompt_id=prompt_id,
        prompt_version_id=data.get("prompt_version_id"),
        source=data.get("source", "api"),
        source_trace_id=data.get("source_trace_id"),
        input_variables=data.get("input_variables"),
        actual_output=data["actual_output"],
        expected_output=data.get("expected_output"),
        failure_reason=data.get("failure_reason"),
        failure_category=data.get("failure_category"),
        raw_metadata=data.get("raw_metadata"),
    )
    db.session.add(failure)
    db.session.commit()
    return jsonify(failure.to_dict()), 201


@bp.route("/failures/<failure_id>", methods=["GET"])
def get_failure(failure_id):
    return jsonify(Failure.query.get_or_404(failure_id).to_dict())


@bp.route("/failures/<failure_id>", methods=["PUT"])
def update_failure(failure_id):
    failure = Failure.query.get_or_404(failure_id)
    data = request.get_json()
    for field in ("status", "failure_reason", "failure_category", "expected_output"):
        if field in data:
            setattr(failure, field, data[field])
    db.session.commit()
    return jsonify(failure.to_dict())


@bp.route("/failures/<failure_id>/promote", methods=["POST"])
def promote_failure(failure_id):
    """
    Promote a failure to a TestCase (ground truth).
    Optionally override fields in the body.
    """
    failure = Failure.query.get_or_404(failure_id)

    data = request.get_json(silent=True) or {}
    tc = TestCase(
        prompt_id=failure.prompt_id,
        name=data.get("name", f"Promoted from failure {failure.id[:8]}"),
        description=data.get("description", failure.failure_reason),
        input_variables=data.get("input_variables", failure.input_variables),
        expected_output=data.get("expected_output", failure.expected_output),
        eval_method=data.get("eval_method", "contains"),
        eval_config=data.get("eval_config"),
        source="manual",
        tags=data.get("tags"),
    )
    db.session.add(tc)
    db.session.flush()

    failure.promoted_test_case_id = tc.id
    failure.status = "resolved"
    db.session.commit()

    return jsonify({"test_case": tc.to_dict(), "failure": failure.to_dict()}), 201


@bp.route("/failures/<failure_id>", methods=["DELETE"])
def delete_failure(failure_id):
    failure = Failure.query.get_or_404(failure_id)
    db.session.delete(failure)
    db.session.commit()
    return jsonify({"deleted": failure_id})
