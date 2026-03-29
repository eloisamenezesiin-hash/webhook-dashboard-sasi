"""
Worker de processamento de eventos webhook.
Consome a fila Redis (RQ) de forma SEQUENCIAL — um evento por vez.

IMPORTANTE: Este worker deve rodar como processo único.
Isso elimina concorrência de script e protege o banco de dados.

Uso:
    rq worker webhook_events --burst  (processa tudo e para)
    rq worker webhook_events          (fica rodando contínuo)
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.event import WebhookEvent

logger = logging.getLogger(__name__)


def process_event(event_data: dict) -> dict:
    """
    Processa um evento da fila e persiste no PostgreSQL.
    Chamado pelo RQ Worker — executa sequencialmente.

    Args:
        event_data: Evento normalizado (NormalizedEvent serializado)

    Returns:
        dict com status do processamento
    """
    db: Session = SessionLocal()

    try:
        logger.info(f"Processando evento: app={event_data.get('app')}, evento={event_data.get('evento')}")

        # --- Criar registro no banco ---
        concluded_at = _parse_datetime(event_data.get("concluded_at")) if event_data.get("concluded_at") else None
        event = WebhookEvent(
            app=event_data.get("app", ""),
            canal=event_data.get("canal", ""),
            evento=event_data.get("evento", ""),
            usuario=event_data.get("usuario", ""),
            valor=event_data.get("valor"),
            comunicante=event_data.get("comunicante", ""),
            status=event_data.get("status", "aberto"),
            concluded_at=concluded_at,
            metadata_=event_data.get("metadata", {}),
            raw_payload=event_data.get("raw_payload", {}),
            received_at=_parse_datetime(event_data.get("data")),
            processed_at=datetime.now(timezone.utc),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(f"Evento persistido: id={event.id}, app={event.app}")

        return {
            "status": "success",
            "event_id": str(event.id),
            "app": event.app,
            "evento": event.evento,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao processar evento: {e}", exc_info=True)

        # Tenta salvar o erro no log
        try:
            from app.models.log import WebhookLog
            error_log = WebhookLog(
                status_code=500,
                error_message=f"Worker error: {str(e)[:500]}",
                app_name=event_data.get("app", "unknown"),
            )
            db.add(error_log)
            db.commit()
        except Exception:
            db.rollback()

        raise

    finally:
        db.close()


def _parse_datetime(value: str | None) -> datetime:
    """Tenta parsear uma string de datetime, retorna UTC now se falhar."""
    if not value:
        return datetime.now(timezone.utc)

    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    logger.warning(f"Não foi possível parsear datetime '{value}', usando UTC now")
    return datetime.now(timezone.utc)
