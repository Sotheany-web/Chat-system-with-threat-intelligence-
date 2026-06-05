from flask import Flask, make_response, render_template, request, redirect, session, jsonify, url_for
# for real time communication
from flask_sock import Sock
import json

from modules.database import init_db, get_db
# from secure_chat.modules.database import init_db, get_db
from modules.auth import register_user, login_user
from modules.database import get_all_users, save_message, get_chat_history

# for cryptography algo
from flask_sqlalchemy import SQLAlchemy
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from datetime import datetime
from flask import send_from_directory
from urllib.parse import urlparse
import os


app = Flask(__name__)
app.secret_key = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
db = SQLAlchemy(app)

# --- Uploads ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))   # secure_chat/
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")       # secure_chat/uploads
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- WebSocket setup ---
sock = Sock(app)

init_db()  # Ensure DB is initialized on startup

connections = {}

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
# connections = {}

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

            # --- Handle encrypted text messages ---
            if "ciphertext" in msg and "nonce" in msg:
                ciphertext = msg.get("ciphertext")
                nonce = msg.get("nonce")

                if not receiver or not ciphertext or not nonce:
                    print(f"[DEBUG] Invalid text message from {username}")
                    continue

                payload = json.dumps({
                    "sender": username,
                    "receiver": receiver,
                    "ciphertext": ciphertext,
                    "nonce": nonce,
                    "timestamp": datetime.now().isoformat()
                })

                # Save to DB
                try:
                    save_message(username, receiver, ciphertext, nonce)
                    print(f"[DEBUG] Saved text message from {username} to {receiver}")
                except Exception as e:
                    print(f"[DEBUG] Failed to save text message: {e}")

                # Forward to receiver
                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(f"[DEBUG] Forwarded text message from {username} to {receiver}")
                    except Exception as e:
                        print(f"[DEBUG] Failed to send text message to {receiver}: {e}")

            # --- Handle file/image messages ---
            elif msg.get("type") in ["file", "image"]:
                print(f"[DEBUG] Received {msg['type']} message from {username}: {msg}")

                if not receiver or not msg.get("url"):
                    print(f"[DEBUG] Invalid {msg['type']} message from {username} — missing receiver or url")
                    continue

                # Extract just the filename from the URL
                filename = os.path.basename(urlparse(msg["url"]).path)

                payload = json.dumps({
                    "sender": username,
                    "receiver": receiver,
                    "type": msg["type"],
                    "url": url_for("uploaded_file", filename=filename),  # full URL for frontend
                    "timestamp": datetime.now().isoformat()
                })
                print(f"[DEBUG] Prepared payload for {msg['type']} message: {payload}")

                try:
                    new_message = Message(
                        sender=username,
                        receiver=receiver,
                        file_name=filename,   # only filename stored in DB
                        msg_type=msg["type"],
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_message)
                    db.session.commit()
                    print(f"[DEBUG] Saved {msg['type']} message in DB for {username} -> {receiver}")
                except Exception as e:
                    db.session.rollback()
                    print(f"[DEBUG] Failed to save {msg['type']} message in DB: {e}")

                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(f"[DEBUG] Forwarded {msg['type']} message from {username} to {receiver}")
                    except Exception as e:
                        print(f"[DEBUG] Failed to forward {msg['type']} message to {receiver}: {e}")
                else:
                    print(f"[DEBUG] Receiver {receiver} not connected, cannot forward {msg['type']} message")
            
            # --- Handle call signaling ---
            elif msg.get("type") in ["call-offer", "call-answer", "ice-candidate", "call-end", "call-missed"]:
                print(f"[DEBUG] Received {msg['type']} from {username}: {msg}")

                if not receiver:
                    print(f"[DEBUG] Invalid {msg['type']} message from {username} — missing receiver")
                    continue

                payload = json.dumps({
                    "sender": username,
                    "receiver": receiver,
                    "type": msg["type"],
                    "sdp": msg.get("sdp"),              # for offer/answer
                    "candidate": msg.get("candidate"),  # for ICE
                    "status": msg.get("status"),        # for call-end/missed
                    "duration": msg.get("duration"),    # optional duration
                    "timestamp": datetime.now().isoformat()
                })

                # Save call log in DB for call-end/missed
                if msg["type"] in ["call-end", "call-missed"]:
                    try:
                        new_message = Message(
                            sender=username,
                            receiver=receiver,
                            msg_type="call",
                            status=msg.get("status"),       # "ended" or "missed"
                            duration=msg.get("duration"),   # seconds if ended
                            timestamp=datetime.utcnow()
                        )

                        db.session.add(new_message)
                        db.session.commit()
                        print(f"[DEBUG] Saved call log in DB for {username} -> {receiver}")
                    except Exception as e:
                        db.session.rollback()
                        print(f"[DEBUG] Failed to save call log: {e}")

                # Forward signaling payload
                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(f"[DEBUG] Forwarded {msg['type']} from {username} to {receiver}")
                    except Exception as e:
                        print(f"[DEBUG] Failed to forward {msg['type']} to {receiver}: {e}")
                else:
                    print(f"[DEBUG] Receiver {receiver} not connected, cannot forward {msg['type']}")


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
        entry = {
            "sender": row[0],
            "receiver": row[1],
            "ciphertext": row[2],
            "nonce": row[3],
            "file_name": row[4],
            "msg_type": row[5],
            "url": url_for("uploaded_file", filename=row[4]) 
                if row[5] in ("file","image") and row[4] else None,
            "timestamp": row[6].isoformat() if isinstance(row[6], datetime) else row[6]
        }

        # Add extra fields for call logs
        if row[5] == "call":
            entry["status"] = row[7] if len(row) > 7 else None   # e.g. "ended", "missed"
            entry["duration"] = row[8] if len(row) > 8 else None # seconds or formatted string

        formatted.append(entry)

    payload = json.dumps(formatted)
    resp = make_response(payload, 200)
    resp.headers["Content-Type"] = "application/json"
    return resp

