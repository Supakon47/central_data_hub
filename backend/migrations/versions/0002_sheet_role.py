"""Record each sheet's role (object register or storage-location list).

Revision ID: 0002_sheet_role
Revises: 0001_baseline
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_sheet_role"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_sheet_configs") as batch:
        batch.add_column(sa.Column("role", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_sheet_configs") as batch:
        batch.drop_column("role")
