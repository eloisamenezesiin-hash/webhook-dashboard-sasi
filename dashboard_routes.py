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


def _add_date_filter(where, params):
    """Adiciona filtro de data_inicio e data_fim se presentes na query string."""
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")
    if data_inicio:
        where.append("data >= %s::date")
        params.append(data_inicio)
    if data_fim:
        where.append("data < (%s::date + INTERVAL '1 day')")
        params.append(data_fim)


def _mnt_equipe_filter(equipe):
    """Retorna (where_clause, params_list) para filtro de equipe Manutenção."""
    if equipe:
        return "equipe = %s", [equipe]
    else:
        return "equipe LIKE %s", ["Manutenção%"]


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
        _add_date_filter(where, params)
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
        where = ["canal IS NOT NULL"]
        params = []
        if equipe:
            where.append("equipe = %s")
            params.append(equipe)
        _add_date_filter(where, params)
        w = " WHERE " + " AND ".join(where)
        cur.execute(
            "SELECT canal, COUNT(*) as total FROM registros" + w +
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
        where = ["equipe IS NOT NULL"]
        params = []
        if canal:
            where.append("canal = %s")
            params.append(canal)
        _add_date_filter(where, params)
        w = " WHERE " + " AND ".join(where)
        cur.execute(
            "SELECT equipe, COUNT(*) as total FROM registros" + w +
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
        _add_date_filter(where, params)
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
        _add_date_filter(where, params)
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
        _add_date_filter(where, params)
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
                "evento": msg or tipo or "",
                "mensagem": msg or "",
                "equipe": eq or "",
                "usuario": site or "",
                "comunicante": comunicante or "",
                "status": "sucesso",
            })
        return jsonify({"eventos": eventos, "total": len(eventos)})
    except Exception as e:
        return jsonify({"eventos": [], "total": 0, "erro": str(e)})


# ================================================================
# 7. /api/dashboard/resumo - Resumo geral para o painel
# ================================================================
@dashboard_bp.route("/api/dashboard/resumo")
def api_resumo():
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

        w7d = " WHERE data >= NOW() - INTERVAL '7 days'"
        if where:
            w7d += " AND " + " AND ".join(where)
        cur.execute("SELECT COUNT(*) FROM registros" + w7d, params)
        total_7d = cur.fetchone()[0]

        cur.close()
        conn.close()

        return jsonify({
            "total_registros": total,
            "registros_24h": total_24h,
            "registros_7d": total_7d,
        })
    except Exception as e:
        return jsonify({
            "erro": str(e),
            "total_registros": 0,
            "registros_24h": 0,
            "registros_7d": 0,
        })


