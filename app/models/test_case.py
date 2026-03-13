from uuid import uuid4
from datetime import datetime
from ..extensions import db


class TestCase(db.Model):
    __tablename__ = "test_cases"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id = db.Column(db.String(36), db.ForeignKey("prompts.id"), nullable=False)
    name = db.Column(db.String(255))
    description = db.Column(db.Text)
    input_variables = db.Column(db.JSON)       # {"variable_name": "value", ...}
    expected_output = db.Column(db.Text)
    eval_method = db.Column(db.String(50), default="contains")  # "exact" | "contains" | "regex" | "llm_judge"
    eval_config = db.Column(db.JSON)           # {"judge_prompt": "...", "pattern": "..."} etc.
    source = db.Column(db.String(50), default="manual")  # "manual" | "ai_generated" | "api"
    tags = db.Column(db.JSON)                  # ["tag1", "tag2"]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    prompt = db.relationship("Prompt", back_populates="test_cases")

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "name": self.name,
            "description": self.description,
            "input_variables": self.input_variables,
            "expected_output": self.expected_output,
            "eval_method": self.eval_method,
            "eval_config": self.eval_config,
            "source": self.source,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }
