"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}

def upgrade():
    from backend.app.main import Base
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    from backend.app.main import Base
    Base.metadata.drop_all(bind=op.get_bind())
