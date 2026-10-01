"""esquema de autenticación: rol, usuario, refresh_token

Revision ID: 0001
Revises:
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rol",
        sa.Column("id_rol", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(50), nullable=False, unique=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
    )

    op.create_table(
        "usuario",
        sa.Column("id_usuario", sa.Integer(), primary_key=True),
        sa.Column("id_rol", sa.Integer(), sa.ForeignKey("rol.id_rol"), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("email", sa.String(150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_creacion", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bloqueado_hasta", sa.DateTime(), nullable=True),
        sa.Column("ultimo_login", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_usuario_email", "usuario", ["email"])

    op.create_table(
        "refresh_token",
        sa.Column("id_refresh_token", sa.Integer(), primary_key=True),
        sa.Column("id_usuario", sa.Integer(), sa.ForeignKey("usuario.id_usuario"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expira_en", sa.DateTime(), nullable=False),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "reemplazado_por_id", sa.Integer(), sa.ForeignKey("refresh_token.id_refresh_token"), nullable=True
        ),
    )
    op.create_index("ix_refresh_token_id_usuario", "refresh_token", ["id_usuario"])
    op.create_index("ix_refresh_token_token_hash", "refresh_token", ["token_hash"])

    # Catálogo base: sin estas dos filas nadie puede tener cuenta.
    rol_table = sa.table("rol", sa.column("nombre", sa.String), sa.column("descripcion", sa.Text))
    op.bulk_insert(
        rol_table,
        [
            {"nombre": "administrador", "descripcion": "Acceso completo: todos los trámites, agentes y panel de KPIs"},
            {"nombre": "agente", "descripcion": "Gestiona sus propias solicitudes y trámites asignados"},
        ],
    )


def downgrade() -> None:
    op.drop_table("refresh_token")
    op.drop_table("usuario")
    op.drop_table("rol")
