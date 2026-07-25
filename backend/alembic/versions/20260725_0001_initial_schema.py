"""Initial local NARATrace schema."""

from __future__ import annotations

from alembic import op

revision = "20260725_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from naratrace.database.base import Base
    import naratrace.database.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from naratrace.database.base import Base
    import naratrace.database.models  # noqa: F401

    Base.metadata.drop_all(bind=op.get_bind())
