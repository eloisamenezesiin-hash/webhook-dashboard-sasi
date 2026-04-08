from flask import Flask, request, jsonify
import json
import os
import psycopg2
import time
import hashlib
import functools
from dashboard_routes import dashboard_bp

app = Flask(__name__)
app.register_blueprint(dashboard_bp)


# -- Rota temporaria para diagnostico Redis --
@app.route("/redis-test")
def redis_test():
    import os, traceback
    info = {"redis_url_set": bool(os.environ.get("REDIS_URL")),
            "redis_url_prefix": (os.environ.get("REDIS_URL") or "")[:30]}
    try:
        from redis import Redis
        info["redis_import"] = "ok"
    except ImportError as e:
        info["redis_import"] = str(e)
        # --- Diagnostic: test cache functions directly ---
    try:
        from dashboard_routes import _cache_set, _cache_get, _cache_key
        with app.test_request_context('/diag'):
            try:
                key = _cache_key("_diag_test")
                info["diag_cache_key"] = key
            except Exception as e:
                info["diag_key_error"] = str(e)
            try:
                _cache_set("_diag_test", {"test": True, "n": 42}, ttl=60)
                info["diag_cache_set"] = "ok"
            except Exception as e:
                info["diag_set_error"] = str(e)
            try:
                got = _cache_get("_diag_test")
                info["diag_cache_get"] = got
            except Exception as e:
                info["diag_get_error"] = str(e)
        if bp_r:
            info["dash_keys_after"] = bp_r.keys("dash:*")[:20]
    except ImportError as e:
        info["diag_import_error"] = str(e)
        return jsonify(info)
    try:
        r = Redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True, socket_timeout=2)
        pong = r.ping()
        info["ping"] = pong
        r.set("_debug_test", "hello", ex=30)
        val = r.get("_debug_test")
        info["set_get"] = val
        info["status"] = "connected"
        # List all dash:* keys
        keys = r.keys("dash:*")
        info["cache_keys"] = keys[:20]
        info["cache_key_count"] = len(keys)
    except Exception as e:
        info["error"] = str(e)
        info["traceback"] = traceback.format_exc()
        info["status"] = "failed"
    # Test blueprint's _get_redis
    try:
        from dashboard_routes import _get_redis, REDIS_URL as DR_REDIS_URL
        info["blueprint_redis_url_set"] = bool(DR_REDIS_URL)
        bp_r = _get_redis()
        info["blueprint_get_redis"] = "connected" if bp_r else "None"
        if bp_r:
            bp_r.set("_bp_test", "world", ex=30)
            info["blueprint_set_get"] = bp_r.get("_bp_test")
    except Exception as e:
        info["blueprint_error"] = str(e)
    return jsonify(info)

# ── Auto-migração: adicionar coluna comunicante
def _run_migrations():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS comunicante TEXT")
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass

_run_migrations()

DATABASE_URL = os.environ.get("DATABASE_URL")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

# ── Rate Limiter simples em memória ──────────────────────────────
RATE_LIMIT_WINDOW = 60   # segundos
RATE_LIMIT_MAX = 60      # requisições por janela
_rate_store = {}

def _check_rate_limit(ip):
    now = time.time()
    if ip not in _rate_store:
        _rate_store[ip] = []
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_store[ip].append(now)
    return True

# ── Limite do fila.txt (500 KB) ─────────────────────────────────
FILA_MAX_BYTES = 500_000

def _append_fila(raw):
    try:
        if os.path.exists("fila.txt") and os.path.getsize("fila.txt") > FILA_MAX_BYTES:
            return
        with open("fila.txt", "a") as f:
            f.write(raw + "\n")
    except Exception:
        pass

# ── Conexão DB com context manager ──────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL)


