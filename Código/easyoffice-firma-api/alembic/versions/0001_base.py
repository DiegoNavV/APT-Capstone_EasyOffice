"""Base: punto de partida de las migraciones (Fase 0, sin tablas).

Las tablas de cada fase se agregan como migraciones nuevas sobre esta.

Revision ID: 0001_base
Revises:
Create Date: 2026-10-08
"""

revision = "0001_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
