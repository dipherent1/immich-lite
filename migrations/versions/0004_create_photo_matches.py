"""create photo_matches

Revision ID: 0004_create_photo_matches
Revises: 0003_create_photos
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_create_photo_matches'
down_revision: Union[str, Sequence[str], None] = '0003_create_photos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'photo_matches',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('photo_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=False),
        sa.Column('bbox', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('photo_id', 'user_id', name='uq_photo_matches_photo_user'),
    )
    op.create_index(op.f('ix_photo_matches_id'), 'photo_matches', ['id'], unique=False)
    op.create_index(op.f('ix_photo_matches_photo_id'), 'photo_matches', ['photo_id'], unique=False)
    op.create_index(op.f('ix_photo_matches_user_id'), 'photo_matches', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_photo_matches_user_id'), table_name='photo_matches')
    op.drop_index(op.f('ix_photo_matches_photo_id'), table_name='photo_matches')
    op.drop_index(op.f('ix_photo_matches_id'), table_name='photo_matches')
    op.drop_table('photo_matches')
