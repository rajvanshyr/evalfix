from uuid import uuid4
from datetime import datetime
from ..extensions import db


class Failure(db.Model):
    __tablename__ = "failures"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id = db.Column(db.String(36), db.ForeignKey("prompts.id"), nullable=False)
    prompt_version_id = db.Column(db.String(36), nullable=True)  # which version was active when this failed

    # Where this failure came from
    source = db.Column(db.String(50), default="api")  # "ui" | "api" | "langsmith" | "langfuse" | "helicone" | "custom"
    source_trace_id = db.Column(db.String(255))        # external ID from observability platform

    # The failure data
    input_variables = db.Column(db.JSON)     # what was passed in
    actual_output = db.Column(db.Text)       # what the LLM produced
    expected_output = db.Column(db.Text)     # optional: what it should have produced
    failure_reason = db.Column(db.Text)      # human description: "hallucinated a citation"
    failure_category = db.Column(db.String(50))  # "hallucination" | "format" | "wrong_answer" | "refusal" | "other"
    raw_metadata = db.Column(db.JSON)        # full payload from source platform

    status = db.Column(db.String(50), default="pending")  # "pending" | "in_optimization" | "resolved" | "ignored"
    promoted_test_case_id = db.Column(db.String(36), nullable=True)  # set when promoted to a TestCase

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    prompt = db.relationship("Prompt", back_populates="failures")

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_id": self.prompt_id,
            "prompt_version_id": self.prompt_version_id,
            "source": self.source,
            "source_trace_id": self.source_trace_id,
            "input_variables": self.input_variables,
            "actual_output": self.actual_output,
            "expected_output": self.expected_output,
            "failure_reason": self.failure_reason,
            "failure_category": self.failure_category,
            "raw_metadata": self.raw_metadata,
            "status": self.status,
            "promoted_test_case_id": self.promoted_test_case_id,
            "created_at": self.created_at.isoformat(),
        }
