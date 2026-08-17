"""drones tablosu

Revision ID: 0001_drones
Revises:
Create Date: 2026-08-17

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_drones"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "aktif",
                "bakimda",
                "gorevde",
                name="dronestatus",
            ),
            nullable=False,
        ),
        sa.Column("fuel_percentage", sa.Float(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_drones_serial_number"),
        "drones",
        ["serial_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_drones_serial_number"), table_name="drones")
    op.drop_table("drones")
    sa.Enum(name="dronestatus").drop(op.get_bind(), checkfirst=True)
