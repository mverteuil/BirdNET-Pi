"""Baseline schema - BirdNET-Pi 2.0.0a

Revision ID: 3afaf6ab75f4
Revises:
Create Date: 2025-09-27 11:33:25.828371

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "3afaf6ab75f4"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # This is the baseline migration for BirdNET-Pi 2.0.0a
    # It represents the schema as it exists at the start of using Alembic
    # All tables already exist, so we just mark this revision as applied
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Cannot downgrade from baseline
    pass
