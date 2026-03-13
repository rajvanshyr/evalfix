from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.prompt_file import PromptFile
from ..models.project import Project
from ..services.parser import parse_prompt_file

bp = Blueprint("prompt_files", __name__)


@bp.route("/projects/<project_id>/prompt-files", methods=["GET"])
def list_prompt_files(project_id):
    Project.query.get_or_404(project_id)
    files = PromptFile.query.filter_by(project_id=project_id).all()
    return jsonify([f.to_dict() for f in files])


@bp.route("/projects/<project_id>/prompt-files", methods=["POST"])
def create_prompt_file(project_id):
    """
    Upload a file. Body:
      { "file_path": "src/prompts.py", "language": "python", "raw_content": "..." }
    """
    Project.query.get_or_404(project_id)
    data = request.get_json()
    if not data or not data.get("file_path"):
        return jsonify({"error": "file_path is required"}), 400

    pf = PromptFile(
        project_id=project_id,
        file_path=data["file_path"],
        language=data.get("language", "python"),
        raw_content=data.get("raw_content"),
    )
    db.session.add(pf)
    db.session.commit()
    return jsonify(pf.to_dict()), 201


@bp.route("/prompt-files/<file_id>", methods=["GET"])
def get_prompt_file(file_id):
    pf = PromptFile.query.get_or_404(file_id)
    return jsonify(pf.to_dict())


@bp.route("/prompt-files/<file_id>/parse", methods=["POST"])
def parse_file(file_id):
    """
    Trigger parsing of the file — extracts Prompt + PromptVersion records.
    Optionally pass updated raw_content in the body to update before parsing.
    """
    pf = PromptFile.query.get_or_404(file_id)
    data = request.get_json(silent=True) or {}
    if "raw_content" in data:
        pf.raw_content = data["raw_content"]
        db.session.commit()

    results = parse_prompt_file(file_id)
    return jsonify({"parsed": results})


@bp.route("/prompt-files/<file_id>", methods=["DELETE"])
def delete_prompt_file(file_id):
    pf = PromptFile.query.get_or_404(file_id)
    db.session.delete(pf)
    db.session.commit()
    return jsonify({"deleted": file_id})
