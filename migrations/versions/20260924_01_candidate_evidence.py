"""Create citation-backed candidate evidence retrieval storage.

Revision ID: 20260924_01
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "20260924_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "candidate_evidence",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("profile_id", sa.String(length=80), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("skill_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("skill_text", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=32), server_default="public", nullable=False),
        sa.Column("embedding", VECTOR(dim=192), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(claim, '') || ' ' || coalesce(skill_text, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", "profile_id"),
    )
    op.create_index(
        "ix_candidate_evidence_profile",
        "candidate_evidence",
        ["profile_id"],
    )
    op.create_index(
        "ix_candidate_evidence_search_vector",
        "candidate_evidence",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute(
        "CREATE INDEX ix_candidate_evidence_embedding_hnsw "
        "ON candidate_evidence USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_evidence_embedding_hnsw", table_name="candidate_evidence")
    op.drop_index("ix_candidate_evidence_search_vector", table_name="candidate_evidence")
    op.drop_index("ix_candidate_evidence_profile", table_name="candidate_evidence")
    op.drop_table("candidate_evidence")
