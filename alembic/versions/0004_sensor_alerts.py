"""sensor_alerts tablosu

Revision ID: 0004_sensor_alerts
Revises: 0003_telemetry_logs
Create Date: 2026-08-18

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_sensor_alerts"
down_revision: str | None = "0003_telemetry_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sensor_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drone_id", sa.Integer(), nullable=False),
        sa.Column("telemetry_log_id", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "alert_type",
            sa.Enum(
                "dusuk_yakit",
                "anomali",
                "sinyal_kaybi",
                name="alerttype",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "dusuk",
                "orta",
                "yuksek",
                "kritik",
                name="alertseverity",
            ),
            nullable=False,
        ),
        sa.Column("message", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["drone_id"], ["drones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["telemetry_log_id"], ["telemetry_logs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sensor_alerts_drone_id"), "sensor_alerts", ["drone_id"])
    op.create_index(op.f("ix_sensor_alerts_timestamp"), "sensor_alerts", ["timestamp"])
    op.create_index(op.f("ix_sensor_alerts_alert_type"), "sensor_alerts", ["alert_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sensor_alerts_alert_type"), table_name="sensor_alerts")
    op.drop_index(op.f("ix_sensor_alerts_timestamp"), table_name="sensor_alerts")
    op.drop_index(op.f("ix_sensor_alerts_drone_id"), table_name="sensor_alerts")
    op.drop_table("sensor_alerts")
    sa.Enum(name="alertseverity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="alerttype").drop(op.get_bind(), checkfirst=True)
