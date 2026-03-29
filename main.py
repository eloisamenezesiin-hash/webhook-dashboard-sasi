from flask import Flask, request, jsonify
import json
import os
import psycopg2

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    return psycopg2.connect(DATABASE_URL)


# ── Webhook endpoint ──────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO registros (canal, mensagem) VALUES (%s, %s)",
            (data.get("canal"), data.get("mensagem"))
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "destino": "banco"}), 200
    except Exception as e:
        # fallback: salva em fila local se o banco falhar
        with open("fila.txt", "a") as f:
            f.write(json.dumps(data) + "\n")
        return jsonify({"status": "ok", "destino": "fila", "erro": str(e)}), 200


@app.route("/", methods=["GET"])
def home():
    return "Webhook SASI ativo", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
