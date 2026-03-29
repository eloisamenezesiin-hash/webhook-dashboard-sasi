"""
Serviço de normalização de payloads webhook.
Converte dados de múltiplos formatos para o formato padrão.

Segue o padrão do skill webhook-normalizacao:
{
  "app": "", "canal": "", "evento": "", "data": "",
  "usuario": "", "valor": null, "metadata": {}
}
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.webhook import WebhookPayload, NormalizedEvent

logger = logging.getLogger(__name__)


def normalize_payload(raw_data: dict[str, Any]) -> NormalizedEvent:
    """
    Normaliza um payload bruto para o formato padrão.

    Resolve aliases (source→app, event→evento, etc.)
    e preserva campos extras em metadata.
    """
    try:
        payload = WebhookPayload(**raw_data)
    except Exception as e:
        logger.warning(f"Erro ao parsear payload, usando valores vazios: {e}")
        payload = WebhookPayload()

    # --- Resolver aliases (prioridade: campo PT-BR > alias EN) ---
    app = _first_non_empty(payload.app, payload.source, "desconhecido")
    canal = _first_non_empty(payload.canal, payload.channel, "")
    evento = _first_non_empty(payload.evento, payload.event, payload.type, "sem_evento")
    usuario = _first_non_empty(payload.usuario, payload.user, "")
    data = _first_non_empty(payload.data, payload.timestamp, datetime.now(timezone.utc).isoformat())
    valor = _first_non_none(payload.valor, payload.amount, payload.value)

    # Novos campos de atendimento
    comunicante = _first_non_empty(
        payload.comunicante, payload.reporter, payload.informante, payload.denunciante, ""
    )
    status = _first_non_empty(payload.status, "aberto")
    concluded_at = _first_non_empty(payload.concluded_at, "")

    # Normalizar status para valores padrão
    status_map = {
        "aberto": "aberto", "open": "aberto", "novo": "aberto", "new": "aberto",
        "em_andamento": "em_andamento", "em andamento": "em_andamento",
        "in_progress": "em_andamento", "andamento": "em_andamento",
        "concluido": "concluido", "concluído": "concluido",
        "closed": "concluido", "done": "concluido", "finalizado": "concluido",
        "completed": "concluido", "resolvido": "concluido",
    }
    status = status_map.get(status.strip().lower(), status.strip().lower()) if status else "aberto"

    # --- Coletar campos extras para metadata ---
    metadata = dict(payload.metadata or {})

    # Campos extras que vieram no payload (via Config extra="allow")
    if hasattr(payload, "__pydantic_extra__") and payload.__pydantic_extra__:
        metadata.update(payload.__pydantic_extra__)

    return NormalizedEvent(
        app=app.strip().lower() if app else "",
        canal=canal.strip().lower() if canal else "",
        evento=evento.strip().lower() if evento else "",
        data=data,
        usuario=usuario.strip() if usuario else "",
        valor=valor,
        comunicante=comunicante.strip() if comunicante else "",
        status=status,
        concluded_at=concluded_at if concluded_at else None,
        metadata=metadata,
        raw_payload=raw_data,
    )


def _first_non_empty(*values: Any, default: str = "") -> str:
    """Retorna o primeiro valor não vazio/nulo."""
    for v in values:
        if v is not None and str(v).strip():
            return str(v)
    return default


def _first_non_none(*values: Any) -> Any:
    """Retorna o primeiro valor não None."""
    for v in values:
        if v is not None:
            return v
    return None