# ---------------- MODELS ----------------
class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender = db.Column(db.String, nullable=False)
    receiver = db.Column(db.String, nullable=False)

    # For text
    ciphertext = db.Column(db.Text)
    nonce = db.Column(db.Text)

    # For file/image/audio
    file_name = db.Column(db.Text)

    # Message type: "text", "file", "image", "audio", "call"
    msg_type = db.Column(db.String)

    # For calls
    status = db.Column(db.String)     # "ended", "missed", "declined"
    duration = db.Column(db.Integer)  # seconds

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

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

# ---------------- UPLOAD ROUTES ----------------
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

@app.route("/upload_file", methods=["POST"])
def upload_file():
    print("[DEBUG] /upload_file route called")
    print("[DEBUG] request.form:", request.form)
    print("[DEBUG] request.files:", request.files)

    if "user" not in session:
        print("[DEBUG] Not logged in")
        return jsonify({"error": "Not logged in"}), 403

    if "file" not in request.files:
        print("[DEBUG] No file in request.files")
        return jsonify({"error": "Missing file"}), 400
    
    try:
        file = request.files["file"]
        receiver = request.form.get("receiver")
        print("[DEBUG] Receiver value:", receiver)

        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400
        if "file" not in request.files:
            print("[DEBUG] No file in request.files")
            return jsonify({"error": "Missing file"}), 400

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        print("[DEBUG] File saved at:", filepath)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=file.filename,
            msg_type="file",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()
        print("[DEBUG] File message stored in DB")

        payload = json.dumps({
            "sender": session["user"],
            "receiver": receiver,
            "file_url": url_for("uploaded_file", filename=file.filename),
            "msg_type": "file",
            "timestamp": datetime.utcnow().isoformat()
        })
        if receiver in connections:
            connections[receiver].send(payload)

        return jsonify({
            "status": "success",
            "url": url_for("uploaded_file", filename=file.filename)
        }), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store file message:", e)
        return jsonify({"error": "Failed to store file"}), 500

@app.route("/upload_image", methods=["POST"])
def upload_image():
    print("[DEBUG] /upload_image route called")
    print("[DEBUG] request.form:", request.form)
    print("[DEBUG] request.files:", request.files)
    print("[DEBUG] DB path:", db.engine.url)

    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 403

    try:
        image = request.files["image"]
        receiver = request.form.get("receiver")
        print("[DEBUG] Receiver value:", receiver)
        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400
        if "image" not in request.files:
            print("[DEBUG] No image in request.files")
            return jsonify({"error": "Missing image"}), 400

        filepath = os.path.join(UPLOAD_FOLDER, image.filename)
        image.save(filepath)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=image.filename,
            msg_type="image",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()

        return jsonify({
            "status": "success",
            "url": url_for("uploaded_file", filename=image.filename)
        }), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store image message:", e)
        return jsonify({"error": "Failed to store image"}), 500
    
@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    print("[DEBUG] /upload_audio route called")
    print("[DEBUG] request.form:", request.form)
    print("[DEBUG] request.files:", request.files)

    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 403

    try:
        # Get audio file and receiver
        audio = request.files.get("audio")
        receiver = request.form.get("receiver")
        print("[DEBUG] Receiver value:", receiver)

        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400
        if not audio:
            print("[DEBUG] No audio in request.files")
            return jsonify({"error": "Missing audio"}), 400
        
        # Generate simple unique filename: user + timestamp
        ext = os.path.splitext(audio.filename)[1] or ".webm"
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique_name = f"{session['user']}_{timestamp}{ext}"

        # Save audio file
        filepath = os.path.join(UPLOAD_FOLDER, unique_name)
        audio.save(filepath)

        # Store metadata in DB
        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="audio",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()

        return jsonify({
            "status": "success",
            "url": url_for("uploaded_file", filename=unique_name)
        }), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store audio message:", e)
        return jsonify({"error": "Failed to store audio"}), 500

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False) # allow inline viewing

# Temporary debug route
@app.route("/debug-messages")
def debug_messages():
    conn = get_db()
    cur = conn.cursor()
    # Select all columns from the messages table
    cur.execute("SELECT * FROM messages ORDER BY timestamp DESC")
    rows = cur.fetchall()
    conn.close()

    # Convert rows into a list of dicts for readability
    messages = []
    for row in rows:
        messages.append({
            "id": row[0],
            "sender": row[1],
            "receiver": row[2],
            "ciphertext": row[3],
            "nonce": row[4],
            "file_name": row[5],
            "msg_type": row[6],
            "status": row[7],
            "duration": row[8],
            "timestamp": row[9]
        })

    return {"messages": messages}

# ---------------- STARTUP ----------------
if __name__ == "__main__":
   
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT
    app.run(host="0.0.0.0", port=port, debug=True)
# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))
#     eventlet.wsgi.server(eventlet.listen(("0.0.0.0", port)), app)

# # Add this at the very bottom:
# from asgiref.wsgi import WsgiToAsgi

# # Expose an ASGI-compatible app for Hypercorn
# asgi_app = WsgiToAsgi(app)