"""2FA: columnas totp_secret / totp_habilitado en usuario

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("totp_secret", sa.String(32), nullable=True))
    op.add_column(
        "usuario", sa.Column("totp_habilitado", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("usuario", "totp_habilitado")
    op.drop_column("usuario", "totp_secret")
