from flask import Flask, request, jsonify
import json
import os
import psycopg2

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    raw = json.dumps(data) if data else request.get_data(as_text=True)
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO registros (canal, mensagem) VALUES (%s, %s)",
            (data.get("canal") if data else None, data.get("mensagem") if data else None)
        )
        cur.execute(
            "INSERT INTO webhook_logs (raw_json) VALUES (%s)",
            (raw,)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "destino": "banco"}), 200
    except Exception as e:
        with open("fila.txt", "a") as f:
            f.write((raw or json.dumps(data)) + "\n")
        return jsonify({"status": "ok", "destino": "fila", "erro": str(e)}), 200
@app.route("/", methods=["GET"])
def home():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, canal, mensagem, data FROM registros ORDER BY data DESC LIMIT 100")
        registros = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM registros")
        total = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as e:
        registros = []
        total = 0

    linhas = ""
    for r in registros:
        data_fmt = r[3].strftime("%d/%m/%Y %H:%M") if r[3] else ""
        linhas += f"""
            <tr>
                <td>{r[0]}</td>
                <td><span class="badge">{r[1] or ''}</span></td>
                <td>{r[2] or ''}</td>
                <td>{data_fmt}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitoramento SASI - IIN</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 25px 30px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(26, 115, 232, 0.3); }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .header p {{ opacity: 0.85; font-size: 14px; }}
        .stats {{ display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }}
        .stat-card {{ background: white; padding: 20px 25px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); flex: 1; min-width: 150px; }}
        .stat-card .number {{ font-size: 32px; font-weight: bold; color: #1a73e8; }}
        .stat-card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
        .table-container {{ background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
        .table-header {{ padding: 18px 25px; border-bottom: 1px solid #e8eaed; display: flex; justify-content: space-between; align-items: center; }}
        .table-header h2 {{ font-size: 18px; color: #333; }}
        .refresh-btn {{ background: #1a73e8; color: white; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }}
        .refresh-btn:hover {{ background: #1557b0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f8f9fa; padding: 12px 20px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; }}
        td {{ padding: 12px 20px; border-top: 1px solid #f0f0f0; font-size: 14px; }}
        tr:hover {{ background: #f8f9ff; }}
        .badge {{ background: #e8f0fe; color: #1a73e8; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }}
        .empty {{ text-align: center; padding: 50px; color: #999; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Monitoramento SASI</h1>
        <p>Instituto Insular de Niteroi - Webhook Dashboard</p>
    </div>
    <div class="stats">
        <div class="stat-card">
            <div class="number">{total}</div>
            <div class="label">Total de Registros</div>
        </div>
    </div>
    <div class="table-container">
        <div class="table-header">
            <h2>Ultimos Registros</h2>
            <a href="/" class="refresh-btn">Atualizar</a>
        </div>
        {'<table><thead><tr><th>ID</th><th>Canal</th><th>Mensagem</th><th>Data</th></tr></thead><tbody>' + linhas + '</tbody></table>' if registros else '<div class="empty">Nenhum registro ainda. Aguardando dados do SASI...</div>'}
    </div>
    <div class="footer">
        Webhook ativo em /webhook (POST)
    </div>
</body>
</html>"""
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
