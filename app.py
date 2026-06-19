import email

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
from werkzeug.utils import secure_filename
from supabase import create_client, Client
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message as MailMessage
from dotenv import load_dotenv
import time
import random 
import os

import secrets as _secrets

app = Flask(__name__)

app.permanent_session_lifetime = timedelta(minutes=30)

# 2FA email configuration (using environment variables for security)
load_dotenv()
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

def send_otp_email(receiver_email, otp):
    try:
        msg = MailMessage(
            subject="Your Secure Messaging OTP",
            recipients=[receiver_email]
        )

        msg.body = f"Your OTP is: {otp}"

        mail.send(msg)
        print("EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        print("EMAIL ERROR:", e)
def get_user_email(username):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT email FROM users WHERE username = ?",
        (username,)
    )

    row = cur.fetchone()
    conn.close()

    return row[0] if row else None

def generate_otp():
    return str(random.randint(100000, 999999))

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    # fallback ONLY for local dev (not file-based anymore)
    SECRET_KEY = _secrets.token_hex(24)

app.secret_key = SECRET_KEY

csrf = CSRFProtect(app)
# Use Postgres if DATABASE_URL is set, otherwise fallback to SQLite
db_url = os.environ.get("DATABASE_URL")
if db_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"

db = SQLAlchemy(app)

# Local dev → always use project folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))   # secure_chat/
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # ensure local folder exists

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.mp3', '.wav', '.pdf'}

# Supabase client (only used if USE_SUPABASE=true)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = None
if os.environ.get("USE_SUPABASE") == "true":
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- WebSocket setup ---
sock = Sock(app)

