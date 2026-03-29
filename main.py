from flask import Flask, request
import json
import os
import threading
import time
import psycopg2

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


# ── Webhook endpoint ──────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    with open("fila.txt", "a") as f:
        f.write(json.dumps(data) + "\n")
    return "ok", 200


@app.route("/", methods=["GET"])
def home():
    return "Webhook SASI ativo", 200


# ── Worker (thread) ───────────────────────────────────
def processar_fila():
    while True:
        try:
            if not os.path.exists("fila.txt"):
                time.sleep(2)
                continue

            with open("fila.txt", "r") as f:
                linhas = f.readlines()

            if not linhas:
                time.sleep(2)
                continue

            # limpa o arquivo
            open("fila.txt", "w").close()

            conn = psycopg2.connect(DATABASE_URL)
            for linha in linhas:
                data = json.loads(linha)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO registros (canal, mensagem) VALUES (%s, %s)",
                    (data.get("canal"), data.get("mensagem"))
                )
                conn.commit()
                cur.close()
            conn.close()

        except Exception as e:
            print(f"[worker] erro: {e}")

        time.sleep(2)


# ── Iniciar worker em background ──────────────────────
worker_thread = threading.Thread(target=processar_fila, daemon=True)
worker_thread.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
