"""
Dashboard departamental com Plotly Dash.
Filtros dinц╒micos (app, canal, comunicante) + indicadores de atendimento.
Lц╙ das tabelas bruta e agregadas conforme necessidade.
Atualiza automaticamente a cada N segundos (configurц║vel).
"""

import logging
from datetime import datetime, timedelta, timezone

import dash
from dash import html, dcc, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import func, distinct, and_, case, extract

from app.config import get_settings
from app.database import SessionLocal
from app.models.event import WebhookEvent
from app.models.summary import EventSummaryHourly, EventSummaryDaily
from app.models.log import WebhookLog

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================
# Inicializaц╖цёo do Dash
# ============================================================
dash_app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="Dashboard Departamental Б─■ SASI",
    update_title="Atualizando...",
    suppress_callback_exceptions=True,
)

# Tema de cores
COLORS = {
    "bg": "#0f172a",
    "card": "#1e293b",
    "border": "#334155",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "info": "#38bdf8",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "danger": "#f87171",
    "purple": "#a78bfa",
    "orange": "#fb923c",
}


# ============================================================
# Funц╖ц╣es de consulta ao banco (leitura)
# ============================================================
def _get_db():
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


def get_filter_options() -> dict:
    """Busca opц╖ц╣es ц╨nicas para os dropdowns de filtro."""
    db = _get_db()
    try:
        apps = [r[0] for r in db.query(distinct(WebhookEvent.app)).filter(
            WebhookEvent.app.isnot(None), WebhookEvent.app != ""
        ).order_by(WebhookEvent.app).all()]

        canais = [r[0] for r in db.query(distinct(WebhookEvent.canal)).filter(
            WebhookEvent.canal.isnot(None), WebhookEvent.canal != ""
        ).order_by(WebhookEvent.canal).all()]

        comunicantes = [r[0] for r in db.query(distinct(WebhookEvent.comunicante)).filter(
            WebhookEvent.comunicante.isnot(None), WebhookEvent.comunicante != ""
        ).order_by(WebhookEvent.comunicante).all()]

        return {"apps": apps, "canais": canais, "comunicantes": comunicantes}
    finally:
        db.close()


def _apply_filters(query, app_filter, canal_filter, comunicante_filter):
    """Aplica filtros dinц╒micos a uma query."""
    if app_filter:
        query = query.filter(WebhookEvent.app.in_(app_filter))
    if canal_filter:
        query = query.filter(WebhookEvent.canal.in_(canal_filter))
    if comunicante_filter:
        query = query.filter(WebhookEvent.comunicante.in_(comunicante_filter))
    return query


def get_kpi_data(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> dict:
    """Busca indicadores principais com filtros aplicados."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        base_q = db.query(WebhookEvent).filter(WebhookEvent.received_at >= since)
        base_q = _apply_filters(base_q, app_filter, canal_filter, comunicante_filter)

        total = base_q.count()

        # Status breakdown
        status_q = (
            db.query(
                WebhookEvent.status,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(WebhookEvent.received_at >= since)
        )
        status_q = _apply_filters(status_q, app_filter, canal_filter, comunicante_filter)
        status_q = status_q.group_by(WebhookEvent.status).all()

        status_map = {r.status: r.total for r in status_q}
        abertos = status_map.get("aberto", 0)
        em_andamento = status_map.get("em_andamento", 0)
        concluidos = status_map.get("concluido", 0)

        # Tempo mц╘dio de resposta (minutos) para concluц╜dos
        tempo_q = (
            db.query(
                func.avg(
                    extract("epoch", WebhookEvent.concluded_at - WebhookEvent.received_at) / 60.0
                )
            )
            .filter(
                WebhookEvent.received_at >= since,
                WebhookEvent.status == "concluido",
                WebhookEvent.concluded_at.isnot(None),
            )
        )
        tempo_q = _apply_filters(tempo_q, app_filter, canal_filter, comunicante_filter)
        tempo_medio = tempo_q.scalar() or 0

        # Comunicantes ц╨nicos
        com_q = (
            db.query(func.count(distinct(WebhookEvent.comunicante)))
            .filter(
                WebhookEvent.received_at >= since,
                WebhookEvent.comunicante.isnot(None),
                WebhookEvent.comunicante != "",
            )
        )
        com_q = _apply_filters(com_q, app_filter, canal_filter, comunicante_filter)
        comunicantes_unicos = com_q.scalar() or 0

        # Apps ativos
        apps_q = (
            db.query(func.count(distinct(WebhookEvent.app)))
            .filter(WebhookEvent.received_at >= since)
        )
        apps_q = _apply_filters(apps_q, app_filter, canal_filter, comunicante_filter)
        apps_ativos = apps_q.scalar() or 0

        return {
            "total": total,
            "abertos": abertos,
            "em_andamento": em_andamento,
            "concluidos": concluidos,
            "tempo_medio_min": round(float(tempo_medio), 1),
            "comunicantes_unicos": comunicantes_unicos,
            "apps_ativos": apps_ativos,
        }
    finally:
        db.close()


def get_status_breakdown(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> pd.DataFrame:
    """Breakdown de status para grц║fico de rosca."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                WebhookEvent.status,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(WebhookEvent.received_at >= since)
        )
        q = _apply_filters(q, app_filter, canal_filter, comunicante_filter)
        results = q.group_by(WebhookEvent.status).all()

        # Mapear nomes amigц║veis
        labels = {"aberto": "Abertos", "em_andamento": "Em Andamento", "concluido": "Concluц╜dos"}
        data = []
        for r in results:
            data.append({"status": labels.get(r.status, r.status or "Sem status"), "total": r.total})
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["status", "total"])
    finally:
        db.close()


