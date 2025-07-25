"""add_slug_to_newsletter

Revision ID: 1ed7baeaf282
Revises: ce35472309a4
Create Date: 2025-07-24 12:32:05.618379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ed7baeaf282'
down_revision: Union[str, Sequence[str], None] = 'ce35472309a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_senders_email'), table_name='senders')
    op.drop_index(op.f('ix_senders_id'), table_name='senders')
    op.drop_table('senders')
    op.drop_index(op.f('ix_newsletters_id'), table_name='newsletters')
    op.drop_table('newsletters')
    op.drop_index(op.f('ix_settings_id'), table_name='settings')
    op.drop_index(op.f('ix_settings_imap_server'), table_name='settings')
    op.drop_table('settings')
    op.drop_index(op.f('ix_entries_id'), table_name='entries')
    op.drop_index(op.f('ix_entries_message_id'), table_name='entries')
    op.drop_table('entries')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('entries',
    sa.Column('id', sa.VARCHAR(), nullable=False),
    sa.Column('newsletter_id', sa.VARCHAR(), nullable=True),
    sa.Column('subject', sa.VARCHAR(), nullable=True),
    sa.Column('body', sa.TEXT(), nullable=True),
    sa.Column('received_at', sa.DATETIME(), nullable=True),
    sa.Column('message_id', sa.VARCHAR(), nullable=False),
    sa.ForeignKeyConstraint(['newsletter_id'], ['newsletters.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entries_message_id'), 'entries', ['message_id'], unique=1)
    op.create_index(op.f('ix_entries_id'), 'entries', ['id'], unique=False)
    op.create_table('settings',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('imap_server', sa.VARCHAR(), nullable=True),
    sa.Column('imap_username', sa.VARCHAR(), nullable=True),
    sa.Column('imap_password', sa.VARCHAR(), nullable=True),
    sa.Column('search_folder', sa.VARCHAR(), nullable=True),
    sa.Column('move_to_folder', sa.VARCHAR(), nullable=True),
    sa.Column('mark_as_read', sa.BOOLEAN(), nullable=True),
    sa.Column('email_check_interval', sa.INTEGER(), nullable=True),
    sa.Column('auto_add_new_senders', sa.BOOLEAN(), nullable=True),
    sa.Column('auth_username', sa.VARCHAR(), nullable=True),
    sa.Column('auth_password_hash', sa.VARCHAR(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_settings_imap_server'), 'settings', ['imap_server'], unique=False)
    op.create_index(op.f('ix_settings_id'), 'settings', ['id'], unique=False)
    op.create_table('newsletters',
    sa.Column('id', sa.VARCHAR(), nullable=False),
    sa.Column('name', sa.VARCHAR(), nullable=True),
    sa.Column('move_to_folder', sa.VARCHAR(), nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), nullable=True),
    sa.Column('extract_content', sa.BOOLEAN(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_newsletters_id'), 'newsletters', ['id'], unique=False)
    op.create_table('senders',
    sa.Column('id', sa.VARCHAR(), nullable=False),
    sa.Column('email', sa.VARCHAR(), nullable=False),
    sa.Column('newsletter_id', sa.VARCHAR(), nullable=False),
    sa.ForeignKeyConstraint(['newsletter_id'], ['newsletters.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_senders_id'), 'senders', ['id'], unique=False)
    op.create_index(op.f('ix_senders_email'), 'senders', ['email'], unique=1)
    # ### end Alembic commands ###