@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        admin_email = os.environ.get("ADMIN_EMAIL", "eloisamenezes.iin@gmail.com")
        if email == admin_email and DASHBOARD_PASSWORD:
            try:
                import smtplib
                from email.mime.text import MIMEText
                smtp_user = os.environ.get("SMTP_USER", "")
                smtp_pass = os.environ.get("SMTP_PASS", "")
                if smtp_user and smtp_pass:
                    msg = MIMEText("Sua senha do Dashboard IIN: " + DASHBOARD_PASSWORD)
                    msg["Subject"] = "Dashboard IIN - Recuperacao de Senha"
                    msg["From"] = smtp_user
                    msg["To"] = admin_email
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                        s.login(smtp_user, smtp_pass)
                        s.send_message(msg)
            except Exception:
                pass
        return """<!DOCTYPE html><html><head><title>Senha Enviada</title>
<style>*{margin:0;font-family:Arial,sans-serif}body{background:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{background:white;padding:40px;border-radius:12px;text-align:center;max-width:380px;box-shadow:0 4px 24px rgba(0,0,0,.2)}h2{color:#1e293b;margin-bottom:12px}p{color:#64748b;margin-bottom:20px}a{color:#2563eb;text-decoration:none}</style></head>
<body><div class="box"><h2>Email Enviado</h2><p>Se o email informado estiver cadastrado, a senha sera enviada em instantes.</p><a href="/">Voltar ao login</a></div></body></html>"""

    return """<!DOCTYPE html><html><head><title>Esqueci a Senha</title>
<style>*{margin:0;font-family:Arial,sans-serif}body{background:#1e293b;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{background:white;padding:40px;border-radius:12px;text-align:center;max-width:380px;box-shadow:0 4px 24px rgba(0,0,0,.2)}h2{color:#1e293b;margin-bottom:8px}p{color:#64748b;margin-bottom:16px}input{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:15px;box-sizing:border-box;margin-bottom:12px}button{width:100%;padding:10px;background:#2563eb;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}a{color:#2563eb;text-decoration:none;font-size:13px}</style></head>
<body><div class="box"><h2>Recuperar Senha</h2><p>Digite seu email cadastrado</p><form method="POST"><input name="email" type="email" placeholder="seu@email.com" required><button type="submit">Enviar</button></form><p style="margin-top:16px"><a href="/">Voltar ao login</a></p></div></body></html>"""