def get_events_by_app(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> pd.DataFrame:
    """Total de atendimentos por app/departamento."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                WebhookEvent.app,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(WebhookEvent.received_at >= since)
        )
        q = _apply_filters(q, app_filter, canal_filter, comunicante_filter)
        results = q.group_by(WebhookEvent.app).order_by(func.count(WebhookEvent.id).desc()).limit(20).all()
        return pd.DataFrame(results, columns=["app", "total"])
    finally:
        db.close()


def get_events_by_canal(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> pd.DataFrame:
    """Total de atendimentos por canal."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                WebhookEvent.canal,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(WebhookEvent.received_at >= since)
        )
        q = _apply_filters(q, app_filter, canal_filter, comunicante_filter)
        results = q.group_by(WebhookEvent.canal).order_by(func.count(WebhookEvent.id).desc()).limit(20).all()
        return pd.DataFrame(results, columns=["canal", "total"])
    finally:
        db.close()


def get_daily_trend(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> pd.DataFrame:
    """Tendц╙ncia diц║ria de atendimentos com breakdown por status."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                func.date(WebhookEvent.received_at).label("dia"),
                WebhookEvent.status,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(WebhookEvent.received_at >= since)
        )
        q = _apply_filters(q, app_filter, canal_filter, comunicante_filter)
        results = q.group_by("dia", WebhookEvent.status).order_by("dia").all()

        labels = {"aberto": "Abertos", "em_andamento": "Em Andamento", "concluido": "Concluц╜dos"}
        data = []
        for r in results:
            data.append({
                "dia": r.dia,
                "status": labels.get(r.status, r.status or "Sem status"),
                "total": r.total,
            })
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["dia", "status", "total"])
    finally:
        db.close()


def get_response_time_by_app(app_filter=None, canal_filter=None, comunicante_filter=None, days=30) -> pd.DataFrame:
    """Tempo mц╘dio de resposta por app (apenas concluц╜dos)."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                WebhookEvent.app,
                func.avg(
                    extract("epoch", WebhookEvent.concluded_at - WebhookEvent.received_at) / 60.0
                ).label("tempo_medio"),
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(
                WebhookEvent.received_at >= since,
                WebhookEvent.status == "concluido",
                WebhookEvent.concluded_at.isnot(None),
            )
        )
        q = _apply_filters(q, app_filter, canal_filter, comunicante_filter)
        results = q.group_by(WebhookEvent.app).order_by(func.avg(
            extract("epoch", WebhookEvent.concluded_at - WebhookEvent.received_at) / 60.0
        ).desc()).all()

        data = [{"app": r.app, "tempo_medio_min": round(float(r.tempo_medio), 1), "total": r.total} for r in results]
        return pd.DataFrame(data) if data else pd.DataFrame(columns=["app", "tempo_medio_min", "total"])
    finally:
        db.close()


