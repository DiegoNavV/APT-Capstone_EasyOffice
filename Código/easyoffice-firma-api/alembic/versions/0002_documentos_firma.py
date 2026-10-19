"""Documentos, firmantes, auditoría, idempotencia y webhooks.

Revision ID: 0002_documentos_firma
Revises: 0001_base
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_documentos_firma"
down_revision = "0001_base"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("external_ref", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("client_verification", sa.String(20), nullable=False),
        sa.Column("original_key", sa.String(200), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False),
        sa.Column("signed_key", sa.String(200)),
        sa.Column("signed_sha256", sa.String(64)),
        sa.Column("signature_type", sa.String(20)),
        sa.Column("callback_url", sa.String(500)),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ),
        sa.Column("completed_at", TZ),
        sa.Column("cancelled_at", TZ),
        sa.Column("rejected_at", TZ),
        sa.Column("expired_at", TZ),
    )
    op.create_index("ix_documents_client_id", "documents", ["client_id"])
    op.create_index("ix_documents_external_ref", "documents", ["external_ref"])
    op.create_index("ix_documents_original_sha256", "documents", ["original_sha256"])
    op.create_index("ix_documents_signed_sha256", "documents", ["signed_sha256"])
    op.create_index("ix_documents_expires_at", "documents", ["expires_at"])

    op.create_table(
        "signers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(150)),
        sa.Column("rut", sa.String(15)),
        sa.Column("represents_name", sa.String(200)),
        sa.Column("represents_rut", sa.String(15)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("signed_at", TZ),
        sa.Column("evidence", sa.JSON, nullable=False),
    )
    op.create_index("ix_signers_document_id", "signers", ["document_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(36)),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_audit_events_document_id", "audit_events", ["document_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=False),
        sa.Column("response_body", sa.JSON, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_status_code", sa.Integer),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("delivered_at", TZ),
    )
    op.create_index("ix_webhook_deliveries_document_id", "webhook_deliveries", ["document_id"])

    # La auditoría es append-only también a nivel de base de datos (solo Postgres).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION audit_events_inmutable() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'audit_events es append-only: no se permite %', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_events_no_update_delete
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_inmutable();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS audit_events_inmutable()")
    op.drop_table("webhook_deliveries")
    op.drop_table("idempotency_keys")
    op.drop_table("audit_events")
    op.drop_table("signers")
    op.drop_table("documents")
