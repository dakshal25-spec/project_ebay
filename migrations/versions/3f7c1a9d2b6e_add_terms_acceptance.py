"""Add terms acceptance tracking to users

Revision ID: 3f7c1a9d2b6e
Revises: 1a748238a822
Create Date: 2026-07-15 09:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f7c1a9d2b6e'
down_revision = '1a748238a822'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('terms_accepted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('terms_version', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('terms_version')
        batch_op.drop_column('terms_accepted_at')
