"""Create student_target_roles table

Revision ID: 0004_phase4_gap_engine
Revises: 0003_phase3_evidence
Create Date: 2026-01-04 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase4_gap_engine"
down_revision: Union[str, None] = "0003_phase3_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_target_roles",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles_catalog.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_student_target_roles_student_id",
                    "student_target_roles", ["student_id"])
    op.create_index("ix_student_target_roles_role_id",
                    "student_target_roles", ["role_id"])

    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON student_target_roles
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON student_target_roles;")
    op.drop_table("student_target_roles")
