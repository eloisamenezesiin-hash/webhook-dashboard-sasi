"""
Models de tabelas agregadas (summaries).
Dashboards leem daqui — nunca da tabela bruta.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, Index, UniqueConstraint

from app.database import Base


class EventSummaryHourly(Base):
    """Resumo de eventos agregados por hora."""

    __tablename__ = "events_summary_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hora = Column(DateTime(timezone=True), nullable=False, comment="Início da hora")
    app = Column(String(100), nullable=False)
    canal = Column(String(100), nullable=True)
    evento = Column(String(100), nullable=False)

    total_eventos = Column(Integer, nullable=False, default=0)
    soma_valores = Column(Numeric(15, 2), nullable=True, default=0)
    media_valores = Column(Numeric(15, 2), nullable=True, default=0)
    valor_min = Column(Numeric(15, 2), nullable=True)
    valor_max = Column(Numeric(15, 2), nullable=True)

    # --- Indicadores de atendimento ---
    abertos = Column(Integer, nullable=False, default=0, comment="Atendimentos com status aberto")
    em_andamento = Column(Integer, nullable=False, default=0, comment="Atendimentos em andamento")
    concluidos = Column(Integer, nullable=False, default=0, comment="Atendimentos concluídos")
    tempo_medio_resposta_min = Column(Numeric(10, 2), nullable=True, comment="Tempo médio de resposta em minutos")

    __table_args__ = (
        UniqueConstraint("hora", "app", "canal", "evento", name="uq_summary_hourly"),
        Index("ix_summary_hourly_hora", "hora"),
        Index("ix_summary_hourly_app_hora", "app", "hora"),
    )

    def __repr__(self):
        return f"<SummaryHourly {self.app}/{self.evento} {self.hora} ({self.total_eventos} eventos)>"


class EventSummaryDaily(Base):
    """Resumo de eventos agregados por dia."""

    __tablename__ = "events_summary_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dia = Column(Date, nullable=False, comment="Data do resumo")
    app = Column(String(100), nullable=False)
    canal = Column(String(100), nullable=True)
    evento = Column(String(100), nullable=False)

    total_eventos = Column(Integer, nullable=False, default=0)
    soma_valores = Column(Numeric(15, 2), nullable=True, default=0)
    media_valores = Column(Numeric(15, 2), nullable=True, default=0)
    valor_min = Column(Numeric(15, 2), nullable=True)
    valor_max = Column(Numeric(15, 2), nullable=True)
    usuarios_unicos = Column(Integer, nullable=True, default=0)

    # --- Indicadores de atendimento ---
    abertos = Column(Integer, nullable=False, default=0, comment="Atendimentos com status aberto")
    em_andamento = Column(Integer, nullable=False, default=0, comment="Atendimentos em andamento")
    concluidos = Column(Integer, nullable=False, default=0, comment="Atendimentos concluídos")
    comunicantes_unicos = Column(Integer, nullable=True, default=0, comment="Comunicantes distintos no dia")
    tempo_medio_resposta_min = Column(Numeric(10, 2), nullable=True, comment="Tempo médio de resposta em minutos")

    __table_args__ = (
        UniqueConstraint("dia", "app", "canal", "evento", name="uq_summary_daily"),
        Index("ix_summary_daily_dia", "dia"),
        Index("ix_summary_daily_app_dia", "app", "dia"),
    )

    def __repr__(self):
        return f"<SummaryDaily {self.app}/{self.evento} {self.dia} ({self.total_eventos} eventos)>"
