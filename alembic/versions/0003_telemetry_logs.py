"""telemetry_logs tablosu

Revision ID: 0003_telemetry_logs
Revises: 0002_missions
Create Date: 2026-08-17

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_telemetry_logs"
down_revision: str | None = "0002_missions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drone_id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("altitude", sa.Float(), nullable=False),
        sa.Column("fuel_percentage", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["drone_id"], ["drones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_telemetry_logs_drone_id"), "telemetry_logs", ["drone_id"]
    )
    op.create_index(
        op.f("ix_telemetry_logs_timestamp"), "telemetry_logs", ["timestamp"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_telemetry_logs_timestamp"), table_name="telemetry_logs")
    op.drop_index(op.f("ix_telemetry_logs_drone_id"), table_name="telemetry_logs")
    op.drop_table("telemetry_logs")
