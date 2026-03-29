import psycopg2
import json
import time
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "SUA_CONNECTION_STRING")
conn = psycopg2.connect(DATABASE_URL)


def processar_fila():
    try:
        with open("fila.txt", "r") as f:
            linhas = f.readlines()
        open("fila.txt", "w").close()
        for linha in linhas:
            data = json.loads(linha)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO registros (canal, mensagem) VALUES (%s, %s)",
                (data.get("canal"), data.get("mensagem"))
            )
            conn.commit()
    except Exception:
        pass


while True:
    processar_fila()
    time.sleep(2)
