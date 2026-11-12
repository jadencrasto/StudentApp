"""phase 8d rate limit events

Revision ID: 4e1f7c8b9a2d
Revises: 3d9e2f5a8b1c
Create Date: 2026-11-12 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4e1f7c8b9a2d'
down_revision: Union[str, None] = '3d9e2f5a8b1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create rate_limit_events table
    op.create_table(
        'rate_limit_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('scope', sa.String(length=50), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    # 2. Composite lookup index
    op.create_index(
        'ix_rate_limit_events_lookup',
        'rate_limit_events',
        ['scope', 'key', 'timestamp'],
        unique=False
    )
    # 3. Enable Row Level Security (PostgreSQL)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TABLE rate_limit_events ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index('ix_rate_limit_events_lookup', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')

