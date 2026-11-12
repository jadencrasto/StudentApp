"""phase_8b_performance_indexes

Revision ID: 2c8f1e4b9a7d
Revises: 1a8c9e4b2d5f
Create Date: 2026-11-12 01:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2c8f1e4b9a7d'
down_revision: Union[str, Sequence[str], None] = '1a8c9e4b2d5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 4 performance composite indexes for hot query and sort patterns (additive only)."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. College events: institution + event_date (eliminates sequential scans on events)
    op.execute("CREATE INDEX IF NOT EXISTS ix_college_events_inst_date ON college_events (institution_id, event_date ASC)")

    # 2. Assignments: user_id + deadline + id (eliminates in-memory sort on user assignments)
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignments_user_deadline ON assignments (user_id, deadline ASC, id ASC)")

    # 3. Alerts: unread alerts by user ordered by newest first
    if is_postgres:
        op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_user_unread ON alerts (user_id, created_at DESC) WHERE is_read = false")
    else:
        op.execute("CREATE INDEX IF NOT EXISTS ix_alerts_user_unread ON alerts (user_id, is_read, created_at DESC)")

    # 4. Chat messages: conversation_id + created_at (eliminates in-memory sort on messages)
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_conv_created ON chat_messages (conversation_id, created_at ASC)")


def downgrade() -> None:
    """Drop the 4 performance composite indexes."""
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_conv_created")
    op.execute("DROP INDEX IF EXISTS ix_alerts_user_unread")
    op.execute("DROP INDEX IF EXISTS ix_assignments_user_deadline")
    op.execute("DROP INDEX IF EXISTS ix_college_events_inst_date")