# ================================================================
# 8. /api/dashboard/filtros - Valores para os dropdowns
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
        _add_date_filter(where, params)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            "SELECT data, canal, tipo, equipe, site_nome, mensagem "
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
        writer.writerow(["Data/Hora", "Canal", "Tipo", "Equipe", "Site", "Mensagem"])
        for data, cn, tipo, eq, site, msg in rows:
            writer.writerow([
                data.strftime("%d/%m/%Y %H:%M:%S") if data else "",
                cn or "", tipo or "", eq or "", site or "", msg or "",
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
# 9. /api/debug/raw-sample - Ver estrutura do JSON bruto (temporario)
# ================================================================
@dashboard_bp.route("/api/debug/raw-sample")
def api_debug_raw():
    """Retorna amostras do raw_json da tabela webhook_logs para análise."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        # Descobrir colunas da tabela webhook_logs
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'webhook_logs' ORDER BY ordinal_position"
        )
        cols_wl = [r[0] for r in cur.fetchall()]

        # Descobrir colunas da tabela registros
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'registros' ORDER BY ordinal_position"
        )
        cols_reg = [r[0] for r in cur.fetchall()]

        # Buscar amostras do raw_json
        cur.execute(
            "SELECT id, raw_json FROM webhook_logs "
            "ORDER BY id DESC LIMIT 3"
        )
        rows = cur.fetchall()

        # Buscar amostras de registros com comunicante (Saída)
        cur.execute(
            "SELECT data, canal, tipo, equipe, site_nome, mensagem, comunicante "
            "FROM registros WHERE canal LIKE 'Saída%' OR canal LIKE 'Sa_da%' "
            "ORDER BY data DESC LIMIT 5"
        )
        reg_rows = cur.fetchall()

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

        registros_sample = []
        for dt, cn, tp, eq, sn, msg, com in reg_rows:
            registros_sample.append({
                "data": dt.strftime("%d/%m/%Y %H:%M:%S") if dt else "",
                "canal": cn or "",
                "tipo": tp or "",
                "equipe": eq or "",
                "site_nome": sn or "",
                "mensagem": msg or "",
                "comunicante": com or "",
            })

        return jsonify({
            "colunas_webhook_logs": cols_wl,
            "colunas_registros": cols_reg,
            "total_samples": len(samples),
            "samples": samples,
            "registros_saida_sample": registros_sample,
        })
    except Exception as e:
        return jsonify({"erro": str(e)})


# ================================================================
# 9b. /api/debug/find-status - Encontrar path do status_do_servico
# ================================================================
@dashboard_bp.route("/api/debug/find-status")
def api_debug_find_status():
    """Busca registros com status_do_servico e mostra estrutura JSON completa."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, raw_json FROM webhook_logs "
            "WHERE raw_json ILIKE %s LIMIT 3",
            ["%status_do_servico%"]
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        results = []
        for row_id, raw in rows:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                parsed = {"_parse_error": str(raw)[:500]}

            # Buscar recursivamente onde status_do_servico aparece
            def find_key(obj, target, path=""):
                found = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        current = f"{path}.{k}" if path else k
                        if k == target:
                            found.append({"path": current, "value": v})
                        found.extend(find_key(v, target, current))
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        found.extend(find_key(item, target, f"{path}[{i}]"))
                return found

            paths = find_key(parsed, "status_do_servico")

            results.append({
                "id": row_id,
                "keys_nivel_1": list(parsed.keys()) if isinstance(parsed, dict) else [],
                "status_do_servico_paths": paths,
                "full_json": parsed,
            })

        return jsonify({
            "total_found": len(results),
            "results": results,
        })
    except Exception as e:
        return jsonify({"erro": str(e)})


# ================================================================
# 10. /api/manutencao/stats - KPIs do Dashboard Manutenção (Saída)
# ================================================================
@dashboard_bp.route("/api/manutencao/stats")
def api_manutencao_stats():
    """KPIs focados em Manutenção: total saída, por técnico, por status."""
    equipe = request.args.get("equipe")
    step = "init"
    try:
        step = "connect"
        conn = _get_conn()
        cur = conn.cursor()

        step = "filter"
        eq_clause, eq_params = _mnt_equipe_filter(equipe)

        base_where = [eq_clause]
        base_params = list(eq_params)
        _add_date_filter(base_where, base_params)
        w = " WHERE " + " AND ".join(base_where)

        step = "total"
        sql_total = "SELECT COUNT(*) FROM registros" + w
        cur.execute(sql_total, base_params)
        total = cur.fetchone()[0]

        step = "saida"
        cur.execute(sql_total + " AND (canal LIKE %s OR canal LIKE %s)",
                    base_params + ["Saída%", "Sa_da%"])
        total_saida = cur.fetchone()[0]

        step = "entrada"
        cur.execute(sql_total + " AND canal LIKE %s",
                    base_params + ["Entrada%"])
        total_entrada = cur.fetchone()[0]

        # Contar OS por status usando campo do formulário no webhook_logs
        # Path: raw_json::jsonb->'data'->'meta'->'data'->>'status_do_servico_id_1'
        step = "status_webhook"
        status_sql = """
            SELECT
                raw_json::jsonb->'data'->'meta'->'data'->>'status_do_servico_id_1' as status,
                COUNT(*) as total
            FROM webhook_logs
            WHERE raw_json::jsonb->'data'->'meta'->'data'->>'status_do_servico_id_1' IS NOT NULL
        """
        status_params = []

        # Filtro de data (usa campo data da tabela webhook_logs)
        data_inicio = request.args.get("data_inicio")
        data_fim = request.args.get("data_fim")
        if data_inicio:
            status_sql += " AND data >= %s::date"
            status_params.append(data_inicio)
        if data_fim:
            status_sql += " AND data < (%s::date + INTERVAL '1 day')"
            status_params.append(data_fim)

        status_sql += " GROUP BY 1"
        cur.execute(status_sql, status_params)
        status_rows = cur.fetchall()

        os_concluidas = 0
        os_pendentes = 0
        for status_val, cnt in status_rows:
            if status_val == "concluido":
                os_concluidas = cnt
            elif status_val == "com_pendencia":
                os_pendentes = cnt

        cur.close()
        conn.close()

        return jsonify({
            "total_alertas": total,
            "total_saida": total_saida,
            "total_entrada": total_entrada,
            "os_concluidas": os_concluidas,
            "os_pendentes": os_pendentes,
            "v": 4,
        })
    except Exception as e:
        import traceback
        return jsonify({
            "erro": str(e),
            "step": step,
            "trace": traceback.format_exc()[-500:],
            "total_alertas": 0, "total_saida": 0,
            "total_entrada": 0, "os_concluidas": 0, "os_pendentes": 0,
        })


# ================================================================
# 11. /api/manutencao/por-tecnico - Saída agrupada por comunicante
# ================================================================
@dashboard_bp.route("/api/manutencao/por-tecnico")
def api_manutencao_por_tecnico():
    """Agrupa entradas e saídas por comunicante (técnico)."""
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()

        eq_clause, eq_params = _mnt_equipe_filter(equipe)

        base_where = [eq_clause, "comunicante IS NOT NULL", "comunicante != ''"]
        base_params = list(eq_params)
        _add_date_filter(base_where, base_params)
        w = " WHERE " + " AND ".join(base_where)

        # Saídas por técnico
        saida_params = base_params + ["Saída%", "Sa_da%"]
        cur.execute(
            "SELECT comunicante, COUNT(*) as total FROM registros" + w +
            " AND (canal LIKE %s OR canal LIKE %s)"
            " GROUP BY comunicante ORDER BY total DESC LIMIT 20",
            saida_params
        )
        saidas = {r[0]: r[1] for r in cur.fetchall()}

        # Entradas por técnico
        entrada_params = base_params + ["Entrada%"]
        cur.execute(
            "SELECT comunicante, COUNT(*) as total FROM registros" + w +
            " AND canal LIKE %s"
            " GROUP BY comunicante ORDER BY total DESC LIMIT 20",
            entrada_params
        )
        entradas = {r[0]: r[1] for r in cur.fetchall()}

        cur.close()
        conn.close()

        # Combinar todos os técnicos
        todos = set(list(saidas.keys()) + list(entradas.keys()))
        tecnicos = []
        for nome in todos:
            tecnicos.append({
                "nome": nome,
                "entradas": entradas.get(nome, 0),
                "saidas": saidas.get(nome, 0),
            })
        tecnicos.sort(key=lambda x: x["saidas"] + x["entradas"], reverse=True)

        return jsonify({"tecnicos": tecnicos[:20]})
    except Exception as e:
        return jsonify({"tecnicos": [], "erro": str(e)})


# ================================================================
# 12. /api/manutencao/por-cliente - Saídas agrupadas por site/unidade
# ================================================================
@dashboard_bp.route("/api/manutencao/por-cliente")
def api_manutencao_por_cliente():
    """Agrupa saídas por site_nome (cliente/unidade)."""
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()

        eq_clause, eq_params = _mnt_equipe_filter(equipe)

        base_where = [eq_clause]
        base_params = list(eq_params)
        _add_date_filter(base_where, base_params)
        w = " WHERE " + " AND ".join(base_where)

        # Por site_nome
        site_params = base_params + ["Saída%", "Sa_da%"]
        cur.execute(
            "SELECT site_nome, COUNT(*) as total FROM registros" + w +
            " AND (canal LIKE %s OR canal LIKE %s)"
            " AND site_nome IS NOT NULL AND site_nome != ''"
            " GROUP BY site_nome ORDER BY total DESC LIMIT 15",
            site_params
        )
        por_site = [{"nome": r[0], "total": r[1]} for r in cur.fetchall()]

        # Por código @@NNN extraído da mensagem
        cod_params = base_params + ["Saída%", "Sa_da%"]
        cur.execute(
            "SELECT "
            "  SUBSTRING(mensagem FROM '@@[0-9]+') as cod_unidade, "
            "  COUNT(*) as total "
            "FROM registros" + w +
            " AND (canal LIKE %s OR canal LIKE %s)"
            " AND mensagem ~ '@@[0-9]+'"
            " GROUP BY cod_unidade ORDER BY total DESC LIMIT 15",
            cod_params
        )
        por_codigo = [{"codigo": r[0], "total": r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()

        return jsonify({"por_site": por_site, "por_codigo": por_codigo})
    except Exception as e:
        return jsonify({"por_site": [], "por_codigo": [], "erro": str(e)})


# ================================================================
# 13. /api/manutencao/por-canal - Saídas agrupadas por canal
# ================================================================
@dashboard_bp.route("/api/manutencao/por-canal")
def api_manutencao_por_canal():
    """Serviços por canal de saída."""
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()

        eq_clause, eq_params = _mnt_equipe_filter(equipe)

        base_where = [eq_clause, "canal IS NOT NULL"]
        base_params = list(eq_params)
        _add_date_filter(base_where, base_params)
        w = " WHERE " + " AND ".join(base_where)

        canal_params = base_params + ["Saída%", "Sa_da%"]
        cur.execute(
            "SELECT canal, COUNT(*) as total FROM registros" + w +
            " AND (canal LIKE %s OR canal LIKE %s)"
            " GROUP BY canal ORDER BY total DESC",
            canal_params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        canais = [{"nome": r[0], "total": r[1]} for r in rows]
        return jsonify({"canais": canais})
    except Exception as e:
        return jsonify({"canais": [], "erro": str(e)})


# ================================================================
# 14. /api/manutencao/por-mes - Serviços por mês
# ================================================================
@dashboard_bp.route("/api/manutencao/por-mes")
def api_manutencao_por_mes():
    """Serviços de saída agrupados por mês."""
    equipe = request.args.get("equipe")
    try:
        conn = _get_conn()
        cur = conn.cursor()

        eq_clause, eq_params = _mnt_equipe_filter(equipe)

        base_where = [eq_clause]
        base_params = list(eq_params)
        _add_date_filter(base_where, base_params)
        w = " WHERE " + " AND ".join(base_where)

        mes_params = base_params + ["Saída%", "Sa_da%"]
        cur.execute(
            "SELECT TO_CHAR(data, 'YYYY-MM') as mes, COUNT(*) as total "
            "FROM registros" + w +
            " AND (canal LIKE %s OR canal LIKE %s)"
            " AND data IS NOT NULL"
            " GROUP BY mes ORDER BY mes DESC LIMIT 12",
            mes_params
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        meses_pt = {
            "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
            "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
            "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
        }
        dados = []
        for mes_str, total in reversed(rows):
            partes = mes_str.split("-")
            label = meses_pt.get(partes[1], partes[1]) + "/" + partes[0][2:]
            dados.append({"mes": mes_str, "label": label, "total": total})

        return jsonify({"dados": dados})
    except Exception as e:
        return jsonify({"dados": [], "erro": str(e)})


# ================================================================
# /health - Health check para Render e monitoramento
# ================================================================
@dashboard_bp.route("/health")
def health_check():
    """Endpoint de health check. Testa conexão com o banco."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "database": str(e)}), 503
