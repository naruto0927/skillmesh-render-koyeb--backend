"""Create learning resources, paths, enrollments, and progress tables

Revision ID: 0005_phase5_learning
Revises: 0004_phase4_gap_engine
Create Date: 2026-01-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase5_learning"
down_revision: Union[str, None] = "0004_phase4_gap_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    for enum_name, values in [
        ("resource_type", [
            "course", "tutorial", "documentation",
            "practice_project", "video", "book", "exercise",
        ]),
        ("resource_difficulty", ["beginner", "intermediate", "advanced"]),
        ("enrollment_status", ["active", "completed", "paused", "dropped"]),
        ("progress_status", ["not_started", "in_progress", "completed", "skipped"]),
    ]:
        postgresql.ENUM(*values, name=enum_name, create_type=True).create(
            bind, checkfirst=True
        )

    # ── learning_resources ────────────────────────────────────────────────────
    op.create_table(
        "learning_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="intermediate"),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("estimated_minutes", sa.Integer, nullable=True),
        sa.Column("is_free", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expected_proficiency_gain", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competency_id"], ["competencies.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_learning_resources_skill_id", "learning_resources", ["skill_id"])
    op.create_index("ix_learning_resources_is_active", "learning_resources", ["is_active"])

    # ── learning_paths ────────────────────────────────────────────────────────
    op.create_table(
        "learning_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("target_proficiency", sa.Float, nullable=False),
        sa.Column("from_proficiency", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("total_estimated_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_learning_paths_skill_id", "learning_paths", ["skill_id"])

    # ── learning_path_resources ───────────────────────────────────────────────
    op.create_table(
        "learning_path_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["learning_resources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("path_id", "resource_id", name="uq_path_resource"),
    )
    op.create_index("ix_learning_path_resources_path_id", "learning_path_resources", ["path_id"])

    # ── learning_path_enrollments ─────────────────────────────────────────────
    op.create_table(
        "learning_path_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("proficiency_at_enrollment", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("student_id", "path_id", name="uq_student_path"),
    )
    op.create_index("ix_learning_path_enrollments_student_id",
                    "learning_path_enrollments", ["student_id"])
    op.create_index("ix_learning_path_enrollments_status",
                    "learning_path_enrollments", ["status"])

    # ── learning_progress ─────────────────────────────────────────────────────
    op.create_table(
        "learning_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id"], ["learning_path_enrollments.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["learning_resources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("enrollment_id", "resource_id", name="uq_enrollment_resource"),
    )
    op.create_index("ix_learning_progress_enrollment_id", "learning_progress", ["enrollment_id"])

    # ── updated_at triggers ───────────────────────────────────────────────────
    for table in [
        "learning_resources", "learning_paths", "learning_path_resources",
        "learning_path_enrollments", "learning_progress",
    ]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    tables = [
        "learning_progress", "learning_path_enrollments",
        "learning_path_resources", "learning_paths", "learning_resources",
    ]
    for t in tables:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON {t};")
        op.drop_table(t)
    for e in ["resource_type", "resource_difficulty", "enrollment_status", "progress_status"]:
        op.execute(f"DROP TYPE IF EXISTS {e};")
