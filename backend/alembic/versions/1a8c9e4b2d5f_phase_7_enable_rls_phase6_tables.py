"""phase_7_enable_rls_phase6_tables

Revision ID: 1a8c9e4b2d5f
Revises: f5b7c3e1a9d2
Create Date: 2026-11-09 18:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a8c9e4b2d5f'
down_revision: Union[str, Sequence[str], None] = 'f5b7c3e1a9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    "class_attendance_records",
    "class_attendance_change_logs",
    "class_timetables",
    "exams",
    "marks",
    "mark_change_records",
]


def upgrade() -> None:
    """Enable Row Level Security (RLS) on Phase 6 tables with no public policies."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        insp = sa.inspect(bind)
        existing_tables = set(insp.get_table_names())
        for table in TABLES:
            if table in existing_tables:
                op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable Row Level Security (RLS) on Phase 6 tables."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        insp = sa.inspect(bind)
        existing_tables = set(insp.get_table_names())
        for table in TABLES:
            if table in existing_tables:
                op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

