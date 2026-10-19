"""phase_6e_college_events

Revision ID: f5b7c3e1a9d2
Revises: e3a9c4d2b1f8
Create Date: 2026-10-20 00:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f5b7c3e1a9d2'
down_revision: Union[str, Sequence[str], None] = 'e3a9c4d2b1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    
    if 'college_events' in insp.get_table_names():
        columns = [c['name'] for c in insp.get_columns('college_events')]
        
        if 'institution_id' not in columns:
            op.add_column('college_events', sa.Column('institution_id', sa.Uuid(as_uuid=True), sa.ForeignKey('institutions.id', ondelete='CASCADE'), nullable=True))
        if 'is_hidden' not in columns:
            op.add_column('college_events', sa.Column('is_hidden', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        if 'is_manual' not in columns:
            op.add_column('college_events', sa.Column('is_manual', sa.Boolean(), server_default=sa.text('false'), nullable=False))
            
        if bind.dialect.name == 'postgresql':
            # Drop old indexes if they exist
            op.execute("DROP INDEX IF EXISTS uq_college_events_dedupe;")
            op.execute("DROP INDEX IF EXISTS uq_college_events_dedup;")
            # Create single correct unique index (includes college when institution_id IS NULL)
            op.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_college_events_dedup ON college_events (
                    COALESCE(institution_id, '00000000-0000-0000-0000-000000000000'::uuid),
                    (CASE WHEN institution_id IS NULL THEN LOWER(TRIM(COALESCE(college, ''))) ELSE '' END),
                    LOWER(REGEXP_REPLACE(TRIM(event_name), '\\s+', ' ', 'g')),
                    COALESCE(TRIM(event_date), '')
                );
            """)
        else:
            # SQLite fallback
            try:
                op.execute("DROP INDEX IF EXISTS uq_college_events_dedupe;")
                op.execute("DROP INDEX IF EXISTS uq_college_events_dedup;")
                op.create_index(
                    'uq_college_events_dedup',
                    'college_events',
                    ['institution_id', 'college', 'event_name', 'event_date'],
                    unique=True
                )
            except Exception:
                pass


def downgrade() -> None:
    pass
