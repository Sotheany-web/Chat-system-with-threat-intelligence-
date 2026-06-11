from flask import Flask, make_response, render_template, request, session, jsonify, url_for
from flask_sock import Sock
import json
import hashlib
import hmac
import os
import eventlet
import eventlet.wsgi
from datetime import datetime

from modules.database import (
    init_db, get_db,
    save_message, get_chat_history,
    get_friends, get_pending_requests, search_users,
    send_connection_request, accept_connection, reject_connection
)
from modules.auth import register_user, login_user

app = Flask(__name__)
app.secret_key = "secret123"

sock = Sock(app)

init_db()

# ── Auth routes ────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    resp = make_response("", 302)
    resp.headers["Location"] = url_for('login')
    return resp

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template('login.html', error="Invalid credentials")

        result = login_user(username, password)

        if result == "success":
            session['user'] = username
            resp = make_response("", 302)
            resp.headers["Location"] = url_for('dashboard')
            return resp
        else:
            return render_template('login.html', error=result)

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        result = register_user(username, password)
        if result == "success":
            resp = make_response("", 302)
            resp.headers["Location"] = url_for('login')
            return resp
        error = result
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    resp = make_response("", 302)
    resp.headers["Location"] = url_for('login')
    return resp

# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        resp = make_response("", 302)
        resp.headers["Location"] = url_for('login')
        return resp

    chat_user   = request.args.get('chat_user')
    friends     = get_friends(session['user'])          # only connected users
    pending     = get_pending_requests(session['user']) # incoming requests

    # Validate chat_user is an actual friend
    friend_names = [f[0] for f in friends]
    if chat_user and chat_user not in friend_names:
        chat_user = None

    return render_template(
        'dashboard.html',
        username      = session['user'],
        users         = friends,
        chat_user     = chat_user,
        pending_count = len(pending)
    )

# ── Connection / friend-request API ───────────────────────────────────────────

@app.route('/api/search_users')
def api_search_users():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = search_users(q, session['user'])
    return jsonify([r[0] for r in results])

@app.route('/api/send_request/<receiver>', methods=['POST'])
def api_send_request(receiver):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    result = send_connection_request(session['user'], receiver)
    if result == "success":
        return jsonify({"status": "sent"})
    return jsonify({"error": "Request already exists"}), 400

@app.route('/api/accept_request/<sender>', methods=['POST'])
def api_accept_request(sender):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    accept_connection(sender, session['user'])
    return jsonify({"status": "accepted"})

@app.route('/api/reject_request/<sender>', methods=['POST'])
def api_reject_request(sender):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    reject_connection(sender, session['user'])
    return jsonify({"status": "rejected"})

@app.route('/api/pending_requests')
def api_pending_requests():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    reqs = get_pending_requests(session['user'])
    return jsonify([{"sender": r[0], "created_at": str(r[1])} for r in reqs])

# ── WebSocket ──────────────────────────────────────────────────────────────────

connections = {}

@sock.route("/ws")
def websocket(ws):
    username = None
    try:
        username = ws.receive()
        if not username:
            return

        connections[username] = ws
        print(f">>> {username} connected")

        while True:
            data = ws.receive()
            if data is None:
                break

            try:
                msg = json.loads(data)
            except Exception as e:
                print(f"[DEBUG] Bad message from {username}: {e}")
                continue

            receiver  = msg.get("receiver")
            ciphertext = msg.get("ciphertext")
            nonce     = msg.get("nonce")

            if not receiver or not ciphertext or not nonce:
                continue

            payload = json.dumps({
                "sender"    : username,
                "receiver"  : receiver,
                "ciphertext": ciphertext,
                "nonce"     : nonce,
                "timestamp" : datetime.now().isoformat()
            })

            try:
                save_message(username, receiver, ciphertext, nonce)
            except Exception as e:
                print(f"[DEBUG] Failed to save message: {e}")

            if receiver in connections:
                try:
                    connections[receiver].send(payload)
                except Exception as e:
                    print(f"[DEBUG] Failed to forward to {receiver}: {e}")

    finally:
        if username and username in connections:
            del connections[username]
            print(f">>> {username} disconnected")

# ── Message history ────────────────────────────────────────────────────────────

@app.route('/messages/<chat_user>')
def messages(chat_user):
    if 'user' not in session:
        resp = make_response("", 302)
        resp.headers["Location"] = url_for('login')
        return resp

    history   = get_chat_history(session['user'], chat_user)
    formatted = []
    for row in history:
        formatted.append({
            "sender"    : row[0],
            "receiver"  : row[1],
            "ciphertext": row[2],
            "nonce"     : row[3],
            "timestamp" : row[4].isoformat() if isinstance(row[4], datetime) else row[4]
        })

    resp = make_response(json.dumps(formatted), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp

# ── Encryption key ─────────────────────────────────────────────────────────────

@app.route("/conversation_key/<other_user>")
def conversation_key(other_user):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    participants = sorted([session['user'], other_user])
    key_input    = f"{participants[0]}:{participants[1]}".encode()
    derived      = hmac.new(app.secret_key.encode(), key_input, hashlib.sha256).digest()
    return jsonify({"key": derived[:16].hex()})

# ── Send via HTTP (fallback) ───────────────────────────────────────────────────

@app.route("/send", methods=["POST"])
def send_message():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data     = request.get_json(force=True)
        required = ["receiver", "ciphertext", "nonce"]
        for field in required:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing field: {field}"}), 400

        save_message(session['user'], data["receiver"], data["ciphertext"], data["nonce"])
        return jsonify({"status": "stored"}), 201

    except Exception as e:
        print("[DEBUG] Failed to store message:", e)
        return jsonify({"error": "Failed to store message"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
