"""enable_rls_on_all_tables

Revision ID: 693688620525
Revises: f44449773b72
Create Date: 2026-10-13 10:25:21.582937

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '693688620525'
down_revision: Union[str, Sequence[str], None] = 'f44449773b72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "users",
    "college_events",
    "activities",
    "documents",
    "google_tokens",
    "subjects",
    "timetable_documents",
    "assignments",
    "attendance_records",
    "chat_conversations",
    "timetable_entries",
    "alerts",
    "chat_messages",
]


def upgrade() -> None:
    """Enable Row Level Security (RLS) on all tables with no public policies."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable Row Level Security (RLS) on all tables."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
