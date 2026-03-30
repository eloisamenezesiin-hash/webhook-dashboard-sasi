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
        cur.execute(
            """INSERT INTO registros (canal, mensagem, equipe, site_nome, tipo, prioridade, lat, lng)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (canal, mensagem, equipe, site_nome, tipo, prioridade, lat, lng)
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
        cur.execute("""SELECT EXTRACT(HOUR FROM data) as hora, COUNT(*) as total
                       FROM registros WHERE data >= NOW() - INTERVAL '24 hours'
                       GROUP BY hora ORDER BY hora""")
        por_hora = cur.fetchall()
        # Alertas por dia (ultimos 7 dias)
        cur.execute("""SELECT data::date as dia, COUNT(*) as total
                       FROM registros WHERE data >= NOW() - INTERVAL '7 days'
                       GROUP BY dia ORDER BY dia""")
        por_dia = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        total = hoje = canais_ativos = equipes_ativas = 0
        por_canal = por_equipe = por_hora = por_dia = []

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
            .header-logo svg {{ height: 90px; width: auto; }}
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
        @media (max-width: 768px) {{
            .charts {{ grid-template-columns: 1fr; }}
            .stats {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="header">
            <div class="header-left">
                <div class="header-logo"><svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 220'><defs><path id='tA' d='M 60,125 Q 200,15 340,125' fill='none'/><path id='bA' d='M 70,162 Q 200,242 330,162' fill='none'/></defs><text font-family='Georgia,serif' font-size='15' fill='rgba(255,255,255,0.9)' font-weight='bold' letter-spacing='3'><textPath href='#tA' startOffset='50%' text-anchor='middle'>THE IIN GROUP OF COMPANIES</textPath></text><path d='M 90,112 Q 200,65 310,112' stroke='rgba(255,255,255,0.5)' stroke-width='1.5' fill='none'/><g transform='translate(162,82)'><rect x='0' y='0' width='7' height='55' rx='2' fill='white'/><rect x='20' y='0' width='7' height='55' rx='2' fill='white'/><rect x='44' y='0' width='7' height='55' rx='2' fill='white'/><rect x='60' y='0' width='7' height='55' rx='2' fill='white'/><rect x='80' y='0' width='7' height='55' rx='2' fill='white'/><polygon points='44,0 51,0 83,55 76,55' fill='white'/></g><text font-family='Georgia,serif' font-size='11' fill='rgba(255,255,255,0.8)' letter-spacing='2'><textPath href='#bA' startOffset='50%' text-anchor='middle'>CRIATIVIDADE \u00b7 QUALIDADE \u00b7 FIDELIDADE</textPath></text></svg></div>
                <div>
                    <h1>Monitoramento IIN</h1>
                    <p>Dashboard em Tempo Real</p>
                </div>
            </div>
            <div class="header-actions">
                <button class="dark-toggle" onclick="document.body.classList.toggle('dark'); var m=document.getElementById('moonI'),s=document.getElementById('sunI'); if(document.body.classList.contains('dark')){{m.style.display='none';s.style.display='block';}}else{{m.style.display='block';s.style.display='none';}}"><span id='moonI'><svg viewBox='0 0 24 24' fill='white' stroke='none'><path d='M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z'/></svg></span><span id='sunI' style='display:none'><svg viewBox='0 0 24 24' fill='white' stroke='white' stroke-width='2' stroke-linecap='round'><circle cx='12' cy='12' r='5'/><line x1='12' y1='1' x2='12' y2='3'/><line x1='12' y1='21' x2='12' y2='23'/><line x1='4.22' y1='4.22' x2='5.64' y2='5.64'/><line x1='18.36' y1='18.36' x2='19.78' y2='19.78'/><line x1='1' y1='12' x2='3' y2='12'/><line x1='21' y1='12' x2='23' y2='12'/><line x1='4.22' y1='19.78' x2='5.64' y2='18.36'/><line x1='18.36' y1='5.64' x2='19.78' y2='4.22'/></svg></span></button>
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
