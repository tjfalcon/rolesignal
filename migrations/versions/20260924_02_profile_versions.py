"""Add candidate profiles and immutable resume versions.

Revision ID: 20260924_02
Revises: 20260924_01
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_02"
down_revision: str | None = "20260924_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("headline", sa.Text(), server_default="", nullable=False),
        sa.Column("visibility", sa.String(length=32), server_default="private", nullable=False),
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
        sa.CheckConstraint(
            "visibility IN ('public', 'private')", name="ck_candidate_profiles_visibility"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=80), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "source_name", sa.String(length=255), server_default="Manual entry", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_resume_versions_status"
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "version_number", name="uq_resume_versions_profile_number"
        ),
    )
    op.create_index("ix_resume_versions_profile", "resume_versions", ["profile_id"])
    op.create_index(
        "uq_resume_versions_active_profile",
        "resume_versions",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.add_column("candidate_profiles", sa.Column("active_resume_version_id", sa.String(length=36)))
    op.create_foreign_key(
        "fk_candidate_profiles_active_resume_version",
        "candidate_profiles",
        "resume_versions",
        ["active_resume_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("candidate_evidence", sa.Column("resume_version_id", sa.String(length=36)))
    op.add_column(
        "candidate_evidence",
        sa.Column("approved", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_foreign_key(
        "fk_candidate_evidence_resume_version",
        "candidate_evidence",
        "resume_versions",
        ["resume_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_candidate_evidence_resume_version", "candidate_evidence", ["resume_version_id"]
    )

    op.execute(
        """
        INSERT INTO candidate_profiles (id, display_name, headline, visibility)
        VALUES
          ('demo-thomas', 'Thomas Falcon',
           'Senior full-stack engineer and technical lead building reliable applied-AI products.',
           'public'),
          ('synthetic', 'Fictional Sample Candidate',
           'Synthetic profile for product demonstrations.', 'public')
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO resume_versions
          (id, profile_id, version_number, label, status, source_name, activated_at)
        VALUES
          ('demo-thomas-v1', 'demo-thomas', 1, 'Sanitized baseline', 'active',
           'Sanitized public resume', now()),
          ('synthetic-v1', 'synthetic', 1, 'Fictional baseline', 'active',
           'Fictional sample profile', now())
        """
    )
    op.execute(
        """
        UPDATE candidate_profiles
        SET active_resume_version_id = CASE id
          WHEN 'demo-thomas' THEN 'demo-thomas-v1'
          WHEN 'synthetic' THEN 'synthetic-v1'
        END
        WHERE id IN ('demo-thomas', 'synthetic')
        """
    )
    op.execute(
        """
        UPDATE candidate_evidence
        SET resume_version_id = CASE profile_id
          WHEN 'demo-thomas' THEN 'demo-thomas-v1'
          WHEN 'synthetic' THEN 'synthetic-v1'
        END
        WHERE profile_id IN ('demo-thomas', 'synthetic')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_evidence_resume_version", table_name="candidate_evidence")
    op.drop_constraint(
        "fk_candidate_evidence_resume_version", "candidate_evidence", type_="foreignkey"
    )
    op.drop_column("candidate_evidence", "approved")
    op.drop_column("candidate_evidence", "resume_version_id")
    op.drop_constraint(
        "fk_candidate_profiles_active_resume_version", "candidate_profiles", type_="foreignkey"
    )
    op.drop_column("candidate_profiles", "active_resume_version_id")
    op.drop_index("uq_resume_versions_active_profile", table_name="resume_versions")
    op.drop_index("ix_resume_versions_profile", table_name="resume_versions")
    op.drop_table("resume_versions")
    op.drop_table("candidate_profiles")
