from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.test_case import TestCase
from ..models.prompt import Prompt

bp = Blueprint("test_cases", __name__)


@bp.route("/prompts/<prompt_id>/test-cases", methods=["GET"])
def list_test_cases(prompt_id):
    Prompt.query.get_or_404(prompt_id)
    test_cases = TestCase.query.filter_by(prompt_id=prompt_id).all()
    return jsonify([tc.to_dict() for tc in test_cases])


@bp.route("/prompts/<prompt_id>/test-cases", methods=["POST"])
def create_test_case(prompt_id):
    """
    Body: {
      "name": "...", "input_variables": {...}, "expected_output": "...",
      "eval_method": "contains", "eval_config": {}, "tags": []
    }
    """
    Prompt.query.get_or_404(prompt_id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "request body required"}), 400

    tc = TestCase(
        prompt_id=prompt_id,
        name=data.get("name"),
        description=data.get("description"),
        input_variables=data.get("input_variables"),
        expected_output=data.get("expected_output"),
        eval_method=data.get("eval_method", "contains"),
        eval_config=data.get("eval_config"),
        source=data.get("source", "manual"),
        tags=data.get("tags"),
    )
    db.session.add(tc)
    db.session.commit()
    return jsonify(tc.to_dict()), 201


@bp.route("/test-cases/<tc_id>", methods=["GET"])
def get_test_case(tc_id):
    tc = TestCase.query.get_or_404(tc_id)
    return jsonify(tc.to_dict())


@bp.route("/test-cases/<tc_id>", methods=["PUT"])
def update_test_case(tc_id):
    tc = TestCase.query.get_or_404(tc_id)
    data = request.get_json()
    for field in ("name", "description", "input_variables", "expected_output", "eval_method", "eval_config", "tags"):
        if field in data:
            setattr(tc, field, data[field])
    db.session.commit()
    return jsonify(tc.to_dict())


@bp.route("/test-cases/<tc_id>", methods=["DELETE"])
def delete_test_case(tc_id):
    tc = TestCase.query.get_or_404(tc_id)
    db.session.delete(tc)
    db.session.commit()
    return jsonify({"deleted": tc_id})
