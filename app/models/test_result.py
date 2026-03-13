from uuid import uuid4
from datetime import datetime
from ..extensions import db


class TestResult(db.Model):
    __tablename__ = "test_results"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    test_run_id = db.Column(db.String(36), db.ForeignKey("test_runs.id"), nullable=False)
    test_case_id = db.Column(db.String(36), nullable=False)
    actual_output = db.Column(db.Text)
    passed = db.Column(db.Boolean)
    score = db.Column(db.Float)          # 0.0–1.0
    latency_ms = db.Column(db.Integer)
    tokens_used = db.Column(db.Integer)
    judge_reasoning = db.Column(db.Text) # populated when eval_method = "llm_judge"
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    test_run = db.relationship("TestRun", back_populates="results")

    def to_dict(self):
        return {
            "id": self.id,
            "test_run_id": self.test_run_id,
            "test_case_id": self.test_case_id,
            "actual_output": self.actual_output,
            "passed": self.passed,
            "score": self.score,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "judge_reasoning": self.judge_reasoning,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }
