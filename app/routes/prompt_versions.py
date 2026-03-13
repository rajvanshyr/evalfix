from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.prompt import Prompt
from ..models.prompt_version import PromptVersion

bp = Blueprint("prompt_versions", __name__)


@bp.route("/prompts/<prompt_id>/versions", methods=["GET"])
def list_versions(prompt_id):
    Prompt.query.get_or_404(prompt_id)
    versions = (
        PromptVersion.query
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .all()
    )
    return jsonify([v.to_dict() for v in versions])


@bp.route("/prompts/<prompt_id>/versions", methods=["POST"])
def create_version(prompt_id):
    """
    Manually create a new version for a prompt.
    Body: { "content_type": "text"|"chat", "content": "...", "model": "...", "parameters": {} }
    """
    prompt = Prompt.query.get_or_404(prompt_id)
    data = request.get_json()
    if not data or not data.get("content"):
        return jsonify({"error": "content is required"}), 400

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
        content_type=data.get("content_type", "text"),
        content=data["content"],
        system_message=data.get("system_message"),
        model=data.get("model"),
        parameters=data.get("parameters"),
        parent_version_id=latest.id if latest else None,
        source=data.get("source", "manual"),
        status=data.get("status", "active"),
    )
    db.session.add(version)
    db.session.flush()

    # Auto-set as current if this is the first version or explicitly active
    if not prompt.current_version_id or version.status == "active":
        prompt.current_version_id = version.id

    db.session.commit()
    return jsonify(version.to_dict()), 201


@bp.route("/versions/<version_id>", methods=["GET"])
def get_version(version_id):
    version = PromptVersion.query.get_or_404(version_id)
    return jsonify(version.to_dict())


@bp.route("/versions/<version_id>/activate", methods=["POST"])
def activate_version(version_id):
    """Accept this version — sets it as the prompt's current_version_id and marks it active."""
    version = PromptVersion.query.get_or_404(version_id)
    prompt = Prompt.query.get_or_404(version.prompt_id)

    version.status = "active"
    prompt.current_version_id = version.id
    db.session.commit()
    return jsonify({"activated": version_id, "prompt_id": prompt.id})


@bp.route("/versions/<version_id>/archive", methods=["POST"])
def archive_version(version_id):
    version = PromptVersion.query.get_or_404(version_id)
    version.status = "archived"
    db.session.commit()
    return jsonify(version.to_dict())