def get_top_comunicantes(app_filter=None, canal_filter=None, comunicante_filter=None, days=30, limit=15) -> pd.DataFrame:
    """Top comunicantes por nц╨mero de atendimentos."""
    db = _get_db()
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q = (
            db.query(
                WebhookEvent.comunicante,
                func.count(WebhookEvent.id).label("total"),
            )
            .filter(▓ю╒рбжCс2▓ю╒р▓ю╒р▓ю╒рб7G√фSв╟╒&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рю╒&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"ю╒&&В&FW%&F≈W2#╒#┌"ю╒рб6ф74ФжSр&ж"сB"░══╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╒2ф√ВWBFРF6├&Ж&@╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╕F6┘ЖФф√ВWBрF&2Д6ЖГF√ФW"┘╟╒2ррр├VFW"ррп╒F&2Е&Вr┘╟╒F&2Д6Жб┘╟╒┤FжбД┐"┌$F6├&Ж&BFW'FжVГFб(	B44▓"б7G√фSв╡&6ЖфВ"#╒4ТдУ%5╡&√ФfР%врб6ф74ФжSр&ж"с"▓ю╒┤FжбЕ┌$√ФF√6FВ&W2FRFVФF√жVГFРВ"FW'FжVГFРб6ФбR6ЖвVФ√6ГFR"ю╒7G√фSв╡&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒рбv√GF┐с┌▓ю╒F&2Д6Жб┘╟╒┤FжбДF≈b├√Cр&ф7BвWFFR"б7G√фSв╡&fЖГE6≈╕R#╒#Ц┤&Vр"б&6ЖфВ"#╒4ТдУ%5╡&вWFVB%рб'FW┤Dф√vБ#╒'&√v┤B'р▓ю╒рбv√GF┐сBб6ф74ФжSр&BжfфW┌ф√vБж≈FVв2ж6VГFW"╖W7F√g▓ж6ЖГFVГBжVФB"▓ю╒рб6ф74ФжSр&ж"с2вBс2"▓ю═╒2рррf√гG&В2ррп╒7&VFUЖf√гFW%ВФVб┌▓ю═╒2ррр╣▓6&G2ррп╒F&2Е&Вr├√Cр&╥▓ж6&G2"б6ф74ФжSр&ж"сB"▓ю═╒2рррф√Ф├╒7FGW2╡FVФF√жVГFВ2В"FW'FжVГFРррп╒F&2Е&Вr┘╟╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌%7FGW2FВ2FVФF√жVГFВ2"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌в7FGW2"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCсB▓ю╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌$FVФF√жVГFВ2В"FW'FжVГFР"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌ж'▓ж"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCс┌▓ю╒рб6ф74ФжSр&ж"сB"▓ю═╒2рррф√Ф├#╒6Ф≈2╡FVвРFR&W7В7Fррп╒F&2Е&Вr┘╟╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌$FVФF√жVГFВ2В"6Фб"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌ж'▓ж6Фб"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCсb▓ю╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌%FVвРэ:√F√РFR&W7В7FВ"FW'FжVГFР├ж√Б▓"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌в&W7ЖГ6RвF√жR"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCсb▓ю╒рб6ф74ФжSр&ж"сB"▓ю═╒2рррф√Ф├3╒FVФL:╕Ф6√╡FВ6ЖвVФ√6ГFW2ррп╒F&2Е&Вr┘╟╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌%FVФL:╕Ф6√F°:&√FRFVФF√жVГFВ2"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌жF√г▓вG&VФB"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCсr▓ю╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌%FВ6ЖвVФ√6ГFW2"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├F62Дw&┌├√Cр&w&┌вFВж6ЖвVФ√6ГFW2"б6ЖФf√sв╡&F≈7ф■жЖFT&"#╒fг6Wр▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒рбжCсR▓ю╒рб6ф74ФжSр&ж"сB"▓ю═╒2рррF&VфFRFVФF√жVГFВ2&V6VГFW2ррп╒F&2Е&Вr┘╟╒F&2Д6Жб┘╟╒F&2Д6&B┘╟╒F&2Д6&D├VFW"┌,9╕гF√жВ2FVФF√жVГFВ2"ю╒7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&6ЖфВ"#╒4ТдУ%5╡&вWFVB%вр▓ю╒F&2Д6&D&ЖG▓├┤FжбДF≈b├√Cр'F&фRв&V6VГBжWfVГG2"▓▓ю╒рб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&6&B%рб&&В&FW"#╒b#┌6Жф√B╢4ТдУ%5╡v&В&FW"uвр"б&&В&FW%&F≈W2#╒#┌'р▓ю╒р▓ю╒рб6ф74ФжSр&ж"сB"▓ю═╒2ррр7FВ&W2R√ГFW'fбррп╒F62Д√ГFW'fб├√Cр&√ГFW'fбв&Vg&W6┌"б√ГFW'fцв6WGF√Фw2ФF6┘ВWFFUЖ√ГFW'fббЕЖ√ГFW'fг3с▓ю╒F62Е7FВ&R├√Cр'7FВ&Rжf√гFW'2жфЖFVB"бFFтfг6R▓ю═╔рбfгV√CуG'VRб7G√фSв╡&&6╤w&ВVФD6ЖфВ"#╒4ТдУ%5╡&&r%рб&ж√Д├V√v┤B#╒#f┌"б'FF√Фr#╒#&Vр'&Vр'р░══╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╒26фф&6╥0╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп═╒2ррр6фф&6╡╒GVф≈╕"В:|;VW2FВ2f√гG&В2F√Фж√6жVГFRррп╓F6┘ЖФ6фф&6╡─╒╟╒ВWGWB┌&f√гFW"ж"б&ВF√ЖГ2"▓ю╒ВWGWB┌&f√гFW"ж6Фб"б&ВF√ЖГ2"▓ю╒ВWGWB┌&f√гFW"ж6ЖвVФ√6ГFR"б&ВF√ЖГ2"▓ю╒рю╒√ГWB┌&√ГFW'fбв&Vg&W6┌"б&ЕЖ√ГFW'fг2"▓ю╒░╕FVbWFFUЖf√гFW%ЖВF√ЖГ2├Б⌠═╒""$6'&VvВ:|;VW2FВ2G&ВFВvГ2'F≈"FР&Ф6РБ"" ╒G'⌠═╒ВG2рvWEЖf√гFW%ЖВF√ЖГ2┌░╒&WGW&Б─╒╥╡&ф&Vб#╒ГF≈FфR┌▓б'fгVR#╒рfВ"√БВG5╡&2%урю╒╥╡&ф&Vб#╒2ГF≈FфR┌▓б'fгVR#╒7рfВ"2√БВG5╡&6Ф≈2%урю╒╥╡&ф&Vб#╒2ГF≈FфR┌▓б'fгVR#╒7рfВ"2√БВG5╡&6ЖвVФ√6ГFW2%урю╒░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&РР6'&Vv"f√гG&В3╒╤Wр"░╒&WGW&Б╣рб╣рб╣п══╒2ррр6фф&6╡#╒ф√в"f√гG&В2ррп╓F6┘ЖФ6фф&6╡─╒╟╒ВWGWB┌&f√гFW"ж"б'fгVR"▓ю╒ВWGWB┌&f√гFW"ж6Фб"б'fгVR"▓ю╒ВWGWB┌&f√гFW"ж6ЖвVФ√6ГFR"б'fгVR"▓ю╒рю╒√ГWB┌&'FБж6фV"жf√гFW'2"б&ЕЖ6ф√6╥2"▓ю╒&WfVГEЖ√Ф≈F√еЖ6фцуG'VRю╒░╕FVb6фV%Жf√гFW'2├ЕЖ6ф√6╥2⌠═╒&WGW&БФЖФRбФЖФRбФЖФP══╒2ррр6фф&6╡3╒GVф≈╕"FЖFРРF6├&Ж&B6Жрf√гG&В2ррп╓F6┘ЖФ6фф&6╡─╒╟╒ВWGWB┌&╥▓ж6&G2"б&6├√фG&VБ"▓ю╒ВWGWB┌&w&┌в7FGW2"б&f√wW&R"▓ю╒ВWGWB┌&w&┌ж'▓ж"б&f√wW&R"▓ю╒ВWGWB┌&w&┌ж'▓ж6Фб"б&f√wW&R"▓ю╒ВWGWB┌&w&┌в&W7ЖГ6RвF√жR"б&f√wW&R"▓ю╒ВWGWB┌&w&┌жF√г▓вG&VФB"б&f√wW&R"▓ю╒ВWGWB┌&w&┌вFВж6ЖвVФ√6ГFW2"б&f√wW&R"▓ю╒ВWGWB┌'F&фRв&V6VГBжWfVГG2"б&6├√фG&VБ"▓ю╒ВWGWB┌&ф7BвWFFR"б&6├√фG&VБ"▓ю╒рю╒╟╒√ГWB┌&√ГFW'fбв&Vg&W6┌"б&ЕЖ√ГFW'fг2"▓ю╒√ГWB┌&f√гFW"ж"б'fгVR"▓ю╒√ГWB┌&f√гFW"ж6Фб"б'fгVR"▓ю╒√ГWB┌&f√гFW"ж6ЖвVФ√6ГFR"б'fгVR"▓ю╒√ГWB┌&f√гFW"вW&√ЖFР"б'fгVR"▓ю╒рю╒░╕FVbWFFUЖF6├&Ж&B├БбЖf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бW&√ЖFР⌠═╒""$GVф≈╕FЖFВ2В26ЖвЖФVГFW2FРF6├&Ж&B6Жрf√гG&В2ф√6FВ2Б"" ╒FVвфFRр'фВFг∙ЖF&╡ ╒F≈2рW&√ЖFРВ"3 ═╒2ФВ&жф≈╕"f√гG&В2f╕√В0╒Жf√гFW"рЖf√гFW"√bЖf√гFW"Vг6RФЖФP╒6ФеЖf√гFW"р6ФеЖf√гFW"√b6ФеЖf√гFW"Vг6RФЖФP╒6ЖвVФ√6ГFUЖf√гFW"р6ЖвVФ√6ГFUЖf√гFW"√b6ЖвVФ√6ГFUЖf√гFW"Vг6RФЖФP═╒2рррр╣≈2рррп╒G'⌠═╒╥≈2рvWEЖ╥∙ЖFF├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Р╣≈3╒╤Wр"░╒╥≈2р╡'FВFб#╒б&&W'FВ2#╒б&VуЖФFжVГFР#╒б&6ЖФ6гV√FВ2#╒ю╒'FVвУЖжVF√УЖж√Б#╒б&6ЖвVФ√6ГFW5ВVФ√6В2#╒б&5ЖF≈fВ2#╒п═╒F├Ж6ЖФ6гW6Рр&ВVФB├╥≈5╡&6ЖФ6гV√FВ2%рР╥≈5╡'FВFб%р╒б▓√b╥≈5╡'FВFб%рБVг6R ═╒╥∙Ж6&G2р╟╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌%FВFбFVФF√жVГFВ2"бb'╤╥≈5╡wFВFбuс╒гр"б&√ФfР"▓бфsс"бжCсBб6ссb▓ю╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌$&W'FВ2"бb'╤╥≈5╡v&W'FВ2uс╒гр"б'v&Ф√Фr"▓бфsс"бжCсBб6ссb▓ю╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌$VрФFжVГFР"бb'╤╥≈5╡vVуЖФFжVГFРuс╒гр"б&В&ФvR"▓бфsс"бжCсBб6ссb▓ю╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌$6ЖФ6г\:жFВ2"бb'╤╥≈5╡v6ЖФ6гV√FВ2uс╒гр"б'7V66W72"▓бфsс"бжCсBб6ссb▓ю╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌%FVвРэ:√F√Р"бb'╤╥≈5╡wFVвУЖжVF√УЖж√Бuврж√Б"б'W'фR"▓бфsс"бжCсBб6ссb▓ю╒F&2Д6Жб├7&VFUЖ╥∙Ж6&B┌%F├6ЖФ6гW<:6Р"бb'╥F├Ж6ЖФ6гW6ВрR"б'7V66W72"√bF├Ж6ЖФ6гW6РЦрsVг6R&FФvW""▓бфsс"бжCсBб6ссb▓ю╒п═╒2рррр7FGW2┤&В66▓рррп╒G'⌠═╒FeВ7FGW2рvWEВ7FGW5Ж'&V╤FВvБ├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeВ7FGW2ФVвG⌠═╒6ЖфВ%Жжр╡$&W'FВ2#╒4ТдУ%5╡'v&Ф√Фr%рб$VрФFжVГFР#╒4ТдУ%5╡&В&ФvR%рб$6ЖФ6г\:жFВ2#╒4ТдУ%5╡'7V66W72%вп╒f√uВ7FGW2р┌Г√R─╒FeВ7FGW2бФжW3р'7FGW2"бfгVW3р'FВFб"ю╒FVвфFSвFVвфFRб├ЖфSсЦRю╒6ЖфВ#р'7FGW2"б6ЖфВ%ЖF≈67&WFUЖжж6ЖфВ%Жжю╒░╒f√uВ7FGW2ГWFFUВG&6W2┤FW┤F√ФfСр'fгVR╥W&6VГB"бFW┤FfЖГEВ6≈╕Sс"░╒Vг6S═╒f√uВ7FGW2рЖVвG∙Жf√wW&R┌%6VрFFВ2FR7FGW2"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌в7FGW3╒╤Wр"░╒f√uВ7FGW2рЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uВ7FGW2ГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррFVФF√жVГFВ2В"├&'&2├В&≈╕ЖГF≈2▓рррп╒G'⌠═╒FeЖ2рvWEЖWfVГG5Ж'∙Ж├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeЖ2ФVвG⌠═╒FeЖ5╡&ЖF≈7ф▓%ррFeЖ5╡&%рГ7G"ГF≈FфR┌░╒f√uЖ2р┌Ф&"─╒FeЖ2б┐р'FВFб"б⌠р&ЖF≈7ф▓"бВ&√VГFF√ЖЦр&┌"ю╒FVвфFSвFVвфFRб6ЖфВ%ЖF≈67&WFUВ6WVVФ6Sу╢4ТдУ%5╡&√ФfР%урю╒FW┤Cр'FВFб"ю╒░╒f√uЖ2ГWFFUВG&6W2┤FW┤GВ6≈F√ЖЦр&ВWG6√FR"бFW┤FfЖГEВ6≈╕Sс░╒Vг6S═╒f√uЖ2рЖVвG∙Жf√wW&R┌%6VрFFВ2В"FW'FжVГFР"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌ж'▓ж╒╤Wр"░╒f√uЖ2рЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uЖ2ГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррFVФF√жVГFВ2В"6Фб├&'&2▓рррп╒G'⌠═╒FeЖ6Ф≈2рvWEЖWfVГG5Ж'∙Ж6Фб├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeЖ6Ф≈2ФVвG⌠═╒FeЖ6Ф≈5╡&6ФеЖF≈7ф▓%ррFeЖ6Ф≈5╡&6Фб%рГ7G"ГF≈FфR┌░╒f√uЖ6Ф≈2р┌Ф&"─╒FeЖ6Ф≈2б┐р&6ФеЖF≈7ф▓"б⌠р'FВFб"ю╒FVвфFSвFVвфFRб6ЖфВ%ЖF≈67&WFUВ6WVVФ6Sу╢4ТдУ%5╡'W'фR%урю╒FW┤Cр'FВFб"ю╒░╒f√uЖ6Ф≈2ГWFFUВG&6W2┤FW┤GВ6≈F√ЖЦр&ВWG6√FR"бFW┤FfЖГEВ6≈╕Sс░╒Vг6S═╒f√uЖ6Ф≈2рЖVвG∙Жf√wW&R┌%6VрFFВ2В"6Фб"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌ж'▓ж6Фц╒╤Wр"░╒f√uЖ6Ф≈2рЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uЖ6Ф≈2ГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррFVвРFR&W7В7FВ"рррп╒G'⌠═╒FeВFVвРрvWEВ&W7ЖГ6UВF√жUЖ'∙Ж├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeВFVвРФVвG⌠═╒FeВFVвУ╡&ЖF≈7ф▓%ррFeВFVвУ╡&%рГ7G"ГF≈FфR┌░╒f√uВFVвРр┌Ф&"─╒FeВFVвРб┐р&ЖF≈7ф▓"б⌠р'FVвУЖжVF√УЖж√Б"ю╒FVвфFSвFVвфFRб6ЖфВ%ЖF≈67&WFUВ6WVVФ6Sу╢4ТдУ%5╡&В&ФvR%урю╒FW┤Cр'FVвУЖжVF√УЖж√Б"ю╒░╒f√uВFVвРГWFFUВG&6W2┤FW┤GВ6≈F√ЖЦр&ВWG6√FR"бFW┤FfЖГEВ6≈╕SсбFW┤GFVвфFSр"W╥FW┤Gрж√Б"░╒Vг6S═╒f√uВFVвРрЖVвG∙Жf√wW&R┌%6VрFFВ2FRFVвРFR&W7В7F"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌в&W7ЖГ6RвF√жS╒╤Wр"░╒f√uВFVвРрЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uВFVвРГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррFVФL:╕Ф6√F°:&√┤7F6╤VBВ"7FGW2▓рррп╒G'⌠═╒FeЖF√г▓рvWEЖF√г∙ВG&VФB├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeЖF√г▓ФVвG⌠═╒6ЖфВ%Жжр╡$&W'FВ2#╒4ТдУ%5╡'v&Ф√Фr%рб$VрФFжVГFР#╒4ТдУ%5╡&В&ФvR%рб$6ЖФ6г\:жFВ2#╒4ТдУ%5╡'7V66W72%вп╒f√uЖF√г▓р┌Ф&"─╒FeЖF√г▓б┐р&F√"б⌠р'FВFб"б6ЖфВ#р'7FGW2"ю╒FVвфFSвFVвфFRб&&жЖFSр'7F6╡"ю╒6ЖфВ%ЖF≈67&WFUЖжж6ЖфВ%Жжю╒░╒Vг6S═╒f√uЖF√г▓рЖVвG∙Жf√wW&R┌%6VрFFВ2FRFVФL:╕Ф6√"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌жF√г⌠╒╤Wр"░╒f√uЖF√г▓рЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uЖF√г▓ГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррFВ6ЖвVФ√6ГFW2рррп╒G'⌠═╒FeЖ6ЖррvWEВFВЖ6ЖвVФ√6ГFW2├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"бF≈2░╒√bФВBFeЖ6ЖрФVвG⌠═╒FeЖ6Жу╡&6ЖвVФ√6ГFUЖF≈7ф▓%ррFeЖ6Жу╡&6ЖвVФ√6ГFR%рГ7G"ГF≈FфR┌░╒f√uЖ6Жрр┌Ф&"─╒FeЖ6Жрб┐р'FВFб"б⌠р&6ЖвVФ√6ГFUЖF≈7ф▓"бВ&√VГFF√ЖЦр&┌"ю╒FVвфFSвFVвфFRб6ЖфВ%ЖF≈67&WFUВ6WVVФ6Sу╢4ТдУ%5╡'7V66W72%урю╒FW┤Cр'FВFб"ю╒░╒f√uЖ6ЖрГWFFUВG&6W2┤FW┤GВ6≈F√ЖЦр&ВWG6√FR"бFW┤FfЖГEВ6≈╕Sс░╒Vг6S═╒f√uЖ6ЖррЖVвG∙Жf√wW&R┌%6VрFFВ2FR6ЖвVФ√6ГFW2"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&Рw&┌вFВж6ЖвVФ√6ГFW3╒╤Wр"░╒f√uЖ6ЖррЖVвG∙Жf√wW&R┌$W'&РР6'&Vv"FFВ2"░═╒f√uЖ6ЖрГWFFUЖф√ВWB┘Ж6├'EЖф√ВWB├├V√v┤Cс3S▓░═╒2ррррF&Vф&V6VГFRрррп╒G'⌠═╒FeВ&V6VГBрvWEВ&V6VГEЖWfVГG2├Жf√гFW"б6ФеЖf√гFW"б6ЖвVФ√6ГFUЖf√гFW"б#R░╒√bФВBFeВ&V6VГBФVвG⌠═╒2fВ&жF"7FGW26Жр&FvW26ЖфВ&√FВ0╒FVbЖfВ&жEВ7FGW2┤7FGW2⌠═╒6ЖфВ'5Жжр╡&&W'FР#╒'v&Ф√Фr"б&VуЖФFжVГFР#╒&√ФfР"б&6ЖФ6гV√FР#╒'7V66W72'п╒ф&Vг5Жжр╡&&W'FР#╒$&W'FР"б&VуЖФFжVГFР#╒$VрФFжVГFР"б&6ЖФ6гV√FР#╒$6ЖФ6г\:жFР'п╒&WGW&Бф&Vг5ЖжФvWB┤7FGW2б7FGW2В".(	B"░═╒FeВ&V6VГE╡%7FGW2%ррFeВ&V6VГE╡%7FGW2%рФг▓┘ЖfВ&жEВ7FGW2░╒FeВ&V6VГE╡$FW'FжVГFР%ррFeВ&V6VГE╡$FW'FжVГFР%рГ7G"ГF≈FфR┌░╒FeВ&V6VГE╡$6Фб%ррFeВ&V6VГE╡$6Фб%рГ7G"ГF≈FфR┌░═╒F&фRрF&2ЕF&фRФg&ЖуЖFFg&жR─╒FeВ&V6VГBб7G&≈VCуG'VRб&В&FW&VCтfг6Rб├ВfW#уG'VRбF&ЁуG'VRю╒7G√фSв╡&fЖГE6≈╕R#╒#Ц┤&Vр'рю╒░╒Vг6S═╒F&фRр┤FжбЕ┌$ФVФ┤VрFVФF√жVГFР&Vv≈7G&FРБ"б6ф74ФжSр'FW┤BжвWFVBFW┤Bж6VГFW"▓сB"░╒W├6WBW├6WF√ЖБ2S═╒фЖvvW"ФW'&В"├b$W'&РF&Vф╒╤Wр"░╒F&фRр┤FжбЕ┌$W'&РР6'&Vv"FFВ2Б"б6ф74ФжSр'FW┤BжFФvW"FW┤Bж6VГFW"▓сB"░═╒2ррррF√жW7Fврррп╒ФВuВ7G"рFFWF√жRФФВr┤F√жW╕ЖФRГWF2▓Г7G&gF√жR┌$GVф≈╕FРVрVBРVрРU▓T┐╒Tс╒U2UD2"░═╒&WGW&Б╥∙Ж6&G2бf√uВ7FGW2бf√uЖ2бf√uЖ6Ф≈2бf√uВFVвРбf√uЖF√г▓бf√uЖ6ЖрбF&фRбФВuВ7G ══╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╒2├VгW'0╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╕FVbЖ6├'EЖф√ВWB├├V√v┤Cс3S▓сБF√7C═╒""$ф√ВWBG,:6Р&w,:f√6В2Б"" ╒&WGW&БF√7B─╒W%Ж&v6ЖфВ#р'&v&┐ццц▓"ю╒фВEЖ&v6ЖфВ#р'&v&┐ццц▓"ю╒ж&v√ЦжF√7B├цс#б#с#бCсб#с#▓ю╒├V√v┤Cж├V√v┤Bю╒6├ВvфVvVФCуG'VRю╒фVvVФCжF√7B├В&√VГFF√ЖЦр&┌"б√Ф6├В#р&&ВGFЖр"б⌠сЦ"б├Ф6├В#р'&√v┤B"б┐с▓ю╒fЖГCжF√7B├6ЖфВ#т4ТдУ%5╡'FW┤B%р▓ю╒░══╕FVbЖVвG∙Жf√wW&R├жW76vS╒7G"▓сБvРДf√wW&S═╒""$7&√Vрw,:f√6Рf╕√Р6ЖржVГ6vVрБ"" ╒f√rрvРДf√wW&R┌░╒f√rФFEЖФФВFF√ЖБ┤FW┤CжжW76vRб6├Вv'&Вsтfг6RбfЖГCжF√7B┤6≈╕SсBб6ЖфВ#т4ТдУ%5╡&вWFVB%р▓░╒f√rГWFFUЖф√ВWB─╒W%Ж&v6ЖфВ#р'&v&┐ццц▓"бфВEЖ&v6ЖфВ#р'&v&┐ццц▓"ю╒├├≈3жF√7B┤f≈6√&фSтfг6R▓б√├≈3жF√7B┤f≈6√&фSтfг6R▓ю╒░╒&WGW&Бf√p══╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╒2W├V7\:|:6Р7FФFфЖФP╒2сссссссссссссссссссссссссссссссссссссссссссссссссссссссссссп╕√bУЖФжUУРср%УЖж√ЕУР#═╒F6┘ЖГ'VБ─╒├В7Cв6WGF√Фw2ФF6┘Ж├В7Bю╒В'Cв6WGF√Фw2ФF6┘ВВ'Bю╒FV'Vsв6WGF√Фw2ФF6┘ЖFV'Vrю╒░