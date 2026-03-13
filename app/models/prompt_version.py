from uuid import uuid4
from datetime import datetime
from ..extensions import db


class PromptVersion(db.Model):
    __tablename__ = "prompt_versions"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id = db.Column(db.String(36), db.ForeignKey("prompts.id"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)

    # Content — supports both plain text and chat message arrays
    content_type = db.Column(db.String(10), default="text")  # "text" | "chat"
    content = db.Column(db.Text, nullable=False)
    # For "text": plain string with {variable} placeholders
    # For "chat": JSON array of {"role": "system"|"user"|"assistant", "content": "..."}

    system_message = db.Column(db.Text)  # convenience field for chat system prompt
    model = db.Column(db.String(100))    # e.g. "claude-sonnet-4-6"
    parameters = db.Column(db.JSON)      # {"temperature": 0.7, "max_tokens": 1024, ...}

    parent_version_id = db.Column(db.String(36), nullable=True)  # lineage
    source = db.Column(db.String(50), default="manual")  # "manual" | "ai_generated" | "file_import" | "api"
    status = db.Column(db.String(20), default="active")  # "draft" | "active" | "archived"

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    prompt = db.relationship("Prompt", back_populates="versions", foreign_keys=[prompt_id])

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "version_number": self.version_number,
            "content_type": self.content_type,
            "content": self.content,
            "system_message": self.system_message,
            "model": self.model,
            "parameters": self.parameters,
            "parent_version_id": self.parent_version_id,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
