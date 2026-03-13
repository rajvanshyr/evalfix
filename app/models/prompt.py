from uuid import uuid4
from datetime import datetime
from ..extensions import db


class Prompt(db.Model):
    __tablename__ = "prompts"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    prompt_file_id = db.Column(db.String(36), db.ForeignKey("prompt_files.id"), nullable=True)
    name = db.Column(db.String(255), nullable=False)  # variable name / identifier
    description = db.Column(db.Text)
    current_version_id = db.Column(db.String(36), nullable=True)  # set after first version is created
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship("Project", back_populates="prompts")
    prompt_file = db.relationship("PromptFile", back_populates="prompts")
    versions = db.relationship("PromptVersion", back_populates="prompt", foreign_keys="PromptVersion.prompt_id", cascade="all, delete-orphan")
    test_cases = db.relationship("TestCase", back_populates="prompt", cascade="all, delete-orphan")
    failures = db.relationship("Failure", back_populates="prompt", cascade="all, delete-orphan")
    optimization_runs = db.relationship("OptimizationRun", back_populates="prompt", cascade="all, delete-orphan")

    def to_dict(self, include_related=False):
        data = {
            "id": self.id,
            "project_id": self.project_id,
            "prompt_file_id": self.prompt_file_id,
            "name": self.name,
            "description": self.description,
            "current_version_id": self.current_version_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_related:
            data["versions"] = [v.to_dict() for v in self.versions]
            data["test_cases"] = [tc.to_dict() for tc in self.test_cases]
            data["failures"] = [f.to_dict() for f in self.failures]
        return data
