from flask import Flask, make_response, render_template, request, redirect, session, jsonify, url_for
# for real time communication
from flask_sock import Sock
import json

from modules.database import init_db, get_db
from modules.auth import register_user, login_user
from modules.database import get_all_users, save_message, get_chat_history

# for cryptography algo
from flask_sqlalchemy import SQLAlchemy
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import os, base64
from datetime import datetime
import os, eventlet, eventlet.wsgi

app = Flask(__name__)
app.secret_key = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
db = SQLAlchemy(app)

sock = Sock(app)

init_db()

@app.route('/')
def home():
    print("[DEBUG] home() called")
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
            error = "Invalid credentials"
            return render_template('login.html', error=error)

        result = login_user(username, password)
        print("LOGIN RESULT:", result, type(result))

        if result == "success":
            session['user'] = username
            print("SESSION SET:", session.get('user'))
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


@app.route('/dashboard')
def dashboard():
    print("[DEBUG] dashboard() called")
    if 'user' not in session:
        print("[DEBUG] no user in session")
        # Replace redirect() with manual response
        resp = make_response("", 302)
        resp.headers["Location"] = url_for('login')
        return resp

    chat_user = request.args.get('chat_user')
    users = get_all_users()
    valid_users = [u[0] for u in users]

    if chat_user and chat_user not in valid_users:
        print("[DEBUG] invalid chat_user")
        # Replace jsonify() with manual JSON response
        error_payload = json.dumps({"error": "Invalid user"})
        resp = make_response(error_payload, 403)
        resp.headers["Content-Type"] = "application/json"
        return resp

    return render_template(
        'dashboard.html',
        username=session['user'],
        users=users,
        chat_user=chat_user
    )

# --- WEBSOCKET EVENTS (Flask-Sock) ---
connections = {}

@sock.route("/ws")
def websocket(ws):
    username = None
    try:
        print("[DEBUG] WebSocket route entered — handshake accepted")

        # First message from client must be the username string
        username = ws.receive()
        if not username:
            print("[DEBUG] No username received, closing connection")
            return

        # Register connection
        connections[username] = ws
        print(f">>> {username} connected")

        # Main receive/send loop
        while True:
            data = ws.receive()
            if data is None:
                print(f"[DEBUG] Connection closed by {username}")
                break

            try:
                msg = json.loads(data)
            except Exception as e:
                print(f"[DEBUG] Failed to parse message from {username}: {e}")
                continue

            receiver = msg.get("receiver")
            ciphertext = msg.get("ciphertext")
            nonce = msg.get("nonce")

            if not receiver or not ciphertext or not nonce:
                print(f"[DEBUG] Invalid message format from {username}")
                continue

            payload = json.dumps({
                "sender": username,
                "receiver": receiver,
                "ciphertext": ciphertext,
                "nonce": nonce,
                "timestamp": datetime.now().isoformat()
            })
            # --- Save to database ---
            try:
                save_message(username, receiver, ciphertext, nonce)
                print(f"[DEBUG] Saved message from {username} to {receiver}")
            except Exception as e:
                print(f"[DEBUG] Failed to save message: {e}")
        
            # Forward to receiver if connected
            if receiver in connections:
                try:
                    connections[receiver].send(payload)
                    print(f"[DEBUG] Forwarded message from {username} to {receiver}")
                except Exception as e:
                    print(f"[DEBUG] Failed to send to {receiver}: {e}")

            # Echo back to sender (optional, for confirmation)
            try:
                # ws.send(payload)
                print(f"[DEBUG] Echoed message back to {username}")
            except Exception as e:
                print(f"[DEBUG] Failed to echo back to {username}: {e}")

    finally:
        if username and username in connections:
            del connections[username]
            print(f">>> {username} disconnected")

@app.route('/messages/<chat_user>')
def messages(chat_user):
    if 'user' not in session:
        resp = make_response("", 302)
        resp.headers["Location"] = url_for('login')
        return resp

    history = get_chat_history(session['user'], chat_user)
    formatted = []
    for row in history:
        formatted.append({
            "sender": row[0],
            "receiver": row[1],
            "ciphertext": row[2],
            "nonce": row[3],
            "timestamp": row[4].isoformat() if isinstance(row[4], datetime) else row[4]
        })

    payload = json.dumps(formatted)
    resp = make_response(payload, 200)
    resp.headers["Content-Type"] = "application/json"
    return resp



class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    receiver = db.Column(db.String(50))
    ciphertext = db.Column(db.Text)
    nonce = db.Column(db.Text)
    timestamp = db.Column(db.DateTime)

# --- RSA key generation per user ---
user_keys = {}

def generate_rsa_keypair(username):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    user_keys[username] = private_key
    return public_key

@app.route("/public_key/<username>")
def get_public_key(username):
    pub = generate_rsa_keypair(username)
    pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem.decode()

@app.route("/send", methods=["POST"])
def send_message():
    try:
        data = request.get_json(force=True)

        # Validate required fields
        required = ["sender", "receiver", "ciphertext", "nonce"]
        for field in required:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing field: {field}"}), 400

        msg = Message(
            sender=data["sender"],
            receiver=data["receiver"],
            ciphertext=data["ciphertext"],
            nonce=data["nonce"],
            timestamp=datetime.utcnow()  # ensure timestamp is set
        )
        db.session.add(msg)
        db.session.commit()

        return jsonify({"status": "stored"}), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store message:", e)
        return jsonify({"error": "Failed to store message"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))
#     eventlet.wsgi.server(eventlet.listen(("0.0.0.0", port)), app)

# # Add this at the very bottom:
# from asgiref.wsgi import WsgiToAsgi

# # Expose an ASGI-compatible app for Hypercorn
# asgi_app = WsgiToAsgi(app)