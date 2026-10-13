"""phase_5a_roles_institutions_rls

Revision ID: 7c9a1e3b5d8f
Revises: 693688620525
Create Date: 2026-10-13 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c9a1e3b5d8f'
down_revision: Union[str, Sequence[str], None] = '693688620525'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 1. Create institutions table
    op.create_table(
        'institutions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('join_code', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1' if is_sqlite else 'true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('institutions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_institutions_join_code'), ['join_code'], unique=True)

    # 2. Create cohorts table
    op.create_table(
        'cohorts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('institution_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('level_type', sa.String(length=50), nullable=False),
        sa.Column('level_value', sa.String(length=50), nullable=False),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('academic_year', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1' if is_sqlite else 'true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('institution_id', 'name', 'academic_year', name='uq_institution_cohort_academic_year')
    )
    with op.batch_alter_table('cohorts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cohorts_institution_id'), ['institution_id'], unique=False)

    # 3. Create join_requests table
    op.create_table(
        'join_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('institution_id', sa.Uuid(), nullable=False),
        sa.Column('requested_cohort_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('decided_by', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['institution_id'], ['institutions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_cohort_id'], ['cohorts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('join_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_join_requests_institution_id'), ['institution_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_join_requests_user_id'), ['user_id'], unique=False)

    # 4. Add new columns to users table (additive only)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=30), server_default='student', nullable=False))
        batch_op.add_column(sa.Column('institution_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('cohort_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False))
        batch_op.add_column(sa.Column('onboarding_completed', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False))
        batch_op.add_column(sa.Column('education_level', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('grade_or_year', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('location', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('institution_name_text', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('extra_info', sa.JSON(), nullable=True))
        batch_op.create_foreign_key('fk_users_institution_id', 'institutions', ['institution_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_users_cohort_id', 'cohorts', ['cohort_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index(batch_op.f('ix_users_institution_id'), ['institution_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_cohort_id'), ['cohort_id'], unique=False)

    # 5. Enable Row Level Security (RLS) on new tables for PostgreSQL
    if bind.dialect.name == "postgresql":
        for table in ["institutions", "cohorts", "join_requests"]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ["join_requests", "cohorts", "institutions"]:
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_cohort_id'))
        batch_op.drop_index(batch_op.f('ix_users_institution_id'))
        batch_op.drop_constraint('fk_users_cohort_id', type_='foreignkey')
        batch_op.drop_constraint('fk_users_institution_id', type_='foreignkey')
        batch_op.drop_column('extra_info')
        batch_op.drop_column('institution_name_text')
        batch_op.drop_column('location')
        batch_op.drop_column('grade_or_year')
        batch_op.drop_column('education_level')
        batch_op.drop_column('onboarding_completed')
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('cohort_id')
        batch_op.drop_column('institution_id')
        batch_op.drop_column('role')

    op.drop_table('join_requests')
    op.drop_table('cohorts')
    op.drop_table('institutions')
