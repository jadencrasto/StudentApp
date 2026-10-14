"""phase_6c_class_timetable

Revision ID: d2e8b3f5a7c1
Revises: c1f7a8e2b9d4
Create Date: 2026-10-14 19:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e8b3f5a7c1'
down_revision: Union[str, Sequence[str], None] = 'c1f7a8e2b9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'class_timetables',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('institution_id', sa.Uuid(as_uuid=True), sa.ForeignKey('institutions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cohort_id', sa.Uuid(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('entries', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('image_path', sa.String(500), nullable=True),
        sa.Column('created_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index('ix_class_timetable_institution', 'class_timetables', ['institution_id'])
    op.create_index('ix_class_timetable_cohort', 'class_timetables', ['cohort_id'])
    op.create_index('ix_class_timetable_status', 'class_timetables', ['status'])
    op.create_index('ix_class_timetable_cohort_status', 'class_timetables', ['cohort_id', 'status'])

    # Only one published timetable per cohort and only one draft per cohort
    op.create_index(
        'uq_one_published_per_cohort',
        'class_timetables',
        ['cohort_id'],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
        sqlite_where=sa.text("status = 'published'")
    )
    op.create_index(
        'uq_one_draft_per_cohort',
        'class_timetables',
        ['cohort_id'],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
        sqlite_where=sa.text("status = 'draft'")
    )


def downgrade() -> None:
    op.drop_table('class_timetables')
