"""Create skill graph, roles catalog, assessment, and student skill tables

Revision ID: 0002_phase2_skills
Revises: 0001_phase1_auth
Create Date: 2026-01-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase2_skills"
down_revision: Union[str, None] = "0001_phase1_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enums ─────────────────────────────────────────────────────────────────
    for enum_name, values in [
        ("skill_category", ["technical","soft_skill","domain","tool","language","framework","cloud","database","other"]),
        ("skill_status",   ["active","deprecated","pending_review"]),
        ("relationship_type", ["required","preferred","related","prerequisite","equivalent"]),
        ("proficiency_level", ["beginner","elementary","intermediate","advanced","expert"]),
        ("evidence_credibility", ["claimed","demonstrated","verified"]),
        ("question_type",  ["multiple_choice","multi_select","true_false","short_answer"]),
        ("difficulty_level", ["easy","medium","hard"]),
        ("assessment_mode", ["diagnostic","certification","adaptive"]),
        ("attempt_status", ["in_progress","completed","abandoned","timed_out"]),
    ]:
        postgresql.ENUM(*values, name=enum_name, create_type=True).create(bind, checkfirst=True)

    # ── skills ────────────────────────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canonical_name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="other"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("icon_key", sa.String(50), nullable=True),
        sa.Column("aliases", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("canonical_name"),
    )
    op.create_index("ix_skills_canonical_name", "skills", ["canonical_name"], unique=True)
    op.create_index("ix_skills_status", "skills", ["status"])

    # ── competencies ──────────────────────────────────────────────────────────
    op.create_table(
        "competencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("skill_id", "name", name="uq_competency_skill_name"),
    )
    op.create_index("ix_competencies_skill_id", "competencies", ["skill_id"])

    # ── skill_relationships ───────────────────────────────────────────────────
    op.create_table(
        "skill_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("from_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(20), nullable=False),
        sa.Column("strength", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("from_skill_id", "to_skill_id", "relationship_type", name="uq_skill_relationship"),
    )
    op.create_index("ix_skill_relationships_from", "skill_relationships", ["from_skill_id"])
    op.create_index("ix_skill_relationships_to", "skill_relationships", ["to_skill_id"])

    # ── roles_catalog ─────────────────────────────────────────────────────────
    op.create_table(
        "roles_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("industry_sector", sa.String(100), nullable=True),
        sa.Column("experience_level", sa.String(20), nullable=False, server_default="entry"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_roles_catalog_name", "roles_catalog", ["name"], unique=True)

    # ── role_requirements ─────────────────────────────────────────────────────
    op.create_table(
        "role_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("required_proficiency", sa.Integer, nullable=False, server_default="70"),
        sa.Column("is_mandatory", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("relationship_type", sa.String(20), nullable=False, server_default="required"),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles_catalog.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_role_requirements_role_id", "role_requirements", ["role_id"])
    op.create_index("ix_role_requirements_skill_id", "role_requirements", ["skill_id"])

    # ── student_skills ────────────────────────────────────────────────────────
    op.create_table(
        "student_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proficiency", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("credibility", sa.String(20), nullable=False, server_default="claimed"),
        sa.Column("assessment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("student_id", "skill_id", name="uq_student_skill"),
        sa.CheckConstraint("proficiency >= 0 AND proficiency <= 100", name="ck_proficiency_range"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_confidence_range"),
    )
    op.create_index("ix_student_skills_student_id", "student_skills", ["student_id"])
    op.create_index("ix_student_skills_skill_id", "student_skills", ["skill_id"])

    # ── assessment_questions ──────────────────────────────────────────────────
    op.create_table(
        "assessment_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question_type", sa.String(20), nullable=False, server_default="multiple_choice"),
        sa.Column("difficulty", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("options", postgresql.JSON, nullable=True),
        sa.Column("correct_answer", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("points", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competency_id"], ["competencies.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_assessment_questions_skill_id", "assessment_questions", ["skill_id"])
    op.create_index("ix_assessment_questions_difficulty", "assessment_questions", ["difficulty"])
    op.create_index("ix_assessment_questions_is_active", "assessment_questions", ["is_active"])

    # ── assessment_attempts ───────────────────────────────────────────────────
    op.create_table(
        "assessment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="adaptive"),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_limit_seconds", sa.Integer, nullable=True),
        sa.Column("total_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_flagged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("flag_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_assessment_attempts_student_id", "assessment_attempts", ["student_id"])
    op.create_index("ix_assessment_attempts_skill_id", "assessment_attempts", ["skill_id"])
    op.create_index("ix_assessment_attempts_status", "assessment_attempts", ["status"])

    # ── assessment_answers ────────────────────────────────────────────────────
    op.create_table(
        "assessment_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_answer", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("question_difficulty", sa.String(10), nullable=False),
        sa.Column("time_taken_seconds", sa.Integer, nullable=True),
        sa.Column("question_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["assessment_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["assessment_questions.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_assessment_answers_attempt_id", "assessment_answers", ["attempt_id"])

    # ── assessment_results ────────────────────────────────────────────────────
    op.create_table(
        "assessment_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_score", sa.Float, nullable=False),
        sa.Column("proficiency_score", sa.Float, nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column("competency_scores", postgresql.JSON, nullable=True),
        sa.Column("proficiency_level", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["assessment_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_assessment_results_student_id", "assessment_results", ["student_id"])
    op.create_index("ix_assessment_results_skill_id", "assessment_results", ["skill_id"])

    # ── updated_at triggers ───────────────────────────────────────────────────
    new_tables = [
        "skills", "competencies", "skill_relationships", "roles_catalog",
        "role_requirements", "student_skills", "assessment_questions",
        "assessment_attempts", "assessment_answers", "assessment_results",
    ]
    for table in new_tables:
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    tables = [
        "assessment_results", "assessment_answers", "assessment_attempts",
        "assessment_questions", "student_skills", "role_requirements",
        "roles_catalog", "skill_relationships", "competencies", "skills",
    ]
    for t in tables:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON {t};")
        op.drop_table(t)

    for enum_name in [
        "skill_category", "skill_status", "relationship_type", "proficiency_level",
        "evidence_credibility", "question_type", "difficulty_level",
        "assessment_mode", "attempt_status",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
