"""Portal identities, student submissions, durable AI run/budget ledger."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('student_accounts', sa.Column('user_id',sa.String(40),sa.ForeignKey('users.id'),primary_key=True),sa.Column('student_id',sa.String(40),sa.ForeignKey('students.id'),nullable=False,unique=True))
    op.create_table('student_submissions',sa.Column('intervention_id',sa.String(40),sa.ForeignKey('interventions.id'),primary_key=True),sa.Column('student_id',sa.String(40),sa.ForeignKey('students.id'),nullable=False),sa.Column('notes',sa.Text(),nullable=False),sa.Column('created',sa.Integer(),nullable=False))
    op.create_table('ai_budgets',sa.Column('class_id',sa.String(40),sa.ForeignKey('classes.id'),primary_key=True),sa.Column('period',sa.String(7),primary_key=True),sa.Column('committed_idr',sa.Integer(),nullable=False))
    op.create_table('ai_runs',sa.Column('id',sa.String(40),primary_key=True),sa.Column('class_id',sa.String(40),sa.ForeignKey('classes.id'),nullable=False),sa.Column('student_id',sa.String(40),sa.ForeignKey('students.id'),nullable=False),sa.Column('key',sa.String(80),nullable=False),sa.Column('provider',sa.String(20),nullable=False),sa.Column('model',sa.String(100),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('reserved_idr',sa.Integer(),nullable=False),sa.Column('cost_idr',sa.Integer(),nullable=False),sa.Column('input_tokens',sa.Integer(),nullable=False),sa.Column('output_tokens',sa.Integer(),nullable=False),sa.Column('latency_ms',sa.Integer(),nullable=False),sa.Column('intervention_id',sa.String(40),sa.ForeignKey('interventions.id'),nullable=True),sa.Column('created',sa.Integer(),nullable=False),sa.UniqueConstraint('class_id','key'))

def downgrade():
    for table in ['ai_runs','ai_budgets','student_submissions','student_accounts']:
        op.drop_table(table)
