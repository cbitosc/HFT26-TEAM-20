"""Deterministic evaluation results and, separately, operational measurements.

The two live in different tables on purpose: operational data (time, tokens, cost) can
never become an input to, or be confused with, the deterministic score.
"""
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, new_id, utcnow
from app.scoring import SCORE_TOLERANCE, overall_score_sql, test_pass_rate_sql


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("tests_total >= 1", name="ck_evaluations_tests_total"),
        CheckConstraint("tests_passed >= 0 AND tests_passed <= tests_total", name="ck_evaluations_tests_passed"),
        CheckConstraint("test_pass_rate BETWEEN 0 AND 100", name="ck_evaluations_pass_rate"),
        CheckConstraint("correctness_score BETWEEN 0 AND 100", name="ck_evaluations_correctness"),
        CheckConstraint("code_quality_score BETWEEN 0 AND 100", name="ck_evaluations_code_quality"),
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="ck_evaluations_overall"),
        # The stored pass rate must be tests_passed / tests_total * 100. Without this, a forged pass
        # rate could carry a forged overall score. COALESCE(..., 0) makes a NULL result (for example
        # division by zero) fail the check; a bare NULL would silently pass a CHECK constraint.
        CheckConstraint(
            f"COALESCE(ABS(test_pass_rate - ({test_pass_rate_sql('tests_passed', 'tests_total')})) "
            f"<= {SCORE_TOLERANCE!r}, 0)",
            name="ck_evaluations_pass_rate_consistent",
        ),
        # The stored overall score must equal the approved weighted sum of its stored components
        # (50% pass rate, 30% correctness, 20% code quality), generated from app.scoring.
        CheckConstraint(
            f"COALESCE(ABS(overall_score - ({overall_score_sql('test_pass_rate', 'correctness_score', 'code_quality_score')})) "
            f"<= {SCORE_TOLERANCE!r}, 0)",
            name="ck_evaluations_overall_consistent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"), index=True)
    # Deterministic components, all on a 0-100 scale.
    tests_passed: Mapped[int] = mapped_column(Integer)
    tests_total: Mapped[int] = mapped_column(Integer)
    test_pass_rate: Mapped[float] = mapped_column(Float)
    correctness_score: Mapped[float] = mapped_column(Float)
    code_quality_score: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float)
    # List of {test_name, expected, actual, exception, traceback_excerpt}
    failure_details: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    version: Mapped["Version"] = relationship(back_populates="evaluations")  # noqa: F821
    operational: Mapped["EvaluationOperationalMetrics | None"] = relationship(
        back_populates="evaluation", uselist=False
    )


class EvaluationOperationalMetrics(Base):
    __tablename__ = "evaluation_operational_metrics"
    __table_args__ = (
        CheckConstraint("execution_time_seconds IS NULL OR execution_time_seconds >= 0", name="ck_ops_time"),
        CheckConstraint("prompt_tokens IS NULL OR prompt_tokens >= 0", name="ck_ops_prompt_tokens"),
        CheckConstraint("completion_tokens IS NULL OR completion_tokens >= 0", name="ck_ops_completion_tokens"),
        CheckConstraint("total_tokens IS NULL OR total_tokens >= 0", name="ck_ops_total_tokens"),
        CheckConstraint("api_cost_usd IS NULL OR api_cost_usd >= 0", name="ck_ops_cost"),
        CheckConstraint(
            "api_cost_source IS NULL OR api_cost_source IN ('provider_reported', 'estimated')",
            name="ck_ops_cost_source",
        ),
        # A cost figure is never stored without saying where it came from.
        CheckConstraint("(api_cost_usd IS NULL) = (api_cost_source IS NULL)", name="ck_ops_cost_has_source"),
    )

    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="RESTRICT"), primary_key=True
    )
    execution_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_cost_source: Mapped[str | None] = mapped_column(String(16), nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="operational")
