"""phase_6b_class_attendance

Revision ID: c1f7a8e2b9d4
Revises: b4e82f1a9c3d
Create Date: 2026-10-14 19:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1f7a8e2b9d4'
down_revision: Union[str, Sequence[str], None] = 'b4e82f1a9c3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create class_attendance_records table
    op.create_table(
        'class_attendance_records',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('institution_id', sa.Uuid(as_uuid=True), sa.ForeignKey('institutions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cohort_id', sa.Uuid(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('student_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('class_date', sa.Date(), nullable=False),
        sa.Column('subject_name', sa.String(length=100), nullable=False),
        sa.Column('subject_name_normalized', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('marked_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('cohort_id', 'student_id', 'class_date', 'subject_name_normalized', name='uq_cohort_student_date_subject'),
    )
    op.create_index('ix_class_attendance_cohort_date', 'class_attendance_records', ['cohort_id', 'class_date'])
    op.create_index('ix_class_attendance_student_cohort', 'class_attendance_records', ['student_id', 'cohort_id'])
    op.create_index('ix_class_attendance_records_inst_id', 'class_attendance_records', ['institution_id'])
    op.create_index('ix_class_attendance_records_cohort_id', 'class_attendance_records', ['cohort_id'])
    op.create_index('ix_class_attendance_records_student_id', 'class_attendance_records', ['student_id'])
    op.create_index('ix_class_attendance_records_class_date', 'class_attendance_records', ['class_date'])

    # 2. Create class_attendance_change_logs table
    op.create_table(
        'class_attendance_change_logs',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('record_id', sa.Uuid(as_uuid=True), sa.ForeignKey('class_attendance_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('changed_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('previous_status', sa.String(length=20), nullable=False),
        sa.Column('new_status', sa.String(length=20), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
    )
    op.create_index('ix_class_attendance_change_logs_record_id', 'class_attendance_change_logs', ['record_id'])


def downgrade() -> None:
    op.drop_table('class_attendance_change_logs')
    op.drop_table('class_attendance_records')
