from flask import Flask, jsonify, render_template
from flask_sock import Sock
import os

# Point Flask to the project root for templates and assets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

app = Flask(
    __name__,
    template_folder=PARENT_DIR,                     # index.html lives here
    static_folder=os.path.join(PARENT_DIR, "assets") # assets folder
)
sock = Sock(app)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/messages")
def get_messages():
    return jsonify([
        {"sender": "Alice", "content": "Hello!"},
        {"sender": "Bob", "content": "Hi!"}
    ])

@sock.route("/ws")
def websocket(ws):
    while True:
        data = ws.receive()
        ws.send(f"Message received: {data}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
