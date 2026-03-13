from uuid import uuid4
from datetime import datetime
from ..extensions import db


class OptimizationRun(db.Model):
    __tablename__ = "optimization_runs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id = db.Column(db.String(36), db.ForeignKey("prompts.id"), nullable=False)
    base_version_id = db.Column(db.String(36), nullable=False)    # the version being improved
    result_version_id = db.Column(db.String(36), nullable=True)   # the AI-generated improvement (null until done)

    failure_ids = db.Column(db.JSON)      # list of Failure IDs used as negative examples
    test_case_ids = db.Column(db.JSON)    # list of TestCase IDs used as ground truth

    optimizer_model = db.Column(db.String(100), default="claude-sonnet-4-6")
    optimizer_prompt = db.Column(db.Text)  # the meta-prompt sent to the optimizer
    reasoning = db.Column(db.Text)         # LLM's explanation of what it changed and why
    diff = db.Column(db.Text)              # unified diff between base and result content

    status = db.Column(db.String(20), default="pending")  # "pending" | "running" | "completed" | "failed"
    error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    prompt = db.relationship("Prompt", back_populates="optimization_runs")

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "base_version_id": self.base_version_id,
            "result_version_id": self.result_version_id,
            "failure_ids": self.failure_ids,
            "test_case_ids": self.test_case_ids,
            "optimizer_model": self.optimizer_model,
            "optimizer_prompt": self.optimizer_prompt,
            "reasoning": self.reasoning,
            "diff": self.diff,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
