"""missions tablosu

Revision ID: 0002_missions
Revises: 0001_drones
Create Date: 2026-08-17

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_missions"
down_revision: str | None = "0001_drones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drone_id", sa.Integer(), nullable=False),
        sa.Column("start_location", sa.String(length=256), nullable=False),
        sa.Column("end_location", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "planlandi",
                "devam_ediyor",
                "tamamlandi",
                "iptal",
                name="missionstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["drone_id"], ["drones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_missions_drone_id"), "missions", ["drone_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_missions_drone_id"), table_name="missions")
    op.drop_table("missions")
    sa.Enum(name="missionstatus").drop(op.get_bind(), checkfirst=True)
