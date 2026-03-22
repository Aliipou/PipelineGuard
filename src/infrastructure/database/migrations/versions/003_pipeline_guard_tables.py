"""PipelineGuard tables — pipeline monitoring, alerts, and summaries.

Revision ID: 003
Revises: 002
Create Date: 2026-02-19

Adds five tables to the public schema for the PipelineGuard vertical:
pipelines, job_executions, latency_records, pipeline_alerts, weekly_summaries.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum types
    pipeline_status = sa.Enum(
        "active", "paused", "disabled", name="pipeline_status", schema="public"
    )
    pipeline_status.create(op.get_bind(), checkfirst=True)

    job_status = sa.Enum(
        "running",
        "succeeded",
        "failed",
        "silent_failure",
        name="job_status",
        schema="public",
    )
    job_status.create(op.get_bind(), checkfirst=True)

    alert_severity = sa.Enum("warning", "critical", name="alert_severity", schema="public")
    alert_severity.create(op.get_bind(), checkfirst=True)

    alert_type = sa.Enum(
        "silent_failure",
        "latency_drift",
        "consecutive_failures",
        name="alert_type",
        schema="public",
    )
    alert_type.create(op.get_bind(), checkfirst=True)

    # pipelines — registered async data pipelines
    op.create_table(
        "pipelines",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("schedule_cron", sa.String(100), nullable=False, server_default=""),
        sa.Column("status", pipeline_status, nullable=False, server_default="active"),
        sa.Column(
            "expected_duration_seconds",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("failure_threshold", sa.Integer, nullable=False, server_default="3"),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )
    op.create_index("ix_pipelines_tenant_id", "pipelines", ["tenant_id"], schema="public")
    op.create_index("ix_pipelines_status", "pipelines", ["status"], schema="public")

    # job_executions — individual job runs
    op.create_table(
        "job_executions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "pipeline_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duration_seconds",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("records_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "is_silent_failure",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("metadata_json", JSONB, nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_job_executions_pipeline_id", "job_executions", ["pipeline_id"], schema="public"
    )
    op.create_index("ix_job_executions_tenant_id", "job_executions", ["tenant_id"], schema="public")
    op.create_index("ix_job_executions_status", "job_executions", ["status"], schema="public")
    op.create_index(
        "ix_job_executions_started_at", "job_executions", ["started_at"], schema="public"
    )

    # latency_records — latency measurements for drift tracking
    op.create_table(
        "latency_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "pipeline_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "measured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "duration_seconds",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "p50_baseline_seconds",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "p95_baseline_seconds",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "drift_percentage",
            sa.Numeric(8, 2),
            nullable=False,
            server_default="0",
        ),
        schema="public",
    )
    op.create_index(
        "ix_latency_records_pipeline_id", "latency_records", ["pipeline_id"], schema="public"
    )
    op.create_index(
        "ix_latency_records_tenant_id", "latency_records", ["tenant_id"], schema="public"
    )
    op.create_index(
        "ix_latency_records_measured_at", "latency_records", ["measured_at"], schema="public"
    )

    # pipeline_alerts — generated alerts
    op.create_table(
        "pipeline_alerts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "pipeline_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "acknowledged",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("acknowledged_by", UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )
    op.create_index(
        "ix_pipeline_alerts_tenant_id", "pipeline_alerts", ["tenant_id"], schema="public"
    )
    op.create_index(
        "ix_pipeline_alerts_pipeline_id", "pipeline_alerts", ["pipeline_id"], schema="public"
    )
    op.create_index("ix_pipeline_alerts_severity", "pipeline_alerts", ["severity"], schema="public")
    op.create_index(
        "ix_pipeline_alerts_created_at", "pipeline_alerts", ["created_at"], schema="public"
    )

    # weekly_summaries — CTO reports stored for history
    op.create_table(
        "weekly_summaries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("week_end", sa.Date, nullable=False),
        sa.Column("total_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_jobs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("silent_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pipelines_with_drift", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "avg_drift_percentage",
            sa.Numeric(8, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("top_risks", JSONB, nullable=True),
        sa.Column("plain_english_summary", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="public",
    )
    op.create_index(
        "ix_weekly_summaries_tenant_id", "weekly_summaries", ["tenant_id"], schema="public"
    )
    op.create_index(
        "ix_weekly_summaries_week_start", "weekly_summaries", ["week_start"], schema="public"
    )


def downgrade() -> None:
    op.drop_table("weekly_summaries", schema="public")
    op.drop_table("pipeline_alerts", schema="public")
    op.drop_table("latency_records", schema="public")
    op.drop_table("job_executions", schema="public")
    op.drop_table("pipelines", schema="public")

    # Drop enum types
    sa.Enum(name="alert_type", schema="public").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="alert_severity", schema="public").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_status", schema="public").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="pipeline_status", schema="public").drop(op.get_bind(), checkfirst=True)
