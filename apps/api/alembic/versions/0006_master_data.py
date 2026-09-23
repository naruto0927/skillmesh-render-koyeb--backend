"""Add GCAS-ready columns to institutions and request_status to industry_organizations

Revision ID: 0006_master_data
Revises: 0005_phase5_learning
Create Date: 2026-01-06 00:00:00.000000

Changes:
- institutions: add district, aishe_code, source, source_id (GCAS import ready)
- institutions: add pg_trgm index on name for fast ILIKE search
- industry_organizations: add request_status (pending/approved/rejected)
  for the "not listed" self-registration flow
- industry_organizations: add requested_by_email to track who requested it
- Both tables: add search-optimised indexes
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_master_data"
down_revision: Union[str, None] = "0005_phase5_learning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pg_trgm for trigram similarity search ──────────────────────────
    # Already created in init-db.sql for local dev, but run checkfirst on prod
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # ── institutions: GCAS-ready columns ─────────────────────────────────────
    op.add_column("institutions", sa.Column(
        "district", sa.String(100), nullable=True
    ))
    op.add_column("institutions", sa.Column(
        "aishe_code", sa.String(20), nullable=True
    ))
    # source: where this record came from ("manual", "gcas", "ugc", etc.)
    op.add_column("institutions", sa.Column(
        "source", sa.String(50), nullable=True, server_default="manual"
    ))
    # source_id: the ID in the external system (e.g. GCAS institution ID)
    op.add_column("institutions", sa.Column(
        "source_id", sa.String(100), nullable=True
    ))

    # Unique constraint on (source, source_id) so GCAS import is idempotent
    op.create_index(
        "ix_institutions_source_source_id",
        "institutions",
        ["source", "source_id"],
        unique=False,
    )
    # Partial unique index: unique source_id per source when source_id is not null
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_institutions_source_id
        ON institutions (source, source_id)
        WHERE source_id IS NOT NULL;
    """)

    # Trigram index for fast ILIKE name search (powers the searchable selector)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_institutions_name_trgm
        ON institutions USING gin (name gin_trgm_ops);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_institutions_district_trgm
        ON institutions USING gin (district gin_trgm_ops)
        WHERE district IS NOT NULL;
    """)

    # ── industry_organizations: request flow columns ───────────────────────────
    # request_status: NULL = platform-created/admin-added (always approved)
    #                 pending = user requested, awaiting admin review
    #                 approved = admin approved the request
    #                 rejected = admin rejected the request
    op.add_column("industry_organizations", sa.Column(
        "request_status", sa.String(20), nullable=True
    ))
    op.add_column("industry_organizations", sa.Column(
        "requested_by_email", sa.String(255), nullable=True
    ))
    op.add_column("industry_organizations", sa.Column(
        "request_notes", sa.Text, nullable=True
    ))

    # Trigram index for org name search
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_industry_organizations_name_trgm
        ON industry_organizations USING gin (name gin_trgm_ops);
    """)

    # Index for admins to review pending requests
    op.create_index(
        "ix_industry_organizations_request_status",
        "industry_organizations",
        ["request_status"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_industry_organizations_name_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_institutions_name_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_institutions_district_trgm;")
    op.execute("DROP INDEX IF EXISTS uq_institutions_source_id;")

    op.drop_index("ix_industry_organizations_request_status", "industry_organizations")
    op.drop_index("ix_institutions_source_source_id", "institutions")

    for col in ["request_status", "requested_by_email", "request_notes"]:
        op.drop_column("industry_organizations", col)

    for col in ["district", "aishe_code", "source", "source_id"]:
        op.drop_column("institutions", col)
