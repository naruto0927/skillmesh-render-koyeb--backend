"""Create documents, skill_evidence, skill_passports tables

Revision ID: 0003_phase3_evidence
Revises: 0002_phase2_skills
Create Date: 2026-01-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase3_evidence"
down_revision: Union[str, None] = "0002_phase2_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    for enum_name, values in [
        ("evidence_type", [
            "assessment", "certification", "project", "internship",
            "academic_record", "industry_test", "faculty_verification",
            "employer_verification", "self_declaration",
        ]),
        ("verification_status", ["unverified", "pending", "verified", "rejected"]),
        ("passport_visibility", [
            "private", "institution_only", "recruiter_visible", "public"
        ]),
    ]:
        postgresql.ENUM(*values, name=enum_name, create_type=True).create(
            bind, checkfirst=True
        )

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("bucket", sa.String(100), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("scan_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])

    # ── skill_evidence ────────────────────────────────────────────────────────
    op.create_table(
        "skill_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("verification_status", sa.String(20), nullable=False,
                  server_default="unverified"),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("verified_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assessment_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assessment_result_id"], ["assessment_results.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_skill_evidence_student_id", "skill_evidence", ["student_id"])
    op.create_index("ix_skill_evidence_skill_id", "skill_evidence", ["skill_id"])
    op.create_index("ix_skill_evidence_status", "skill_evidence", ["verification_status"])

    # ── skill_passports ───────────────────────────────────────────────────────
    op.create_table(
        "skill_passports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("visibility", sa.String(30), nullable=False,
                  server_default="institution_only"),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column("headline", sa.String(200), nullable=True),
        sa.Column("target_role", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_skill_passports_student_id", "skill_passports", ["student_id"],
                    unique=True)
    op.create_index("ix_skill_passports_share_token", "skill_passports", ["share_token"],
                    unique=True)

    # ── updated_at triggers ───────────────────────────────────────────────────
    for table in ["documents", "skill_evidence", "skill_passports"]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    for table in ["skill_passports", "skill_evidence", "documents"]:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON {table};")
        op.drop_table(table)

    for enum_name in ["evidence_type", "verification_status", "passport_visibility"]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
