"""Create institutions, industry_organizations, users tables

Revision ID: 0001_phase1_auth
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1_auth"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    institution_type = postgresql.ENUM(
        "UNIVERSITY",
        "DEEMED_UNIVERSITY",
        "AUTONOMOUS_COLLEGE",
        "AFFILIATED_COLLEGE",
        "INSTITUTE_OF_TECHNOLOGY",
        "POLYTECHNIC",
        "OTHER",
        name="institution_type",
        create_type=True,
    )
    institution_type.create(op.get_bind(), checkfirst=True)

    user_role = postgresql.ENUM(
        "SUPER_ADMIN",
        "INSTITUTION_ADMIN",
        "FACULTY",
        "STUDENT",
        "INDUSTRY_ADMIN",
        "RECRUITER",
        name="user_role",
        create_type=True,
    )
    user_role.create(op.get_bind(), checkfirst=True)

    # ── institutions ─────────────────────────────────────────────────────────
    op.create_table(
        "institutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(50), nullable=True),
        sa.Column("institution_type", sa.Enum("UNIVERSITY", "DEEMED_UNIVERSITY", "AUTONOMOUS_COLLEGE", "AFFILIATED_COLLEGE", "INSTITUTE_OF_TECHNOLOGY", "POLYTECHNIC", "OTHER", name="institution_type", create_type=False), nullable=False, server_default="OTHER"),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=False, server_default="India"),
        sa.Column("pincode", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutions_name", "institutions", ["name"])

    # ── industry_organizations ────────────────────────────────────────────────
    op.create_table(
        "industry_organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry_sector", sa.String(100), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("headquarters_city", sa.String(100), nullable=True),
        sa.Column("headquarters_country", sa.String(100), nullable=False, server_default="India"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_industry_organizations_name", "industry_organizations", ["name"])

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("supabase_uid", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("role", sa.Enum("SUPER_ADMIN", "INSTITUTION_ADMIN", "FACULTY", "STUDENT", "INDUSTRY_ADMIN", "RECRUITER", name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_onboarded", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("industry_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supabase_uid"),
        sa.UniqueConstraint("email"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["industry_org_id"], ["industry_organizations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_users_supabase_uid", "users", ["supabase_uid"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_institution_id", "users", ["institution_id"])
    op.create_index("ix_users_industry_org_id", "users", ["industry_org_id"])

    # ── updated_at trigger function ───────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    for table in ["institutions", "industry_organizations", "users"]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    for table in ["institutions", "industry_organizations", "users"]:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON {table};")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    op.drop_table("users")
    op.drop_table("industry_organizations")
    op.drop_table("institutions")

    op.execute("DROP TYPE IF EXISTS user_role;")
    op.execute("DROP TYPE IF EXISTS institution_type;")
