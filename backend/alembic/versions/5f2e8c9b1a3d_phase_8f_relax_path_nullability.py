"""phase_8f_relax_path_nullability

Revision ID: 5f2e8c9b1a3d
Revises: 4e1f7c8b9a2d
Create Date: 2026-11-13 15:30:00.000000

Additive migration to relax legacy NOT NULL constraint on timetable_documents.file_path.
Allows cloud-first and fake-storage uploads where files reside in object storage
without requiring a local file system path mirror.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5f2e8c9b1a3d'
down_revision: Union[str, Sequence[str], None] = '4e1f7c8b9a2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Relax NOT NULL constraint on timetable_documents.file_path (strictly additive/relaxing)."""
    op.alter_column(
        'timetable_documents',
        'file_path',
        existing_type=sa.String(length=600),
        nullable=True,
    )


def downgrade() -> None:
    """
    Restore NOT NULL constraint on timetable_documents.file_path.
    Backfills any NULL entries with an empty string so downgrade does not fail.
    """
    op.execute("UPDATE timetable_documents SET file_path = '' WHERE file_path IS NULL")
    op.alter_column(
        'timetable_documents',
        'file_path',
        existing_type=sa.String(length=600),
        nullable=False,
    )

