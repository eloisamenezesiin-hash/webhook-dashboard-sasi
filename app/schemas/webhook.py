"""
Schemas Pydantic para validação e normalização dos payloads webhook.
Compatível com o padrão definido no skill webhook-normalizacao.
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    """
    Schema flexível para receber payloads de múltiplas fontes.
    Aceita qualquer JSON e preserva campos extras em 'extras'.
    """
    # Campos que podem vir no payload (todos opcionais para máxima flexibilidade)
    app: Optional[str] = Field(None, description="App/sistema de origem")
    canal: Optional[str] = Field(None, description="Canal de envio")
    evento: Optional[str] = Field(None, description="Tipo do evento")
    data: Optional[str] = Field(None, description="Data do evento (texto)")
    usuario: Optional[str] = Field(None, description="Usuário associado")
    valor: Optional[float] = Field(None, description="Valor numérico")
    comunicante: Optional[str] = Field(None, description="Pessoa que reportou/comunicou")
    status: Optional[str] = Field(None, description="Status do atendimento: aberto, em_andamento, concluido")
    concluded_at: Optional[str] = Field(None, description="Data/hora de conclusão do atendimento")
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict, description="Dados extras")

    # Aliases comuns de outros sistemas
    source: Optional[str] = Field(None, description="Alias para 'app'")
    event: Optional[str] = Field(None, description="Alias para 'evento' (inglês)")
    channel: Optional[str] = Field(None, description="Alias para 'canal' (inglês)")
    user: Optional[str] = Field(None, description="Alias para 'usuario' (inglês)")
    amount: Optional[float] = Field(None, description="Alias para 'valor' (inglês)")
    value: Optional[float] = Field(None, description="Alias para 'valor' (inglês)")
    type: Optional[str] = Field(None, description="Alias para 'evento'")
    timestamp: Optional[str] = Field(None, description="Alias para 'data'")
    reporter: Optional[str] = Field(None, description="Alias para 'comunicante' (inglês)")
    informante: Optional[str] = Field(None, description="Alias para 'comunicante'")
    denunciante: Optional[str] = Field(None, description="Alias para 'comunicante'")

    class Config:
        extra = "allow"  # Permite campos extras — serão preservados em metadata


class NormalizedEvent(BaseModel):
    """
    Formato padronizado após normalização.
    Segue o padrão do skill webhook-normalizacao.
    """
    app: str = ""
    canal: str = ""
    evento: str = ""
    data: str = ""
    usuario: str = ""
    valor: Optional[float] = None
    comunicante: str = ""
    status: str = "aberto"
    concluded_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class WebhookResponse(BaseModel):
    """Resposta padrão do endpoint webhook."""
    status: str = "accepted"
    message: str = "Evento recebido e enfileirado para processamento"
    queue_id: Optional[str] = None
    received_at: datetime = Field(default_factory=datetime.utcnow)
