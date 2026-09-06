"""Production baseline and workspace settings."""
from alembic import op
import sqlalchemy as sa

revision = "20260906_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # A new installation is created entirely from the current model metadata. For a
    # pre-migration prototype database, preserve records and add only new structures.
    if "users" not in tables:
        from Application.Users.Models import Base
        import Application.Activity.Models
        import Application.Clients.Models
        import Application.Engagements.Models
        import Application.Finance.Models
        import Application.Projects.Models
        import Application.Settings.Models
        import Application.Tasks.Models
        Base.metadata.create_all(bind)
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "must_change_password" not in user_columns:
            batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "session_version" not in user_columns:
            batch.add_column(sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    bind.execute(sa.text("UPDATE users SET role='Developer' WHERE role='Admin'"))
    bind.execute(sa.text("UPDATE users SET role='Outreach Manager' WHERE role='Manager'"))
    bind.execute(sa.text("UPDATE users SET role='Team Member' WHERE role='Member'"))

    if "workspace_settings" not in tables:
        op.create_table(
            "workspace_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("business_name", sa.String(160), nullable=False),
            sa.Column("legal_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("business_email", sa.String(255), nullable=False, server_default=""),
            sa.Column("business_phone", sa.String(60), nullable=False, server_default=""),
            sa.Column("address_line1", sa.String(240), nullable=False, server_default=""),
            sa.Column("city", sa.String(120), nullable=False, server_default=""),
            sa.Column("region", sa.String(120), nullable=False, server_default=""),
            sa.Column("postal_code", sa.String(30), nullable=False, server_default=""),
            sa.Column("country", sa.String(80), nullable=False, server_default=""),
            sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
            sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
            sa.Column("invoice_prefix", sa.String(20), nullable=False, server_default="WD-"),
            sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="15"),
            sa.Column("tax_information", sa.Text(), nullable=False, server_default=""),
            sa.Column("invoice_footer", sa.Text(), nullable=False, server_default="Thank you for your business."),
            sa.Column("next_invoice_number", sa.Integer(), nullable=False, server_default="1"),
            sa.CheckConstraint("id = 1", name="ck_workspace_settings_singleton"),
        )
        owner_count = bind.execute(sa.text("SELECT count(*) FROM users WHERE role IN ('Developer', 'Admin')")).scalar_one()
        if owner_count:
            next_invoice = 1
            if "invoices" in tables:
                next_invoice = bind.execute(sa.text("SELECT count(*) + 1 FROM invoices")).scalar_one()
            bind.execute(sa.text("""INSERT INTO workspace_settings
                (id,business_name,legal_name,business_email,business_phone,address_line1,city,region,postal_code,country,timezone,currency,invoice_prefix,payment_terms_days,tax_information,invoice_footer,next_invoice_number)
                VALUES (1,'WorkDesk','WorkDesk','','','','','','','','UTC','USD','WD-',15,'','Thank you for your business.',:next_invoice)"""), {"next_invoice": next_invoice})
    from Application.Users.Models import Base
    import Application.Activity.Models
    import Application.Clients.Models
    import Application.Engagements.Models
    import Application.Finance.Models
    import Application.Projects.Models
    import Application.Settings.Models
    import Application.Tasks.Models
    Base.metadata.create_all(bind)


def downgrade() -> None:
    # The production baseline is intentionally irreversible; restore a database
    # backup when rolling back an application release.
    pass
