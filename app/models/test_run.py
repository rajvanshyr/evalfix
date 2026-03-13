from uuid import uuid4
from datetime import datetime
from ..extensions import db


class TestRun(db.Model):
    __tablename__ = "test_runs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_version_id = db.Column(db.String(36), nullable=False)
    optimization_run_id = db.Column(db.String(36), nullable=True)  # set if triggered by an optimization

    status = db.Column(db.String(20), default="pending")   # "pending" | "running" | "completed" | "failed"
    triggered_by = db.Column(db.String(50), default="manual")  # "manual" | "post_optimization" | "api"

    pass_count = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)
    avg_score = db.Column(db.Float)

    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    results = db.relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan")

    def to_dict(self, include_results=False):
        data = {
            "id": self.id,
            "prompt_version_id": self.prompt_version_id,
            "optimization_run_id": self.optimization_run_id,
            "status": self.status,
            "triggered_by": self.triggered_by,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "total_count": self.total_count,
            "avg_score": self.avg_score,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
        }
        if include_results:
            data["results"] = [r.to_dict() for r in self.results]
        return data
