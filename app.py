from flask import Flask, request
import json

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    # salva em fila (arquivo simples)
    with open("fila.txt", "a") as f:
        f.write(json.dumps(data) + "\n")
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
