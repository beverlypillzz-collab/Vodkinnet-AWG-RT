"""
SQLAlchemy 2.0 async models for the AWG-RT panel.

Matches the schema agreed in docs/db-schema.md. If you change a field
here, update that doc in the same commit — it's the source of truth
for why each field exists, not just what type it is.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    _UUID_TYPE = PGUUID(as_uuid=True)
except ImportError:  # pragma: no cover
    _UUID_TYPE = String(36)


def _uuid_default() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class Node(Base):
    """An AmneziaWG server, running node-agent + amnezia-awg2."""

    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_TYPE, primary_key=True, default=_uuid_default)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_port: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_token: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False)
    awg_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    protocol_version: Mapped[str] = mapped_column(String(20), nullable=False, default="2.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    peers: Mapped[list["Peer"]] = relationship(back_populates="node", cascade="all, delete-orphan")


class Router(Base):
    """A client OpenWrt/Keenetic router — reference data only, no remote access."""

    __tablename__ = "routers"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_TYPE, primary_key=True, default=_uuid_default)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        Enum("openwrt", "keenetic", name="router_type"), nullable=False
    )
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remote_hub: Mapped[str | None] = mapped_column(
        Enum("owrt-remote", "netcraze-remote", name="remote_hub"), nullable=True
    )
    remote_hub_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    awg_link_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    last_handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    peers: Mapped[list["Peer"]] = relationship(back_populates="router")


class Peer(Base):
    """A WireGuard/AmneziaWG peer linking a router to a node."""

    __tablename__ = "peers"
    __table_args__ = (UniqueConstraint("node_id", "public_key", name="uq_peer_node_pubkey"),)

    id: Mapped[uuid.UUID] = mapped_column(_UUID_TYPE, primary_key=True, default=_uuid_default)
    node_id: Mapped[uuid.UUID] = mapped_column(
        _UUID_TYPE, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    router_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID_TYPE, ForeignKey("routers.id", ondelete="SET NULL"), nullable=True
    )
    public_key: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_ips: Mapped[str] = mapped_column(String(100), nullable=False)
    awg_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    tx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    node: Mapped["Node"] = relationship(back_populates="peers")
    router: Mapped["Router | None"] = relationship(back_populates="peers")


class Admin(Base):
    """A panel operator account."""

    __tablename__ = "admins"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_TYPE, primary_key=True, default=_uuid_default)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only record of admin actions, for accountability."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_TYPE, primary_key=True, default=_uuid_default)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID_TYPE, ForeignKey("admins.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(_UUID_TYPE, nullable=True)
    audit_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
