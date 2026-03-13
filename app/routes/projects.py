from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models.project import Project

bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.route("", methods=["GET"])
def list_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])


@bp.route("", methods=["POST"])
def create_project():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name is required"}), 400

    project = Project(name=data["name"], description=data.get("description"))
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201


@bp.route("/<project_id>", methods=["GET"])
def get_project(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify(project.to_dict())


@bp.route("/<project_id>", methods=["PUT"])
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    if "name" in data:
        project.name = data["name"]
    if "description" in data:
        project.description = data["description"]
    db.session.commit()
    return jsonify(project.to_dict())


@bp.route("/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return jsonify({"deleted": project_id})
