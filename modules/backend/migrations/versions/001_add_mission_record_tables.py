"""add mission record tables

Revision ID: 001_mission_records
Revises:
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa


revision = "001_mission_records"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # mission_records
    op.create_table(
        "mission_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False, index=True),
        sa.Column("roster_name", sa.String(200), nullable=True, index=True),
        sa.Column("objective_statement", sa.Text, nullable=True),
        sa.Column("objective_category", sa.String(100), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("task_plan_json", sa.JSON, nullable=True),
        sa.Column("mission_outcome_json", sa.JSON, nullable=True),
        sa.Column("planning_thinking_trace", sa.Text, nullable=True),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("started_at", sa.String(30), nullable=True),
        sa.Column("completed_at", sa.String(30), nullable=True),
        sa.Column(
            "parent_mission_id",
            sa.String(36),
            sa.ForeignKey("mission_records.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # task_executions
    op.create_table(
        "task_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_record_id",
            sa.String(36),
            sa.ForeignKey("mission_records.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("task_id", sa.String(200), nullable=False),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("output_data", sa.JSON, nullable=True),
        sa.Column("token_usage", sa.JSON, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("verification_outcome", sa.JSON, nullable=True),
        sa.Column("started_at", sa.String(30), nullable=True),
        sa.Column("completed_at", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # task_attempts
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_execution_id",
            sa.String(36),
            sa.ForeignKey("task_executions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("failure_tier", sa.String(30), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("feedback_provided", sa.Text, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # mission_decisions
    op.create_table(
        "mission_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_record_id",
            sa.String(36),
            sa.ForeignKey("mission_records.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("decision_type", sa.String(20), nullable=False, index=True),
        sa.Column("task_id", sa.String(200), nullable=True),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mission_decisions")
    op.drop_table("task_attempts")
    op.drop_table("task_executions")
    op.drop_table("mission_records")
