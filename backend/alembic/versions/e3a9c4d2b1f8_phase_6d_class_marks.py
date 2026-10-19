"""phase_6d_class_marks

Revision ID: e3a9c4d2b1f8
Revises: d2e8b3f5a7c1
Create Date: 2026-10-19 23:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a9c4d2b1f8'
down_revision: Union[str, Sequence[str], None] = 'd2e8b3f5a7c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'exams' not in tables:
        op.create_table(
            'exams',
            sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column('institution_id', sa.Uuid(as_uuid=True), sa.ForeignKey('institutions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('cohort_id', sa.Uuid(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('exam_type', sa.String(50), nullable=False),
            sa.Column('title', sa.String(150), nullable=False),
            sa.Column('title_normalized', sa.String(150), nullable=False),
            sa.Column('subject', sa.String(100), nullable=False),
            sa.Column('subject_normalized', sa.String(100), nullable=False),
            sa.Column('max_marks', sa.Numeric(6, 2), nullable=False),
            sa.Column('exam_date', sa.Date(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
            sa.Column('created_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('cohort_id', 'exam_type', 'subject_normalized', 'title_normalized', name='uq_cohort_exam_type_subject_title'),
        )

    if 'marks' not in tables:
        op.create_table(
            'marks',
            sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column('exam_id', sa.Uuid(as_uuid=True), sa.ForeignKey('exams.id', ondelete='CASCADE'), nullable=False),
            sa.Column('student_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('marks_obtained', sa.Numeric(6, 2), nullable=True),
            sa.Column('is_absent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('entered_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('exam_id', 'student_id', name='uq_exam_student_mark'),
        )

    if 'mark_change_records' not in tables:
        op.create_table(
            'mark_change_records',
            sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column('mark_id', sa.Uuid(as_uuid=True), sa.ForeignKey('marks.id', ondelete='CASCADE'), nullable=False),
            sa.Column('exam_id', sa.Uuid(as_uuid=True), sa.ForeignKey('exams.id', ondelete='CASCADE'), nullable=False),
            sa.Column('student_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('changed_by', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('previous_marks', sa.Numeric(6, 2), nullable=True),
            sa.Column('new_marks', sa.Numeric(6, 2), nullable=True),
            sa.Column('previous_absent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('new_absent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('reason', sa.String(255), nullable=False),
            sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # Indexes
    if 'exams' in tables or 'exams' not in tables:
        existing_exam_idx = [idx['name'] for idx in insp.get_indexes('exams')] if 'exams' in tables else []
        if 'ix_exams_cohort_status' not in existing_exam_idx:
            op.create_index('ix_exams_cohort_status', 'exams', ['cohort_id', 'status'])
        if 'ix_exams_institution' not in existing_exam_idx:
            op.create_index('ix_exams_institution', 'exams', ['institution_id'])
        if 'ix_exams_cohort' not in existing_exam_idx:
            op.create_index('ix_exams_cohort', 'exams', ['cohort_id'])
        if 'ix_exams_status' not in existing_exam_idx:
            op.create_index('ix_exams_status', 'exams', ['status'])

    if 'marks' in tables or 'marks' not in tables:
        existing_marks_idx = [idx['name'] for idx in insp.get_indexes('marks')] if 'marks' in tables else []
        if 'ix_marks_exam' not in existing_marks_idx:
            op.create_index('ix_marks_exam', 'marks', ['exam_id'])
        if 'ix_marks_student' not in existing_marks_idx:
            op.create_index('ix_marks_student', 'marks', ['student_id'])
        if 'ix_marks_student_exam' not in existing_marks_idx:
            op.create_index('ix_marks_student_exam', 'marks', ['student_id', 'exam_id'])

    if 'mark_change_records' in tables or 'mark_change_records' not in tables:
        existing_mcr_idx = [idx['name'] for idx in insp.get_indexes('mark_change_records')] if 'mark_change_records' in tables else []
        if 'ix_mark_change_mark' not in existing_mcr_idx:
            op.create_index('ix_mark_change_mark', 'mark_change_records', ['mark_id'])
        if 'ix_mark_change_exam' not in existing_mcr_idx:
            op.create_index('ix_mark_change_exam', 'mark_change_records', ['exam_id'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'mark_change_records' in tables:
        op.drop_table('mark_change_records')
    if 'marks' in tables:
        op.drop_table('marks')
    if 'exams' in tables:
        op.drop_table('exams')
