"""require conversation owners

Revision ID: 20260718_0003
Revises: 20260718_0002
Create Date: 2026-07-18

"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260718_0003"
down_revision: str | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This pre-production migration is intentionally destructive. These rows
    # cannot be attributed safely, and downgrade cannot restore them.
    op.execute("DELETE FROM messages")
    op.execute("DELETE FROM conversations")
    op.alter_column("conversations", "user_id", nullable=False)


def downgrade() -> None:
    # Schema-only downgrade; legacy conversations deleted by upgrade are lost.
    op.alter_column("conversations", "user_id", nullable=True)
