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


@app.route("/")
def redirect_to_dashboard():
    from flask import redirect
    return redirect("/static/index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