# Ensure DB schema exists and print engine
with app.app_context():
    print("[DEBUG] DB engine:", db.engine.url)
    init_db()

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
            return render_template('login.html', error="Invalid credentials")

        result = login_user(username, password)

        print("LOGIN RESULT:", result, type(result))

        if result == "success":
            otp = generate_otp()

            session.clear()  # IMPORTANT: prevent old session bug

            session['pending_user'] = username
            session['otp'] = otp
            session['otp_expiry'] = time.time() + 300

            print("OTP:", otp)
            print("EXPIRY:", session['otp_expiry'])
            print("USER:", session['pending_user'])

            # IMPORTANT: send email
            email = get_user_email(username)
            send_otp_email(email, otp)

            return redirect(url_for('verify_otp'))

    return render_template('login.html', error=result)
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    error = None

    otp = session.get('otp')
    expiry = session.get('otp_expiry')
    pending_user = session.get('pending_user')

    # DEBUG (TOP LEVEL)
    print("DEBUG OTP:", otp)
    print("DEBUG EXPIRY:", expiry)
    print("DEBUG USER:", pending_user)
    print("CURRENT TIME:", time.time())

    if otp is None or expiry is None or pending_user is None:
        print("SESSION MISSING DATA")
        return redirect(url_for('login'))

    if time.time() > float(expiry):
        print("OTP EXPIRED")
        session.clear()
        return "OTP expired. Please login again."

    if request.method == 'POST':
        user_otp = request.form.get('otp', '').strip()
        print("USER OTP:", user_otp)

        if user_otp == otp:
            print("OTP CORRECT")

            session['user'] = pending_user

            session.pop('otp', None)
            session.pop('otp_expiry', None)
            session.pop('pending_user', None)

            return redirect(url_for('dashboard'))

        error = "Invalid OTP"

    return render_template(
        'verify_otp.html',
        otp_expiry=expiry,
        error=error
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        result = register_user(username, email, password)

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
                    "type": "text",
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

            # # --- Handle file/image messages ---
            # elif msg.get("type") in ["file", "image"]:
            #     print(f"[DEBUG] Received {msg['type']} message from {username}: {msg}")

            #     if not receiver or not msg.get("url"):
            #         print(f"[DEBUG] Invalid {msg['type']} message from {username} — missing receiver or url")
            #         continue

            #     # Extract just the filename from the URL
            #     filename = os.path.basename(urlparse(msg["url"]).path)

            #     payload = json.dumps({
            #         "sender": username,
            #         "receiver": receiver,
            #         "type": msg["type"],
            #         "url": url_for("uploaded_file", filename=filename),  # full URL for frontend
            #         "timestamp": datetime.now().isoformat()
            #     })
            #     print(f"[DEBUG] Prepared payload for {msg['type']} message: {payload}")

            #     try:
            #         new_message = Message(
            #             sender=username,
            #             receiver=receiver,
            #             file_name=filename,   # only filename stored in DB
            #             msg_type=msg["type"],
            #             timestamp=datetime.utcnow()
            #         )
            #         db.session.add(new_message)
            #         db.session.commit()
            #         print(f"[DEBUG] Saved {msg['type']} message in DB for {username} -> {receiver}")
            #     except Exception as e:
            #         db.session.rollback()
            #         print(f"[DEBUG] Failed to save {msg['type']} message in DB: {e}")

            #     if receiver in connections:
            #         try:
            #             connections[receiver].send(payload)
            #             print(f"[DEBUG] Forwarded {msg['type']} message from {username} to {receiver}")
            #         except Exception as e:
            #             print(f"[DEBUG] Failed to forward {msg['type']} message to {receiver}: {e}")
            #     else:
            #         print(f"[DEBUG] Receiver {receiver} not connected, cannot forward {msg['type']} message")
            
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
                    "callType": msg.get("callType"),    # audio or video — must be forwarded
                    "sdp": msg.get("sdp"),
                    "candidate": msg.get("candidate"),
                    "status": msg.get("status"),
                    "duration": msg.get("duration"),
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

    if chat_user == session['user']:
        return jsonify({"error": "Forbidden"}), 403

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
    if username not in user_keys:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        user_keys[username] = private_key
    return user_keys[username].public_key()

@app.route("/conversation_key/<other_user>")
def conversation_key(other_user):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    import hashlib
    pair = sorted([session['user'], other_user])
    raw = app.secret_key + pair[0] + pair[1]
    key = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return jsonify({"key": key})

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
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json(force=True)

        # Validate required fields — sender is taken from session, not client
        for field in ("receiver", "ciphertext", "nonce"):
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing field: {field}"}), 400

        msg = Message(
            sender=session['user'],
            receiver=data["receiver"],
            ciphertext=data["ciphertext"],
            nonce=data["nonce"],
            timestamp=datetime.utcnow()
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

        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower() or ".dat"
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Unsupported file type"}), 400
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        unique_name = f"{session['user']}_{timestamp}{ext}"

        if os.environ.get("USE_SUPABASE") == "true":
            file_bytes = file.read()
            supabase.storage.from_("uploads").upload(unique_name, file_bytes)
            url = supabase.storage.from_("uploads").get_public_url(unique_name)
        else:
            filepath = os.path.join(UPLOAD_FOLDER, unique_name)
            file.save(filepath)
            url = url_for("uploaded_file", filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="file",
            timestamp=datetime.utcnow()
        )

        db.session.add(new_message)
        db.session.commit()
        print("[DEBUG] File message stored in DB")

        payload = json.dumps({
            "sender": session["user"],
            "receiver": receiver,
            "file_url": url,
            "msg_type": "file",
            "timestamp": datetime.utcnow().isoformat()
        })
        if receiver in connections:
            try:
                connections[receiver].send(payload)
            except Exception as e:
                print(f"[DEBUG] Failed to forward file message to {receiver}: {e}")

        return jsonify({"status": "success", "url": url}), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store file message:", e)
        import traceback; traceback.print_exc()
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
        if "image" not in request.files:
            print("[DEBUG] No image in request.files")
            return jsonify({"error": "Missing image"}), 400
    
        image = request.files["image"]
        receiver = request.form.get("receiver")
        print("[DEBUG] Receiver value:", receiver)
        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400
        
        filename = secure_filename(image.filename)
        ext = os.path.splitext(filename)[1].lower() or ".jpg"
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Unsupported file type"}), 400
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        unique_name = f"{session['user']}_{timestamp}{ext}"

        if os.environ.get("USE_SUPABASE") == "true":
            file_bytes = image.read()
            supabase.storage.from_("uploads").upload(unique_name, file_bytes)
            url = supabase.storage.from_("uploads").get_public_url(unique_name)
        else:
            filepath = os.path.join(UPLOAD_FOLDER, unique_name)
            image.save(filepath)
            url = url_for("uploaded_file", filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="image",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()

        return jsonify({"status": "success", "url": url}), 201

    except Exception as e:
        db.session.rollback()
        import traceback; traceback.print_exc()
        print("[DEBUG] Failed to store image message:", e)
        return jsonify({"error": "Failed to store image"}), 500

# --- New route for audio uploads ---
@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    print("[DEBUG] /upload_audio route called")
    print("[DEBUG] request.form:", request.form)
    print("[DEBUG] request.files:", request.files)

    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 403

    try:
        audio = request.files.get("audio")
        receiver = request.form.get("receiver")
        print("[DEBUG] Receiver value:", receiver)

        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400
        if not audio:
            print("[DEBUG] No audio in request.files")
            return jsonify({"error": "Missing audio"}), 400
        
        ext = os.path.splitext(secure_filename(audio.filename))[1].lower() or ".webm"
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": "Unsupported file type"}), 400
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        unique_name = f"{session['user']}_{timestamp}{ext}"

        if os.environ.get("USE_SUPABASE") == "true":
            file_bytes = audio.read()
            supabase.storage.from_("uploads").upload(unique_name, file_bytes)
            url = supabase.storage.from_("uploads").get_public_url(unique_name)
        else:
            filepath = os.path.join(UPLOAD_FOLDER, unique_name)
            audio.save(filepath)
            url = url_for("uploaded_file", filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="audio",
            timestamp=datetime.utcnow()
        )

        db.session.add(new_message)
        db.session.commit()
        print("[DEBUG] Audio message stored in DB")

        # Optional: broadcast to receiver only
        payload = json.dumps({
            "sender": session["user"],
            "receiver": receiver,
            "url": url,
            "msg_type": "audio",
            "timestamp": datetime.utcnow().isoformat()
        })
        if receiver in connections:
            try:
                connections[receiver].send(payload)
            except Exception as e:
                print(f"[DEBUG] Failed to forward audio message to {receiver}: {e}")

        return jsonify({"status": "success", "url": url}), 201

    except Exception as e:
        db.session.rollback()
        import traceback; traceback.print_exc()
        print("[DEBUG] Failed to store audio message:", e)
        return jsonify({"error": "Failed to store audio"}), 500

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    msg = Message.query.filter_by(file_name=filename).first()
    if not msg or session['user'] not in (msg.sender, msg.receiver):
        return jsonify({"error": "Forbidden"}), 403

    if os.environ.get("USE_SUPABASE") == "true":
        url = supabase.storage.from_("uploads").get_public_url(filename)
        return redirect(url)
    else:
        resp = send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)
        resp.headers['Content-Security-Policy'] = "default-src 'none'"
        return resp

# Temporary debug route
@app.route("/debug-messages")
def debug_messages():
    if not app.debug:
        return jsonify({"error": "Not found"}), 404
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