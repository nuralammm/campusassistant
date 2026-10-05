from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("interventions", sa.Column("followup_json", sa.Text(), nullable=False, server_default="{}"))

def downgrade():
    with op.batch_alter_table("interventions") as batch:
        batch.drop_column("followup_json")
