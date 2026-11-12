"""add cover_photo_id to events

Revision ID: 0006_add_event_cover_photo
Revises: 0005_create_join_requests
Create Date: 2026-11-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_add_event_cover_photo'
down_revision: Union[str, Sequence[str], None] = '0005_create_join_requests'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('events', sa.Column('cover_photo_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_events_cover_photo_id',
        'events',
        'photos',
        ['cover_photo_id'],
        ['id'],
        ondelete='SET NULL',
    )
    # Default existing events with photos to their earliest uploaded photo.
    op.execute(
        """
        UPDATE events
        SET cover_photo_id = (
            SELECT id FROM photos
            WHERE photos.event_id = events.id
            ORDER BY uploaded_at ASC
            LIMIT 1
        )
        WHERE cover_photo_id IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_events_cover_photo_id', 'events', type_='foreignkey')
    op.drop_column('events', 'cover_photo_id')

