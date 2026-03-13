from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.prompt import Prompt
from ..models.project import Project

bp = Blueprint("prompts", __name__)


@bp.route("/projects/<project_id>/prompts", methods=["GET"])
def list_prompts(project_id):
    Project.query.get_or_404(project_id)
    prompts = Prompt.query.filter_by(project_id=project_id).all()
    return jsonify([p.to_dict() for p in prompts])


@bp.route("/projects/<project_id>/prompts", methods=["POST"])
def create_prompt(project_id):
    """Manually create a prompt (without parsing a file)."""
    Project.query.get_or_404(project_id)
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name is required"}), 400

    prompt = Prompt(
        project_id=project_id,
        name=data["name"],
        description=data.get("description"),
        prompt_file_id=data.get("prompt_file_id"),
    )
    db.session.add(prompt)
    db.session.commit()
    return jsonify(prompt.to_dict()), 201


@bp.route("/prompts/<prompt_id>", methods=["GET"])
def get_prompt(prompt_id):
    """Returns the prompt with all versions, test cases, and failures."""
    prompt = Prompt.query.get_or_404(prompt_id)
    return jsonify(prompt.to_dict(include_related=True))


@bp.route("/prompts/<prompt_id>", methods=["PUT"])
def update_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    data = request.get_json()
    if "name" in data:
        prompt.name = data["name"]
    if "description" in data:
        prompt.description = data["description"]
    db.session.commit()
    return jsonify(prompt.to_dict())


@bp.route("/prompts/<prompt_id>", methods=["DELETE"])
def delete_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    db.session.delete(prompt)
    db.session.commit()
    return jsonify({"deleted": prompt_id})
