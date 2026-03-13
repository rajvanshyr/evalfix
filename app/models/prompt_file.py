from uuid import uuid4
from datetime import datetime
from ..extensions import db


class PromptFile(db.Model):
    __tablename__ = "prompt_files"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id"), nullable=False)
    file_path = db.Column(db.String(1024), nullable=False)
    language = db.Column(db.String(50), default="python")  # python | js | ts | text
    raw_content = db.Column(db.Text)
    last_parsed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", back_populates="prompt_files")
    prompts = db.relationship("Prompt", back_populates="prompt_file")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "file_path": self.file_path,
            "language": self.language,
            "raw_content": self.raw_content,
            "last_parsed_at": self.last_parsed_at.isoformat() if self.last_parsed_at else None,
            "created_at": self.created_at.isoformat(),
        }
