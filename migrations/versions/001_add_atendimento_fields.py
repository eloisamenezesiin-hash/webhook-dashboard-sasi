"""Add comunicante, status, concluded_at to webhook_events and status columns to summaries

Revision ID: 001_atendimento
Revises:
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa


revision = "001_atendimento"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- webhook_events: novos campos de atendimento ---
    op.add_column("webhook_events", sa.Column("comunicante", sa.String(200), nullable=True))
    op.add_column("webhook_events", sa.Column("status", sa.String(50), nullable=True, server_default="aberto"))
    op.add_column("webhook_events", sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_webhook_events_comunicante", "webhook_events", ["comunicante"])
    op.create_index("ix_events_app_status", "webhook_events", ["app", "status"])

    # --- events_summary_hourly: indicadores de atendimento ---
    op.add_column("events_summary_hourly", sa.Column("abertos", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_hourly", sa.Column("em_andamento", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_hourly", sa.Column("concluidos", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_hourly", sa.Column("tempo_medio_resposta_min", sa.Numeric(10, 2), nullable=True))

    # --- events_summary_daily: indicadores de atendimento ---
    op.add_column("events_summary_daily", sa.Column("abertos", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_daily", sa.Column("em_andamento", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_daily", sa.Column("concluidos", sa.Integer, nullable=False, server_default="0"))
    op.add_column("events_summary_daily", sa.Column("comunicantes_unicos", sa.Integer, nullable=True, server_default="0"))
    op.add_column("events_summary_daily", sa.Column("tempo_medio_resposta_min", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("events_summary_daily", "tempo_medio_resposta_min")
    op.drop_column("events_summary_daily", "comunicantes_unicos")
    op.drop_column("events_summary_daily", "concluidos")
    op.drop_column("events_summary_daily", "em_andamento")
    op.drop_column("events_summary_daily", "abertos")
    op.drop_column("events_summary_hourly", "tempo_medio_resposta_min")
    op.drop_column("events_summary_hourly", "concluidos")
    op.drop_column("events_summary_hourly", "em_andamento")
    op.drop_column("events_summary_hourly", "abertos")
    op.drop_index("ix_events_app_status", "webhook_events")
    op.drop_index("ix_webhook_events_comunicante", "webhook_events")
    op.drop_column("webhook_events", "concluded_at")
    op.drop_column("webhook_events", "status")
    op.drop_column("webhook_events", "comunicante")
