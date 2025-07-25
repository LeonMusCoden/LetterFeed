"""add auth to settings

Revision ID: ce35472309a4
Revises: fb190ac6937f
Create Date: 2025-07-17 22:45:31.442679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce35472309a4'
down_revision: Union[str, Sequence[str], None] = 'fb190ac6937f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('settings', sa.Column('auth_username', sa.String(), nullable=True))
    op.add_column('settings', sa.Column('auth_password_hash', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('settings', 'auth_password_hash')
    op.drop_column('settings', 'auth_username')
    # ### end Alembic commands ###
