"""Optional musical edition metadata; existing records stay unknown.

Revision ID: c2b20260919
Revises: c2a20260918
"""
from alembic import op
import sqlalchemy as sa

revision = "c2b20260919"
down_revision = "c2a20260918"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, length in (("label", 100), ("original_artist", 200), ("performer", 200), ("album", 200), ("release_date", 10)):
        op.add_column("scores", sa.Column("edition_" + name, sa.String(length), nullable=True))


def downgrade() -> None:
    # Dropping these columns would irreversibly erase user-entered edition data.
    raise RuntimeError("Export edition data or restore a verified pre-upgrade backup before reverting this migration.")
