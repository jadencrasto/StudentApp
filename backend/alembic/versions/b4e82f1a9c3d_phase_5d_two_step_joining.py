"""phase_5d_two_step_joining

Revision ID: b4e82f1a9c3d
Revises: 9a3d7f1e4c2b
Create Date: 2026-10-14 18:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e82f1a9c3d'
down_revision: Union[str, Sequence[str], None] = '9a3d7f1e4c2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 1. Add request_type column (default 'institution')
    server_default = sa.text("'institution'")
    op.add_column(
        'join_requests',
        sa.Column('request_type', sa.String(length=30), nullable=False, server_default=server_default)
    )

    # 2. Backfill:
    # Any request for a student with NO institution_id MUST be an 'institution' request with requested_cohort_id = NULL.
    # Convert old combined flow requests (pending or historical without institution) to plain institution requests.
    try:
        bind.execute(sa.text("""
            UPDATE join_requests
            SET request_type = 'institution', requested_cohort_id = NULL
            WHERE id IN (
                SELECT jr.id FROM join_requests jr
                JOIN users u ON jr.user_id = u.id
                WHERE u.institution_id IS NULL AND jr.requested_cohort_id IS NOT NULL
            )
        """))

        # Any request for a student who was already enrolled in an institution and requested a cohort becomes 'class'
        bind.execute(sa.text("""
            UPDATE join_requests
            SET request_type = 'class'
            WHERE id IN (
                SELECT jr.id FROM join_requests jr
                JOIN users u ON jr.user_id = u.id
                WHERE u.institution_id IS NOT NULL AND jr.requested_cohort_id IS NOT NULL
            )
        """))
    except Exception:
        pass


def downgrade() -> None:
    op.drop_column('join_requests', 'request_type')
