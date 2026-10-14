"""phase_6a_students_tab

Revision ID: 9a3d7f1e4c2b
Revises: 8e2b4f6a1c9d
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a3d7f1e4c2b'
down_revision: Union[str, Sequence[str], None] = '8e2b4f6a1c9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 1. Add created_by_admin column (default False)
    server_default_false = sa.text('0') if is_sqlite else sa.text('false')
    op.add_column(
        'users',
        sa.Column('created_by_admin', sa.Boolean(), nullable=False, server_default=server_default_false)
    )

    # 2. Add archived_at column (nullable DateTime)
    op.add_column(
        'users',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True)
    )

    # 3. Add password_changed_at column (nullable DateTime)
    op.add_column(
        'users',
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True)
    )

    # 4. Add token_version column (default 1)
    server_default_one = sa.text('1')
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default=server_default_one)
    )

    # 5. Create index on full_name for student search
    op.create_index('ix_users_full_name', 'users', ['full_name'], unique=False)

    # 6. Create compound index on (institution_id, role) for fast scoped queries
    op.create_index('ix_users_institution_role', 'users', ['institution_id', 'role'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_institution_role', table_name='users')
    op.drop_index('ix_users_full_name', table_name='users')
    op.drop_column('users', 'token_version')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'archived_at')
    op.drop_column('users', 'created_by_admin')
