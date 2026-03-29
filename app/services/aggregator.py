"""
Serviço de agregação de métricas.
Calcula resumos horários e diários a partir dos eventos brutos.
Os dashboards leem apenas das tabelas agregadas — nunca da tabela bruta.
"""

import logging
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

from sqlalchemy import func, distinct, and_, case, extract
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.event import WebhookEvent
from app.models.summary import EventSummaryHourly, EventSummaryDaily

logger = logging.getLogger(__name__)


def aggregate_hourly(db: Session, target_hour: datetime | None = None) -> int:
    """
    Agrega eventos da última hora (ou hora especificada) na tabela de resumo horário.
    Usa UPSERT para atualizar se já existir registro.

    Returns: número de registros inseridos/atualizados
    """
    if target_hour is None:
        now = datetime.now(timezone.utc)
        target_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    hour_start = target_hour.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    logger.info(f"Agregando eventos de {hour_start} a {hour_end}")

    # Consulta agrupada dos eventos brutos
    results = (
        db.query(
            WebhookEvent.app,
            WebhookEvent.canal,
            WebhookEvent.evento,
            func.count(WebhookEvent.id).label("total"),
            func.sum(WebhookEvent.valor).label("soma"),
            func.avg(WebhookEvent.valor).label("media"),
            func.min(WebhookEvent.valor).label("minimo"),
            func.max(WebhookEvent.valor).label("maximo"),
            func.count(case(
                (WebhookEvent.status == "aberto", 1),
            )).label("abertos"),
            func.count(case(
                (WebhookEvent.status == "em_andamento", 1),
            )).label("em_andamento"),
            func.count(case(
                (WebhookEvent.status == "concluido", 1),
            )).label("concluidos"),
            func.avg(
                case(
                    (
                        and_(
                            WebhookEvent.status == "concluido",
                            WebhookEvent.concluded_at.isnot(None),
                        ),
                        extract("epoch", WebhookEvent.concluded_at - WebhookEvent.received_at) / 60.0,
                    ),
                )
            ).label("tempo_medio"),
        )
        .filter(
            and_(
                WebhookEvent.received_at >= hour_start,
                WebhookEvent.received_at < hour_end,
            )
        )
        .group_by(WebhookEvent.app, WebhookEvent.canal, WebhookEvent.evento)
        .all()
    )

    count = 0
    for row in results:
        stmt = pg_insert(EventSummaryHourly).values(
            hora=hour_start,
            app=row.app,
            canal=row.canal or "",
            evento=row.evento,
            total_eventos=row.total,
            soma_valores=row.soma or Decimal("0"),
            media_valores=round(row.media or Decimal("0"), 2),
            valor_min=row.minimo,
            valor_max=row.maximo,
            abertos=row.abertos,
            em_andamento=row.em_andamento,
            concluidos=row.concluidos,
            tempo_medio_resposta_min=round(row.tempo_medio, 2) if row.tempo_medio else None,
        )
        stmt = stmt.on_conflict_on_constraint("uq_summary_hourly").do_update(
            set_={
                "total_eventos": stmt.excluded.total_eventos,
                "soma_valores": stmt.excluded.soma_valores,
                "media_valores": stmt.excluded.media_valores,
                "valor_min": stmt.excluded.valor_min,
                "valor_max": stmt.excluded.valor_max,
                "abertos": stmt.excluded.abertos,
                "em_andamento": stmt.excluded.em_andamento,
                "concluidos": stmt.excluded.concluidos,
                "tempo_medio_resposta_min": stmt.excluded.tempo_medio_resposta_min,
            }
        )
        db.execute(stmt)
        count += 1

    db.commit()
    logger.info(f"Agregação horária concluída: {count} registros para {hour_start}")
    return count


def aggregate_daily(db: Session, target_date: date | None = None) -> int:
    """
    Agrega eventos do dia anterior (ou data especificada) na tabela de resumo diário.
    Usa UPSERT para atualizar se já existir registro.

    Returns: número de registros inseridos/atualizados
    """
    if target_date is None:
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    logger.info(f"Agregando eventos do dia {target_date}")

    results = (
        db.query(
            WebhookEvent.app,
            WebhookEvent.canal,
            WebhookEvent.evento,
            func.count(WebhookEvent.id).label("total"),
            func.sum(WebhookEvent.valor).label("soma"),
            func.avg(WebhookEvent.valor).label("media"),
            func.min(WebhookEvent.valor).label("minimo"),
            func.max(WebhookEvent.valor).label("maximo"),
            func.count(distinct(WebhookEvent.usuario)).label("usuarios"),
            func.count(case(
                (WebhookEvent.status == "aberto", 1),
            )).label("abertos"),
            func.count(case(
                (WebhookEvent.status == "em_andamento", 1),
            )).label("em_andamento"),
            func.count(case(
                (WebhookEvent.status == "concluido", 1),
            )).label("concluidos"),
            func.count(distinct(WebhookEvent.comunicante)).label("comunicantes"),
            func.avg(
                case(
                    (
                        and_(
                            WebhookEvent.status == "concluido",
                            WebhookEvent.concluded_at.isnot(None),
                        ),
                        extract("epoch", WebhookEvent.concluded_at - WebhookEvent.received_at) / 60.0,
                    ),
                )
            ).label("tempo_medio"),
        )
        .filter(
            and_(
                WebhookEvent.received_at >= day_start,
                WebhookEvent.received_at < day_end,
            )
        )
        .group_by(WebhookEvent.app, WebhookEvent.canal, WebhookEvent.evento)
        .all()
    )

    count = 0
    for row in results:
        stmt = pg_insert(EventSummaryDaily).values(
            dia=target_date,
            app=row.app,
            canal=row.canal or "",
            evento=row.evento,
            total_eventos=row.total,
            soma_valores=row.soma or Decimal("0"),
            media_valores=round(row.media or Decimal("0"), 2),
            valor_min=row.minimo,
            valor_max=row.maximo,
            usuarios_unicos=row.usuarios,
            abertos=row.abertos,
            em_andamento=row.em_andamento,
            concluidos=row.concluidos,
            comunicantes_unicos=row.comunicantes,
            tempo_medio_resposta_min=round(row.tempo_medio, 2) if row.tempo_medio else None,
        )
        stmt = stmt.on_conflict_on_constraint("uq_summary_daily").do_update(
            set_={
                "total_eventos": stmt.excluded.total_eventos,
                "soma_valores": stmt.excluded.soma_valores,
                "media_valores": stmt.excluded.media_valores,
                "valor_min": stmt.excluded.valor_min,
                "valor_max": stmt.excluded.valor_max,
                "usuarios_unicos": stmt.excluded.usuarios_unicos,
                "abertos": stmt.excluded.abertos,
                "em_andamento": stmt.excluded.em_andamento,
                "concluidos": stmt.excluded.concluidos,
                "comunicantes_unicos": stmt.excluded.comunicantes_unicos,
                "tempo_medio_resposta_min": stmt.excluded.tempo_medio_resposta_min,
            }
        )
        db.execute(stmt)
        count += 1

    db.commit()
    logger.info(f"Agregação diária concluída: {count} registros para {target_date}")
    return count
