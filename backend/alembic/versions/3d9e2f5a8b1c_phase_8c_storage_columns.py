"""phase_8c_storage_columns

Revision ID: 3d9e2f5a8b1c
Revises: 2c8f1e4b9a7d
Create Date: 2026-11-12 13:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3d9e2f5a8b1c'
down_revision: Union[str, Sequence[str], None] = '2c8f1e4b9a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable storage_path and storage_bucket columns (strictly additive)."""
    # 1. documents table
    op.add_column('documents', sa.Column('storage_path', sa.String(length=600), nullable=True))
    op.add_column('documents', sa.Column('storage_bucket', sa.String(length=100), nullable=True))

    # 2. class_timetables table
    op.add_column('class_timetables', sa.Column('image_storage_path', sa.String(length=600), nullable=True))
    op.add_column('class_timetables', sa.Column('image_storage_bucket', sa.String(length=100), nullable=True))

    # 3. timetable_documents table
    op.add_column('timetable_documents', sa.Column('storage_path', sa.String(length=600), nullable=True))
    op.add_column('timetable_documents', sa.Column('storage_bucket', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Drop the added columns if rolled back."""
    op.drop_column('timetable_documents', 'storage_bucket')
    op.drop_column('timetable_documents', 'storage_path')
    op.drop_column('class_timetables', 'image_storage_bucket')
    op.drop_column('class_timetables', 'image_storage_path')
    op.drop_column('documents', 'storage_bucket')
    op.drop_column('documents', 'storage_path')

