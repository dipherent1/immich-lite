"""event expiry: warning flag + ON DELETE CASCADE from events/photos

Revision ID: 0007_event_expiry_cascade
Revises: 0006_add_event_cover_photo
Create Date: 2026-11-12 00:00:00.000000

Events now live 6 hours and are then deleted. Deleting the `events` row must take
its dependent rows with it, so the child foreign keys become ON DELETE CASCADE:
photos / event_attendees / join_requests -> events, photo_matches -> photos.
(events.cover_photo_id is already ON DELETE SET NULL.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007_event_expiry_cascade'
down_revision: Union[str, Sequence[str], None] = '0006_add_event_cover_photo'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, referred table) — constraint names are Postgres' defaults.
_FKS = [
    ('photos', 'event_id', 'events'),
    ('event_attendees', 'event_id', 'events'),
    ('join_requests', 'event_id', 'events'),
    ('photo_matches', 'photo_id', 'photos'),
]


def _name(table: str, column: str) -> str:
    return f'{table}_{column}_fkey'


def upgrade() -> None:
    op.add_column('events', sa.Column('expiry_warned_at', sa.DateTime(), nullable=True))
    op.create_index('ix_events_expires_at', 'events', ['expires_at'])
    for table, column, referred in _FKS:
        op.drop_constraint(_name(table, column), table, type_='foreignkey')
        op.create_foreign_key(
            _name(table, column), table, referred, [column], ['id'], ondelete='CASCADE'
        )


def downgrade() -> None:
    for table, column, referred in _FKS:
        op.drop_constraint(_name(table, column), table, type_='foreignkey')
        op.create_foreign_key(_name(table, column), table, referred, [column], ['id'])
    op.drop_index('ix_events_expires_at', table_name='events')
    op.drop_column('events', 'expiry_warned_at')
