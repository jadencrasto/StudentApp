"""phase_5c_class_join_codes

Revision ID: 8e2b4f6a1c9d
Revises: 7c9a1e3b5d8f
Create Date: 2026-10-13 18:30:00.000000

"""
import secrets
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e2b4f6a1c9d'
down_revision: Union[str, Sequence[str], None] = '7c9a1e3b5d8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _generate_code(length: int = 8) -> str:
    return "".join(secrets.choice(CHARSET) for _ in range(length))


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 1. Add join_code column (nullable, unique, indexed)
    op.add_column(
        'cohorts',
        sa.Column('join_code', sa.String(length=32), nullable=True)
    )

    # 2. Add join_code_enabled column (default True)
    server_default = sa.text('1') if is_sqlite else sa.text('true')
    op.add_column(
        'cohorts',
        sa.Column('join_code_enabled', sa.Boolean(), nullable=False, server_default=server_default)
    )

    # 3. Create unique index on cohorts.join_code
    op.create_index('ix_cohorts_join_code', 'cohorts', ['join_code'], unique=True)

    # 4. Backfill existing cohorts with non-colliding 8-character codes
    # Collect all existing institution codes to avoid any collision
    used_codes = set()
    try:
        inst_rows = bind.execute(sa.text("SELECT join_code FROM institutions WHERE join_code IS NOT NULL")).fetchall()
        for r in inst_rows:
            if r[0]:
                used_codes.add(r[0].strip().upper())
    except Exception:
        pass

    cohort_rows = bind.execute(sa.text("SELECT id FROM cohorts WHERE join_code IS NULL")).fetchall()
    for row in cohort_rows:
        cohort_id = row[0]
        while True:
            candidate = _generate_code(8)
            if candidate not in used_codes:
                used_codes.add(candidate)
                break
        bind.execute(
            sa.text("UPDATE cohorts SET join_code = :code WHERE id = :id"),
            {"code": candidate, "id": cohort_id}
        )


def downgrade() -> None:
    op.drop_index('ix_cohorts_join_code', table_name='cohorts')
    op.drop_column('cohorts', 'join_code_enabled')
    op.drop_column('cohorts', 'join_code')
