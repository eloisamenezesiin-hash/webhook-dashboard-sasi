"""
Model principal: webhook_events
Armazena todos os eventos recebidos via webhook do SASI.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, DateTime, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class WebhookEvent(Base):
    """Tabela principal de eventos recebidos via webhook."""

    __tablename__ = "webhook_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # --- Campos normalizados (padrão do skill webhook-normalizacao) ---
    app = Column(String(100), nullable=False, index=True, comment="App/sistema de origem")
    canal = Column(String(100), nullable=True, comment="Canal de envio")
    evento = Column(String(100), nullable=False, index=True, comment="Tipo do evento")
    usuario = Column(String(200), nullable=True, comment="Usuário associado")
    valor = Column(Numeric(15, 2), nullable=True, comment="Valor numérico do evento")

    # --- Campos de atendimento (dashboard departamental) ---
    comunicante = Column(String(200), nullable=True, index=True, comment="Pessoa que reportou/comunicou")
    status = Column(String(50), nullable=True, index=True, default="aberto", comment="Status do atendimento: aberto, em_andamento, concluido")
    concluded_at = Column(DateTime(timezone=True), nullable=True, comment="Quando o atendimento foi concluído")

    # --- Dados extras ---
    metadata_ = Column("metadata", JSONB, nullable=True, default={}, comment="Dados adicionais preservados")
    raw_payload = Column(JSONB, nullable=False, comment="Payload original recebido (backup)")

    # --- Timestamps ---
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="Quando o webhook foi recebido",
    )
    processed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Quando o worker processou o evento",
    )

    # --- Índices compostos para queries do dashboard ---
    __table_args__ = (
        Index("ix_events_app_evento", "app", "evento"),
        Index("ix_events_received_at_app", "received_at", "app"),
        Index("ix_events_canal_received_at", "canal", "received_at"),
        Index("ix_events_app_status", "app", "status"),
        Index("ix_events_comunicante", "comunicante"),
    )

    def __repr__(self):
        return f"<WebhookEvent {self.app}/{self.evento} @ {self.received_at}>"
