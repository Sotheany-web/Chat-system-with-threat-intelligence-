# backend/app.py
from flask import Flask, jsonify
from flask_sock import Sock  # for WebSocket support

app = Flask(__name__)
sock = Sock(app)

# Simple REST route
@app.route("/")
def home():
    return jsonify({"message": "Chat server is running with Flask!"})

# Example REST route for messages
@app.route("/messages")
def get_messages():
    return jsonify([
        {"sender": "Alice", "content": "Hello!"},
        {"sender": "Bob", "content": "Hi!"}
    ])

# WebSocket route for real-time chat
@sock.route("/ws")
def websocket(ws):
    while True:
        data = ws.receive()
        ws.send(f"Message received: {data}")
