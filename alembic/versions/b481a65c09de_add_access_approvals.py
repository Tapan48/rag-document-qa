"""add access approvals and email delivery tracking

Revision ID: b481a65c09de
Revises: 743ce2f30300
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b481a65c09de"
down_revision = "743ce2f30300"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("token_version", postgresql.UUID(as_uuid=True)),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','approved','rejected','registered')", name="ck_access_request_status"),
    )
    op.create_index("ix_access_requests_email", "access_requests", ["email"], unique=True)
    op.create_table(
        "access_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("token_version", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('notification','invitation')", name="ck_access_email_kind"),
        sa.CheckConstraint("status IN ('pending','retrying','sent','failed','cancelled')", name="ck_access_email_status"),
    )
    op.create_index("ix_access_emails_request_id", "access_emails", ["request_id"])


def downgrade():
    op.drop_table("access_emails")
    op.drop_table("access_requests")
    op.drop_column("users", "is_admin")
