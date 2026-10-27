"""1.0.1 security release: MFA, idle sessions, security log, respondent reference

Revision ID: 0002_security
Revises: 0001_initial
Create Date: 2026-10-27
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "0002_security"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("mfa_secret", sa.String(64), nullable=True))
        b.add_column(sa.Column("mfa_pending_secret", sa.String(64), nullable=True))
        b.add_column(sa.Column("mfa_last_step", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("sessions") as b:
        b.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("mfa_state", sa.String(10), nullable=False, server_default="ok"))
    op.execute("UPDATE sessions SET last_seen_at = created_at")
    with op.batch_alter_table("invitations") as b:
        b.add_column(sa.Column("reference", sa.String(20), nullable=False, server_default=""))
    # Give every existing survey its own reference (1.0.0 derived it from the link token).
    conn = op.get_bind()
    for (iid,) in conn.execute(sa.text("SELECT id FROM invitations")).fetchall():
        ref = "QEA-" + "".join(secrets.choice(ALPHABET) for _ in range(8))
        conn.execute(sa.text("UPDATE invitations SET reference = :r WHERE id = :i"), {"r": ref, "i": iid})
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("actor", sa.String(254), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    op.create_index("ix_security_events_at", "security_events", ["at"])
    op.create_index("ix_security_events_kind", "security_events", ["kind"])
    op.create_index("ix_security_events_actor", "security_events", ["actor"])
    op.create_index("ix_security_events_ip", "security_events", ["ip"])


def downgrade() -> None:
    op.drop_index("ix_security_events_ip", "security_events")
    op.drop_index("ix_security_events_actor", "security_events")
    op.drop_index("ix_security_events_kind", "security_events")
    op.drop_index("ix_security_events_at", "security_events")
    op.drop_table("security_events")
    with op.batch_alter_table("invitations") as b:
        b.drop_column("reference")
    with op.batch_alter_table("sessions") as b:
        b.drop_column("mfa_state")
        b.drop_column("last_seen_at")
    with op.batch_alter_table("users") as b:
        b.drop_column("mfa_last_step")
        b.drop_column("mfa_pending_secret")
        b.drop_column("mfa_secret")