@app.route("/webhook", methods=["POST"])
def webhook():
    # Rate limiting
    client_ip = request.remote_addr or "unknown"
    if not _check_rate_limit(client_ip):
        return jsonify({"status": "erro", "mensagem": "Muitas requisições. Tente novamente em breve."}), 429

    data = request.json
    raw = json.dumps(data) if data else request.get_data(as_text=True)

    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # Extrair campos do JSON do SASI
        sasi = data.get("data", {}) if data else {}
        channel = sasi.get("Channel", {}) or {}
        group = sasi.get("Group", {}) or {}
        site = sasi.get("Site", {}) or {}
        location = sasi.get("location", {}) or {}

        canal = channel.get("name", data.get("canal") if data else None)
        mensagem = sasi.get("text", data.get("mensagem") if data else None)
        equipe = group.get("name")
        site_nome = site.get("name")
        tipo = data.get("type") if data else None
        prioridade = sasi.get("priority", 0)
        lat = location.get("lat")
        lng = location.get("lng")
        mobile = sasi.get("MobileProfile", {}) or {}
        comunicante = mobile.get("name")

        cur.execute(
            """INSERT INTO registros (canal, mensagem, equipe, site_nome, tipo, prioridade, lat, lng, comunicante)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (canal, mensagem, equipe, site_nome, tipo, prioridade, lat, lng, comunicante)
        )
        cur.execute(
            "INSERT INTO webhook_logs (raw_json) VALUES (%s)",
            (raw,)
        )
        conn.commit()
        cur.close()
        return jsonify({"status": "ok", "destino": "banco"}), 200

    except Exception:
        _append_fila(raw or json.dumps(data))
        return jsonify({"status": "ok", "destino": "fila"}), 200

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/", methods=["GET"])
def home():
    # Proteção do dashboard (se senha configurada)
    if DASHBOARD_PASSWORD:
        auth_cookie = request.cookies.get("dash_auth", "")
        expected = hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()[:16]
        if auth_cookie != expected:
            senha = request.args.get("senha", "")
            if senha == DASHBOARD_PASSWORD:
                from flask import make_response
                resp = make_response("")
                resp.set_cookie("dash_auth", expected, max_age=86400, httponly=True)
                resp.headers["Location"] = "/"
                resp.status_code = 302
                return resp
            return """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#1a1a2e;margin:0}
.box{background:white;padding:40px;border-radius:12px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.3)}
input{padding:10px;margin:10px 0;border:1px solid #ccc;border-radius:6px;width:200px}
button{padding:10px 30px;background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer}
button:hover{background:#1557b0}</style></head>
<body><div class="box"><h2>Dashboard IIN</h2><p>Digite a senha para acessar</p>
<form method="GET" action="/"><input type="password" name="senha" placeholder="Senha" required>
<br><button type="submit" style="width:100%;padding:10px;background:#2563eb;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer;margin-top:8px">Entrar</button></form><p style="margin-top:16px"><a href="/esqueci-senha" style="color:#2563eb;text-decoration:none;font-size:13px">Esqueci minha senha</a></p></div></body></html>""", 401

    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM registros")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM registros WHERE data >= NOW() - INTERVAL '24 hours'")
        hoje = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT canal) FROM registros WHERE canal IS NOT NULL")
        canais_ativos = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT equipe) FROM registros WHERE equipe IS NOT NULL")
        equipes_ativas = cur.fetchone()[0]

        # Alertas por canal (top 10)
        cur.execute("""SELECT canal, COUNT(*) as total FROM registros
                       WHERE canal IS NOT NULL GROUP BY canal ORDER BY total DESC LIMIT 10""")
        por_canal = cur.fetchall()

        # Alertas por equipe
        cur.execute("""SELECT equipe, COUNT(*) as total FROM registros
                       WHERE equipe IS NOT NULL GROUP BY equipe ORDER BY total DESC LIMIT 10""")
        por_equipe = cur.fetchall()

        # Alertas por hora (ultimas 24h)
        cur.execute("""SELECT EXTRACT(HOUR FROM data AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') as hora, COUNT(*) as total FROM registros
                       WHERE data >= NOW() - INTERVAL '24 hours' GROUP BY hora ORDER BY hora""")
        por_hora = cur.fetchall()

        # Alertas por dia (ultimos 7 dias)
        cur.execute("""SELECT (data AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date as dia, COUNT(*) as total FROM registros
                       WHERE data >= NOW() - INTERVAL '7 days' GROUP BY dia ORDER BY dia""")
        por_dia = cur.fetchall()

        cur.close()

    except Exception:
        total = hoje = canais_ativos = equipes_ativas = 0
        por_canal = por_equipe = por_hora = por_dia = []

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # Preparar dados para Chart.js
    canal_labels = json.dumps([r[0] or 'N/A' for r in por_canal])
    canal_values = json.dumps([r[1] for r in por_canal])
    equipe_labels = json.dumps([r[0] or 'N/A' for r in por_equipe])
    equipe_values = json.dumps([r[1] for r in por_equipe])
    hora_labels = json.dumps([f"{int(r[0])}h" for r in por_hora])
    hora_values = json.dumps([r[1] for r in por_hora])
    dia_labels = json.dumps([r[0].strftime("%d/%m") for r in por_dia])
    dia_values = json.dumps([r[1] for r in por_dia])

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitoramento IIN</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 15px 30px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(26,115,232,0.3); display: flex; justify-content: space-between; align-items: center; }}
        .header-left {{ display: flex; align-items: center; gap: 20px; }}
        .header-logo img {{ height: 90px; width: auto; }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .header p {{ opacity: 0.85; font-size: 14px; }}
        .refresh-btn {{ background: rgba(255,255,255,0.2); color: white; border: 1px solid rgba(255,255,255,0.3); padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }}
        .refresh-btn:hover {{ background: rgba(255,255,255,0.3); }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: white; padding: 20px 25px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .stat-card .number {{ font-size: 32px; font-weight: bold; color: #1a73e8; }}
        .stat-card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
        .stat-card.green .number {{ color: #0d9488; }}
        .stat-card.orange .number {{ color: #ea580c; }}
        .stat-card.purple .number {{ color: #7c3aed; }}
        .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 20px; margin-bottom: 20px; }}
        .chart-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .chart-card h3 {{ font-size: 16px; color: #333; margin-bottom: 15px; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #999; }}
        .header-actions {{ display: flex; align-items: center; gap: 12px; }}
        .dark-toggle {{ background: rgba(255,255,255,0.15); border: none; cursor: pointer; padding: 8px; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; }}
        .dark-toggle:hover {{ background: rgba(255,255,255,0.3); }}
        .dark-toggle svg {{ width: 22px; height: 22px; }}
        body.dark {{ background: #1a1a2e; color: #e0e0e0; }}
        body.dark .stat-card {{ background: #16213e; border-color: #1a3a5c; }}
        body.dark .stat-card p {{ color: #aaa; }}
        body.dark .chart-card {{ background: #16213e; }}
        body.dark .chart-card h3 {{ color: #e0e0e0; }}
        body.dark .header {{ box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
        body.dark .footer {{ color: #666; }}
        @media (max-width: 768px) {{
            .charts {{ grid-template-columns: 1fr; }}
            .stats {{ grid-template-columns: repeat(2, 1fr); }}
            .header {{ flex-wrap: wrap; justify-content: center; gap: 10px; padding: 15px; }}
            .header-left {{ justify-content: center; gap: 10px; }}
            .header-logo img {{ height: 60px; }}
            .header h1 {{ font-size: 18px; }}
            .header-actions {{ width: 100%; justify-content: center; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <div class="header-logo"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0NjAgMjIwIj4KICA8ZGVmcz4KICAgIDxwYXRoIGlkPSJ0b3BBcmMiIGQ9Ik0gNTAsMTIwIFEgMjMwLDIwIDQxMCwxMjAiIGZpbGw9Im5vbmUiLz4KICAgIDxwYXRoIGlkPSJib3R0b21BcmMiIGQ9Ik0gNzAsMTcwIFEgMjMwLDI1MCAzOTAsMTcwIiBmaWxsPSJub25lIi8+CiAgPC9kZWZzPgogIDwhLS0gQXJjbyBzdXBlcmlvciBmaW5vIGUgbGltcG8gLSBlc3RpbG8gYm9yZGVyLXJhZGl1cyBDU1MgLS0+CiAgPHBhdGggZD0iTSA0MCwxMjggUSAyMzAsMzAgNDIwLDEyOCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJyZ2JhKDI1NSwyNTUsMjU1LDAuNSkiIHN0cm9rZS13aWR0aD0iMS4yIiBzdHJva2UtbGluZWNhcD0icm91bmQiLz4KICA8IS0tIFRleHRvIHN1cGVyaW9yIHNlZ3VpbmRvIG8gYXJjbyAtLT4KICA8dGV4dCBmb250LWZhbWlseT0iJ1RpbWVzIE5ldyBSb21hbicsR2VvcmdpYSxzZXJpZiIgZm9udC1zaXplPSIxNC41IiBmaWxsPSJyZ2JhKDI1NSwyNTUsMjU1LDAuOTUpIiBmb250LXdlaWdodD0iYm9sZCIgbGV0dGVyLXNwYWNpbmc9IjMuNSI+CiAgICA8dGV4dFBhdGggaHJlZj0iI3RvcEFyYyIgc3RhcnRPZmZzZXQ9IjUwJSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+VEhFIElJTiBHUk9VUCBPRiBDT01QQU5JRVM8L3RleHRQYXRoPgogIDwvdGV4dD4KICA8IS0tIExldHJhcyBJSU4gZ3JhbmRlcyBubyBjZW50cm8gLS0+CiAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoMTc4LDgyKSI+CiAgICA8cmVjdCB4PSIwIiB5PSIwIiB3aWR0aD0iOCIgaGVpZ2h0PSI1OCIgcng9IjEuNSIgZmlsbD0id2hpdGUiLz4KICAgIDxyZWN0IHg9IjI0IiB5PSIwIiB3aWR0aD0iOCIgaGVpZ2h0PSI1OCIgcng9IjEuNSIgZmlsbD0id2hpdGUiLz4KICAgIDxyZWN0IHg9IjUyIiB5PSIwIiB3aWR0aD0iOCIgaGVpZ2h0PSI1OCIgcng9IjEuNSIgZmlsbD0id2hpdGUiLz4KICAgIDxwb2x5Z29uIHBvaW50cz0iNTIsMCA2MCwwIDEwMCw1OCA5Miw1OCIgZmlsbD0id2hpdGUiLz4KICAgIDxyZWN0IHg9IjkyIiB5PSIwIiB3aWR0aD0iOCIgaGVpZ2h0PSI1OCIgcng9IjEuNSIgZmlsbD0id2hpdGUiLz4KICA8L2c+CiAgPCEtLSBBcmNvIGluZmVyaW9yIGZpbm8gLS0+CiAgPHBhdGggZD0iTSA2MCwxNjUgUSAyMzAsMjQwIDQwMCwxNjUiIGZpbGw9Im5vbmUiIHN0cm9rZT0icmdiYSgyNTUsMjU1LDI1NSwwLjMpIiBzdHJva2Utd2lkdGg9IjEiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgogIDwhLS0gVGV4dG8gaW5mZXJpb3IgLS0+CiAgPHRleHQgZm9udC1mYW1pbHk9IkFyaWFsLEhlbHZldGljYSxzYW5zLXNlcmlmIiBmb250LXNpemU9IjExLjUiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC44NSkiIGxldHRlci1zcGFjaW5nPSIyLjUiPgogICAgPHRleHRQYXRoIGhyZWY9IiNib3R0b21BcmMiIHN0YXJ0T2Zmc2V0PSI1MCUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPkNSSUFUSVZJREFERSAmI3gwMEI3OyBRVUFMSURBREUgJiN4MDBCNzsgRklERUxJREFERTwvdGV4dFBhdGg+CiAgPC90ZXh0Pgo8L3N2Zz4K" alt="IIN"></div>
            <div>
                <h1>Monitoramento IIN</h1>
                <p>Dashboard em Tempo Real</p>
            </div>
        </div>
        <div class="header-actions">
            <button class="dark-toggle" onclick="document.body.classList.toggle('dark'); var m=document.getElementById('moonI'),s=document.getElementById('sunI'); if(document.body.classList.contains('dark')){{m.style.display='none';s.style.display='block';}}else{{m.style.display='block';s.style.display='none';}}"><span id="moonI"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0yMSAxMi43OUE5IDkgMCAxIDEgMTEuMjEgMyA3IDcgMCAwIDAgMjEgMTIuNzl6Ii8+PC9zdmc+Cg==" style="width:22px;height:22px"></span><span id="sunI" style="display:none"><img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIj48Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSI1Ii8+PGxpbmUgeDE9IjEyIiB5MT0iMSIgeDI9IjEyIiB5Mj0iMyIvPjxsaW5lIHgxPSIxMiIgeTE9IjIxIiB4Mj0iMTIiIHkyPSIyMyIvPjxsaW5lIHgxPSI0LjIyIiB5MT0iNC4yMiIgeDI9IjUuNjQiIHkyPSI1LjY0Ii8+PGxpbmUgeDE9IjE4LjM2IiB5MT0iMTguMzYiIHgyPSIxOS43OCIgeTI9IjE5Ljc4Ii8+PGxpbmUgeDE9IjEiIHkxPSIxMiIgeDI9IjMiIHkyPSIxMiIvPjxsaW5lIHgxPSIyMSIgeTE9IjEyIiB4Mj0iMjMiIHkyPSIxMiIvPjxsaW5lIHgxPSI0LjIyIiB5MT0iMTkuNzgiIHgyPSI1LjY0IiB5Mj0iMTguMzYiLz48bGluZSB4MT0iMTguMzYiIHkxPSI1LjY0IiB4Mj0iMTkuNzgiIHkyPSI0LjIyIi8+PC9zdmc+Cg==" style="width:22px;height:22px"></span></button>
            <a href="/" class="refresh-btn">Atualizar</a>
        </div>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="number">{total}</div>
            <div class="label">Total de Alertas</div>
        </div>
        <div class="stat-card green">
            <div class="number">{hoje}</div>
            <div class="label">Alertas (24h)</div>
        </div>
        <div class="stat-card orange">
            <div class="number">{canais_ativos}</div>
            <div class="label">Canais Ativos</div>
        </div>
        <div class="stat-card purple">
            <div class="number">{equipes_ativas}</div>
            <div class="label">Equipes Ativas</div>
        </div>
    </div>

    <div class="charts">
        <div class="chart-card">
            <h3>Alertas por Canal</h3>
            <canvas id="canalChart"></canvas>
        </div>
        <div class="chart-card">
            <h3>Atividade por Equipe</h3>
            <canvas id="equipeChart"></canvas>
        </div>
        <div class="chart-card">
            <h3>Alertas por Hora (24h)</h3>
            <canvas id="horaChart"></canvas>
        </div>
        <div class="chart-card">
            <h3>Alertas por Dia (7 dias)</h3>
            <canvas id="diaChart"></canvas>
        </div>
    </div>

    <div class="footer">
        Webhook ativo em /webhook (POST) | Dados atualizados ao recarregar
    </div>

    <script>
    var canalLabels = {canal_labels};
    var canalValues = {canal_values};
    var equipeLabels = {equipe_labels};
    var equipeValues = {equipe_values};
    var horaLabels = {hora_labels};
    var horaValues = {hora_values};
    var diaLabels = {dia_labels};
    var diaValues = {dia_values};
    var cores = ['#1a73e8','#ea580c','#0d9488','#7c3aed','#dc2626','#ca8a04','#2563eb','#059669','#d946ef','#64748b'];

    new Chart(document.getElementById('canalChart'), {{
        type: 'doughnut',
        data: {{ labels: canalLabels, datasets: [{{ data: canalValues, backgroundColor: cores }}] }},
        options: {{ responsive: true, plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }} }} }}
    }});

    new Chart(document.getElementById('equipeChart'), {{
        type: 'bar',
        data: {{ labels: equipeLabels, datasets: [{{ label: 'Alertas', data: equipeValues, backgroundColor: '#1a73e8' }}] }},
        options: {{ responsive: true, indexAxis: 'y', plugins: {{ legend: {{ display: false }} }} }}
    }});

    new Chart(document.getElementById('horaChart'), {{
        type: 'line',
        data: {{ labels: horaLabels, datasets: [{{ label: 'Alertas', data: horaValues, borderColor: '#0d9488', backgroundColor: 'rgba(13,148,136,0.1)', fill: true, tension: 0.3 }}] }},
        options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
    }});

    new Chart(document.getElementById('diaChart'), {{
        type: 'bar',
        data: {{ labels: diaLabels, datasets: [{{ label: 'Alertas', data: diaValues, backgroundColor: '#7c3aed' }}] }},
        options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
    }});
    </script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
