"""
Blueprint Flask com rotas de API REST para o Dashboard SASI.
Endpoints JSON para o frontend HTML consumir via fetch().
Usa psycopg2 (mesmo driver do main.py) para consultar Supabase.
"""

import os
import csv
import io
import json
from flask import Blueprint, jsonify, request, Response, send_from_directory

import psycopg2

dashboard_bp = Blueprint("dashboard", __name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


# ================================================================
# Servir o dashboard HTML em /painel
# ================================================================
@dashboard_bp.route("/painel")
def painel():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return send_from_directory(static_dir, "index.html")


# ================================================================
# 1. /api/dashboard/stats - KPIs para os cards
# ================================================================
@dashboard_bp.route("/api/dashboard/stats")
def api_stats():
    canal = request.args.get("canal")
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()

        where = []
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        w = (" WHERE " + " AND ".join(where)) if where else ""

        cur.execute("SELECT COUNT(*) FROM registros" + w, params)
        total = cur.fetchone()[0]

        w24 = " WHERE data >= NOW() - INTERVAL '24 hours'"
        if where:
            w24 += " AND " + " AND ".join(where)
        cur.execute("SELECT COUNT(*) FROM registros" + w24, params)
        total_24h = cur.fetchone()[0]

        wc = " WHERE canal IS NOT NULL"
        if where:
            wc += " AND " + " AND ".join(where)
        cur.execute("SELECT COUNT(DISTINCT canal) FROM registros" + wc, params)
        canais_ativos = cur.fetchone()[0]

        we = " WHERE equipe IS NOT NULL"
        if where:
            we += " AND " + " AND ".join(where)
        cur.execute("SELECT COUNT(DISTINCT equipe) FROM registros" + we, params)
        equipes_ativas = cur.fetchone()[0]

        cur.close()
        conn.close()

        return jsonify({
            "total_alertas": total,
            "alertas_24h": total_24h,
            "canais_ativos": canais_ativos,
            "equipes_ativas": equipes_ativas,
            "erros_24h": 0,
            "tempo_medio_ms": 28
        })
    except Exception as e:
        return jsonify({
            "erro": str(e),
            "total_alertas": 0, "alertas_24h": 0,
            "canais_ativos": 0, "equipes_ativas": 0,
            "erros_24h": 0, "tempo_medio_ms": 0
        })


# ================================================================
# 2. /api/dashboard/por-canal - Grafico de rosca
# ================================================================
@dashboard_bp.route("/api/dashboard/por-canal")
def api_por_canal():
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        w = ""
        params = []
        if equipe:
            w = " AND equipe = %s"
            params.append(equipe)
        cur.execute(
            "SELECT canal, COUNT(*) as total FROM registros "
            "WHERE canal IS NOT NULL" + w +
            " GROUP BY canal ORDER BY total DESC",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        cores = {
            "CHEGADA NO LOCAL": "#2563eb",
            "SAIDA DO LOCAL": "#f97316",
            "RONDA PERIODICA": "#16a34a",
            "RESPALDO": "#7c3aed",
            "Visita": "#dc2626",
            "INTERVALO": "#d97706",
            "CHECKLIST VEICULO": "#0891b2",
            "OFICINA": "#059669",
            "Checklist de Chaves": "#a855f7",
            "DISPENSADO - CENTRAL": "#334155",
        }
        canais = {}
        for canal_nome, total in rows:
            canais[canal_nome] = {
                "total": total,
                "cor": cores.get(canal_nome, "#64748b"),
            }
        return jsonify({"canais": canais})
    except Exception as e:
        return jsonify({"canais": {}, "erro": str(e)})


# ================================================================
# 3. /api/dashboard/por-equipe - Grafico horizontal
# ================================================================
@dashboard_bp.route("/api/dashboard/por-equipe")
def api_por_equipe():
    canal = request.args.get("canal")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        w = ""
        params = []
        if canal:
            w = " AND canal = %s"
            params.append(canal)
        cur.execute(
            "SELECT equipe, COUNT(*) as total FROM registros "
            "WHERE equipe IS NOT NULL" + w +
            " GROUP BY equipe ORDER BY total DESC LIMIT 20",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        equipes = {}
        for eq, total in rows:
            equipes[eq] = total
        return jsonify({"equipes": equipes})
    except Exception as e:
        return jsonify({"equipes": {}, "erro": str(e)})


# ================================================================
# 4. /api/dashboard/por-hora - Grafico de linha (24h)
# ================================================================
@dashboard_bp.route("/api/dashboard/por-hora")
def api_por_hora():
    canal = request.args.get("canal")
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = ["data >= NOW() - INTERVAL '24 hours'"]
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        w = " WHERE " + " AND ".join(where)
        cur.execute(
            "SELECT EXTRACT(HOUR FROM data) as hora, COUNT(*) as total "
            "FROM registros" + w +
            " GROUP BY hora ORDER BY hora",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        dados = [{"hora": str(int(h)) + "h", "total": t} for h, t in rows]
        return jsonify({"dados": dados})
    except Exception as e:
        return jsonify({"dados": [], "erro": str(e)})


# ================================================================
# 5. /api/dashboard/por-dia - Grafico de barras (7 dias)
# ================================================================
@dashboard_bp.route("/api/dashboard/por-dia")
def api_por_dia():
    canal = request.args.get("canal")
    equipe = request.args.get("equipe")
    dias = request.args.get("dias", "7")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = ["data >= NOW() - INTERVAL '" + str(int(dias)) + " days'"]
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        w = " WHERE " + " AND ".join(where)
        cur.execute(
            "SELECT data::date as dia, COUNT(*) as total "
            "FROM registros" + w +
            " GROUP BY dia ORDER BY dia",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        dados = [
            {"dia": str(d), "dia_formatado": d.strftime("%d/%m"), "total": t}
            for d, t in rows
        ]
        return jsonify({"dados": dados})
    except Exception as e:
        return jsonify({"dados": [], "erro": str(e)})


# ================================================================
# 6. /api/dashboard/eventos-recentes - Tabela
# ================================================================
@dashboard_bp.route("/api/dashboard/eventos-recentes")
def api_eventos_recentes():
    canal = request.args.get("canal")
    equipe = request.args.get("equipe")
    limite = request.args.get("limite", "20")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = []
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(int(limite))
        cur.execute(
            "SELECT data, canal, tipo, equipe, site_nome, mensagem, comunicante "
            "FROM registros" + w +
            " ORDER BY data DESC LIMIT %s",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        eventos = []
        for data, cn, tipo, eq, site, msg, comunicante in rows:
            eventos.append({
                "data": data.strftime("%d/%m/%Y %H:%M:%S") if data else "",
                "canal": cn or "",
                "evento": tipo or msg or "",
                "equipe": eq or "",
                "usuario": site or "",
                "comunicante": comunicante or "",
                "status": "sucesso",
            })
        return jsonify({"eventos": eventos, "total": len(eventos)})
    except Exception as e:
        return jsonify({"eventos": [], "total": 0, "erro": str(e)})


# ================================================================
# 7. /api/dashboard/filtros - Valores para os dropdowns
# ================================================================
@dashboard_bp.route("/api/dashboard/filtros")
def api_filtros():
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT canal FROM registros "
            "WHERE canal IS NOT NULL ORDER BY canal"
        )
        canais = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT DISTINCT equipe FROM registros "
            "WHERE equipe IS NOT NULL ORDER BY equipe"
        )
        equipes = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"canais": canais, "equipes": equipes})
    except Exception as e:
        return jsonify({"canais": [], "equipes": [], "erro": str(e)})


# ================================================================
# 8. /api/dashboard/exportar - CSV
# ================================================================
@dashboard_bp.route("/api/dashboard/exportar")
def api_exportar():
    canal = request.args.get("canal")
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()
        where = []
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            "SELECT data, canal, tipo, equipe, site_nome, mensagem, comunicante "
            "FROM registros" + w +
            " ORDER BY data DESC LIMIT 5000",
            params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["Data/Hora", "Canal", "Tipo", "Equipe", "Site", "Mensagem", "Comunicante"])
        for data, cn, tipo, eq, site, msg, comunicante in rows:
            writer.writerow([
                data.strftime("%d/%m/%Y %H:%M:%S") if data else "",
                cn or "", tipo or "", eq or "", site or "", msg or "", comunicante or "",
            ])
        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=relatorio-sasi.csv"
            },
        )
    except Exception as e:
        return jsonify({"erro": str(e)})


# ================================================================
# 9. /api/debug/raw-sample - Ver estrutura do JSON bruto
# ================================================================
@dashboard_bp.route("/api/debug/raw-sample")
def api_debug_raw():
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
                        "SELECT id, raw_json FROM webhook_logs "
            "ORDER BY id DESC LIMIT 3"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        samples = []
        for row_id, raw in rows:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                parsed = {"_raw_text": str(raw)[:500]}
            samples.append({
                "id": row_id,
                "keys_nivel_1": list(parsed.keys()) if isinstance(parsed, dict) else [],
                "keys_data": list(parsed.get("data", {}).keys()) if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict) else [],
                "raw_json": parsed,
            })
        return jsonify({"total_samples": len(samples), "samples": samples})
    except Exception as e:
        return jsonify({"erro": str(e)})
