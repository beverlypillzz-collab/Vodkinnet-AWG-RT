"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("agent_port", sa.Integer, nullable=False),
        sa.Column("agent_token", sa.String(255), nullable=False),
        sa.Column("public_key", sa.String(255), nullable=True),
        sa.Column("listen_port", sa.Integer, nullable=False),
        sa.Column("awg_params", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("protocol_version", sa.String(20), nullable=False, server_default="2.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    router_type = postgresql.ENUM("openwrt", "keenetic", name="router_type")
    remote_hub_enum = postgresql.ENUM("owrt-remote", "netcraze-remote", name="remote_hub")
    router_type.create(op.get_bind(), checkfirst=True)
    remote_hub_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "routers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", postgresql.ENUM("openwrt", "keenetic", name="router_type", create_type=False), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("firmware_version", sa.String(100), nullable=True),
        sa.Column(
            "remote_hub",
            postgresql.ENUM("owrt-remote", "netcraze-remote", name="remote_hub", create_type=False),
            nullable=True,
        ),
        sa.Column("remote_hub_url", sa.String(255), nullable=True),
        sa.Column("awg_link_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "peers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("router_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("routers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("public_key", sa.String(255), nullable=False),
        sa.Column("allowed_ips", sa.String(100), nullable=False),
        sa.Column("awg_overrides", postgresql.JSONB, nullable=True),
        sa.Column("last_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rx_bytes", sa.BigInteger, server_default="0"),
        sa.Column("tx_bytes", sa.BigInteger, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("node_id", "public_key", name="uq_peer_node_pubkey"),
    )

    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admins.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("admins")
    op.drop_table("peers")
    op.drop_table("routers")
    op.drop_table("nodes")
    postgresql.ENUM(name="remote_hub").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="router_type").drop(op.get_bind(), checkfirst=True)
