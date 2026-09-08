"""Add the normalized commercial and billing model without removing legacy data."""

from alembic import op
import sqlalchemy as sa


revision = "20260908_01"
down_revision = "20260906_01"
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "clients" in tables:
        columns = _columns(inspector, "clients")
        with op.batch_alter_table("clients") as batch:
            if "legal_name" not in columns:
                batch.add_column(sa.Column("legal_name", sa.String(180), nullable=True))
            if "default_currency" not in columns:
                batch.add_column(sa.Column("default_currency", sa.String(3), nullable=False, server_default="CAD"))
            if "tax_identifiers" not in columns:
                batch.add_column(sa.Column("tax_identifiers", sa.Text(), nullable=True))

    if "engagements" in tables and "delivery_status" not in _columns(inspector, "engagements"):
        with op.batch_alter_table("engagements") as batch:
            batch.add_column(sa.Column("delivery_status", sa.String(24), nullable=True))
            batch.create_index("ix_engagements_delivery_status", ["delivery_status"])

    # create_all only creates missing tables. Existing identifiers, columns, routes,
    # and financial records are intentionally untouched by this migration.
    from Application.Users.Models import Base
    import Application.Clients.Models  # noqa: F401
    import Application.Engagements.Models  # noqa: F401
    import Application.Finance.Models  # noqa: F401

    Base.metadata.create_all(bind)


def downgrade() -> None:
    # Additive production migrations remain in place during an app rollback.
    # Removal is a separately reviewed release after reconciliation.
    pass
