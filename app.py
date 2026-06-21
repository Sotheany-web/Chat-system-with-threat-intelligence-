from flask import Flask, make_response, render_template, request, redirect, session, jsonify, url_for
# for real time communication
from flask_sock import Sock
import json

from modules.database import init_db, get_db
# from secure_chat.modules.database import init_db, get_db
from modules.auth import register_user, login_user
from modules.database import get_all_users, save_message, save_file_message, get_chat_history

from modules.ai_intelligence import predict_threat

from modules.database import (
    save_threat_log,
    get_security_logs,
    create_admin_alert,
    get_admin_alerts
)

from modules.threat_detection import (
    check_message_rate,
    check_sql_injection,
    check_sql_payload_for_chat,
    check_file_upload,
    record_event_for_intelligence,
    should_block,
    public_message,
    final_security_decision
)

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
import os

from datetime import datetime
import secrets as _secrets

app = Flask(__name__)
_key_file = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '.secret_key')
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ.get("SECRET_KEY")
elif os.path.exists(_key_file):
    with open(_key_file) as _f:
        app.secret_key = _f.read().strip()
else:
    _new_key = _secrets.token_hex(24)
    with open(_key_file, 'w') as _f:
        _f.write(_new_key)
    app.secret_key = _new_key

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

ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.mp4', '.webm', '.mp3', '.wav',
    '.pdf', '.docx', '.txt', '.xlsx', '.pptx',
    '.csv', '.zip',
    '.py', '.html', '.css', '.js', '.php'
}

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


def save_admin_alert_if_needed(username, result, intel, decision):
    if decision.get("admin_alert"):
        create_admin_alert(
            username=username,
            rule_id=result.rule_id,
            risk_score=intel["risk_score"],
            threat_level=intel["threat_level"],
            decision=decision["action"]
        )


@app.route('/')
def home():
    print("[DEBUG] home() called")
    resp = make_response("", 302)
    resp.headers["Location"] = url_for('login')
    return resp


def detect_sql_payload_from_request(username, source_name):
    values_to_check = []

    for key, value in request.args.items():
        values_to_check.append((key, value))

    for key, value in request.form.items():
        values_to_check.append((key, value))

    if request.is_json:
        data = request.get_json(silent=True) or {}
        for key, value in data.items():
            values_to_check.append((key, str(value)))

    for field_name, value in values_to_check:
        result = check_sql_injection(username, value, field_name=field_name)

        if result.status == "BLOCK":
            intel = record_event_for_intelligence(username, result)

            ai_prediction = predict_threat(
                failed_logins=0,
                messages=0,
                sql_injection=1,
                dangerous_file=0
            )

            decision = final_security_decision(
                result=result,
                intelligence=intel,
                ai_prediction=ai_prediction,
                context="request"
            )

            save_threat_log(
                username=username,
                event_type=source_name,
                description=result.message,
                rule_triggered=result.rule_id,
                risk_score=intel["risk_score"],
                threat_level=intel["threat_level"],
                ai_prediction=ai_prediction,
                status=result.status,
                final_decision=decision["action"]
            )

            save_admin_alert_if_needed(username, result, intel, decision)
            return result

    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        sql_result = detect_sql_payload_from_request(
            request.form.get("username", "unknown"),
            "LOGIN_SQL_PAYLOAD_CHECK"
        )

        if sql_result:
            error = "Suspicious input detected. Login blocked."
            return render_template('login.html', error=error)

        if not username or not password:
            error = "Invalid credentials"
            return render_template('login.html', error=error)

        # result = login_user(username, password)
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
        sql_result = detect_sql_payload_from_request(
            request.form.get("username", "unknown"),
            "REGISTER_SQL_PAYLOAD_CHECK"
        )

        if sql_result:
            error = "Suspicious input detected. Registration blocked."
            return render_template('register.html', error=error)

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
    sql_result = detect_sql_payload_from_request(
        session.get("user", "unknown"),
        "URL_SQL_PAYLOAD_CHECK"
    )

    if sql_result:
        return jsonify({"error": "Suspicious URL parameter detected"}), 403

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

            # Forward uploaded files/images/audio to receiver
            if msg.get("type") in ["file", "image", "audio"]:
                receiver = msg.get("receiver")

            if msg.get("type") in ["file", "image", "audio"]:
                receiver = msg.get("receiver")

                payload = json.dumps({
                    "type": msg.get("type"),
                    "sender": username,
                    "receiver": receiver,
                    "url": msg.get("url"),
                    "filename": msg.get("filename"),
                    "abnormal_file_detected": msg.get("abnormal_file_detected", False),
                    "dangerous_file_detected": msg.get("dangerous_file_detected", False),
                    "timestamp": datetime.utcnow().isoformat()
                })

                print(
                    f"[DEBUG] Forwarding media: {msg.get('type')} from {username} to {receiver}")
                print("[DEBUG] Active connections:", list(connections.keys()))

                if receiver in connections:
                    connections[receiver].send(payload)
                    print("[DEBUG] Media forwarded to receiver")
                else:
                    print("[DEBUG] Receiver not connected")

                    continue

                payload = json.dumps({
                    "type": msg.get("type"),
                    "sender": username,
                    "receiver": receiver,
                    "url": msg.get("url"),
                    "filename": msg.get("filename"),
                    "abnormal_file_detected": msg.get("abnormal_file_detected", False),
                    "dangerous_file_detected": msg.get("dangerous_file_detected", False),
                    "timestamp": datetime.utcnow().isoformat()
                })

                print("[DEBUG] Forwarding media:", msg.get(
                    "type"), "from", username, "to", receiver)
                print("[DEBUG] Active connections:", list(connections.keys()))

                if receiver in connections:
                    connections[receiver].send(payload)
                    print("[DEBUG] Media forwarded to receiver")
                else:
                    print("[DEBUG] Receiver not connected")

                continue

            # --- Handle encrypted text messages ---
            if "ciphertext" in msg and "nonce" in msg:
                ciphertext = msg.get("ciphertext")
                nonce = msg.get("nonce")
                sql_payload_detected = bool(
                    msg.get("sql_payload_detected", False))

                results = []

                if sql_payload_detected:
                    sql_result = check_sql_payload_for_chat(
                        username,
                        "' OR 1=1 --",
                        field_name="client_chat_message"
                    )
                    results.append(sql_result)

                message_result = check_message_rate(username)
                results.append(message_result)

                message_count = 0
                sql_injection_flag = 0
                dangerous_file_flag = 0
                latest_intel = None
                blocking_result = None
                decision = None

                for result in results:
                    message_count = max(
                        message_count,
                        result.evidence.get("message_count", 0)
                    )

                    if result.rule_id == "R6" and result.status == "BLOCK":
                        sql_injection_flag = 1

                    if should_block(result):
                        blocking_result = result

                ai_prediction = predict_threat(
                    failed_logins=0,
                    messages=message_count,
                    sql_injection=sql_injection_flag,
                    dangerous_file=dangerous_file_flag
                )

                for result in results:
                    latest_intel = record_event_for_intelligence(
                        username, result)

                    decision = final_security_decision(
                        result=result,
                        intelligence=latest_intel,
                        ai_prediction=ai_prediction,
                        context="chat"
                    )

                    save_threat_log(
                        username=username,
                        event_type="WEBSOCKET_TEXT_CHECK",
                        description=result.message,
                        rule_triggered=result.rule_id,
                        risk_score=latest_intel["risk_score"],
                        threat_level=latest_intel["threat_level"],
                        ai_prediction=ai_prediction,
                        message_count=message_count,
                        file_count=0,
                        status=result.status,
                        final_decision=decision["action"]
                    )

                    save_admin_alert_if_needed(
                        username, result, latest_intel, decision)

                if decision and decision["allow"] is False:
                    ws.send(json.dumps({
                        "type": "security_alert",
                        "message": public_message(blocking_result),
                        "rule_id": blocking_result.rule_id if blocking_result else "UNKNOWN",
                        "threat_level": latest_intel["threat_level"] if latest_intel else "HIGH",
                        "risk_score": latest_intel["risk_score"] if latest_intel else 100,
                        "findings": latest_intel["correlation_findings"] if latest_intel else [],
                        "ai_prediction": ai_prediction,
                    }))
                    continue

                if not receiver or not ciphertext or not nonce:
                    print(f"[DEBUG] Invalid text message from {username}")
                    continue

                spam_detected = message_result.rule_id == "R4" and message_result.status == "ALERT"

                payload = json.dumps({
                    "type": "text",
                    "sender": username,
                    "receiver": receiver,
                    "ciphertext": ciphertext,
                    "nonce": nonce,
                    "sql_payload_detected": sql_payload_detected,
                    "spam_detected": spam_detected,
                    "timestamp": datetime.now().isoformat()
                })

                # Save to DB
                try:
                    save_message(username, receiver, ciphertext, nonce)
                    print(
                        f"[DEBUG] Saved text message from {username} to {receiver}")
                except Exception as e:
                    print(f"[DEBUG] Failed to save text message: {e}")

                # Forward to receiver
                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(
                            f"[DEBUG] Forwarded text message from {username} to {receiver}")
                    except Exception as e:
                        print(
                            f"[DEBUG] Failed to send text message to {receiver}: {e}")

            # --- Handle file/image messages from frontend ---
            elif msg.get("type") in ["file", "image"]:
                print(
                    f"[DEBUG] Received {msg.get('type')} message from {username}: {msg}")

                receiver = msg.get("receiver")
                url = msg.get("url")
                filename = msg.get("filename") or os.path.basename(
                    urlparse(url).path)

                if not receiver or not url:
                    print(
                        f"[DEBUG] Invalid {msg.get('type')} message from {username}")
                    continue

                payload = json.dumps({
                    "type": msg.get("type"),
                    "sender": username,
                    "receiver": receiver,
                    "url": url,
                    "filename": filename,
                    "dangerous_file_detected": bool(msg.get("dangerous_file_detected", False)),
                    "abnormal_file_detected": bool(msg.get("abnormal_file_detected", False)),
                    "timestamp": datetime.now().isoformat()
                })

                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(
                            f"[DEBUG] Forwarded {msg.get('type')} from {username} to {receiver}")
                    except Exception as e:
                        print(
                            f"[DEBUG] Failed to forward {msg.get('type')} to {receiver}: {e}")
                else:
                    print(
                        f"[DEBUG] Receiver {receiver} not connected. Message saved only.")

            # --- Handle call signaling ---
            elif msg.get("type") in ["call-offer", "call-answer", "ice-candidate", "call-end", "call-missed"]:
                print(f"[DEBUG] Received {msg['type']} from {username}: {msg}")

                if not receiver:
                    print(
                        f"[DEBUG] Invalid {msg['type']} message from {username} — missing receiver")
                    continue

                payload = json.dumps({
                    "sender": username,
                    "receiver": receiver,
                    "type": msg["type"],
                    # audio or video — must be forwarded
                    "callType": msg.get("callType"),
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
                            # "ended" or "missed"
                            status=msg.get("status"),
                            duration=msg.get("duration"),   # seconds if ended
                            timestamp=datetime.utcnow()
                        )

                        db.session.add(new_message)
                        db.session.commit()
                        print(
                            f"[DEBUG] Saved call log in DB for {username} -> {receiver}")
                    except Exception as e:
                        db.session.rollback()
                        print(f"[DEBUG] Failed to save call log: {e}")

                # Forward signaling payload
                if receiver in connections:
                    try:
                        connections[receiver].send(payload)
                        print(
                            f"[DEBUG] Forwarded {msg['type']} from {username} to {receiver}")
                    except Exception as e:
                        print(
                            f"[DEBUG] Failed to forward {msg['type']} to {receiver}: {e}")
                else:
                    print(
                        f"[DEBUG] Receiver {receiver} not connected, cannot forward {msg['type']}")

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
            if row[5] in ("file", "image") and row[4] else None,
            "timestamp": row[6].isoformat() if isinstance(row[6], datetime) else row[6]
        }

        # Add extra fields for call logs
        if row[5] == "call":
            entry["status"] = row[7] if len(
                row) > 7 else None   # e.g. "ended", "missed"
            entry["duration"] = row[8] if len(
                row) > 8 else None  # seconds or formatted string

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
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048)
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


@app.route("/chat-threat-check", methods=["POST"])
def chat_threat_check():
    data = request.get_json(force=True)

    username = data.get("username", "tester")
    detected_type = data.get("type", "")

    if detected_type != "sql_payload":
        return jsonify({"error": "Use type = sql_payload"}), 400

    result = check_sql_payload_for_chat(
        username,
        "' OR 1=1 --",
        field_name="chat_message"
    )

    intel = record_event_for_intelligence(username, result)

    ai_prediction = predict_threat(
        failed_logins=0,
        messages=0,
        sql_injection=1,
        dangerous_file=0
    )

    decision = final_security_decision(
        result=result,
        intelligence=intel,
        ai_prediction=ai_prediction,
        context="chat"
    )

    save_threat_log(
        username=username,
        event_type="CHAT_SQL_PAYLOAD_CHECK",
        description=result.message,
        rule_triggered=result.rule_id,
        risk_score=intel["risk_score"],
        threat_level=intel["threat_level"],
        ai_prediction=ai_prediction,
        status=result.status,
        final_decision=decision["action"]
    )

    save_admin_alert_if_needed(username, result, intel, decision)

    return jsonify({
        "rule_id": result.rule_id,
        "status": result.status,
        "severity": result.severity,
        "message": result.message,
        "threat_level": intel["threat_level"],
        "risk_score": intel["risk_score"],
        "findings": intel["correlation_findings"],
        "ai_prediction": ai_prediction
    })


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

    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 403

    if "file" not in request.files:
        return jsonify({"error": "Missing file"}), 400

    try:
        file = request.files["file"]
        receiver = request.form.get("receiver")

        if not receiver:
            return jsonify({"error": "Missing receiver"}), 400

        filename = secure_filename(file.filename)
        file_size = request.content_length or 0

        file_result = check_file_upload(session["user"], filename, file_size)
        intel = record_event_for_intelligence(session["user"], file_result)

        dangerous_file_flag = 1 if file_result.rule_id == "R7" else 0

        ai_prediction = predict_threat(
            failed_logins=0,
            messages=0,
            sql_injection=0,
            dangerous_file=dangerous_file_flag
        )

        decision = final_security_decision(
            result=file_result,
            intelligence=intel,
            ai_prediction=ai_prediction,
            context="file_upload"
        )

        save_threat_log(
            username=session["user"],
            event_type="UPLOAD_FILE_CHECK",
            description=file_result.message,
            rule_triggered=file_result.rule_id,
            risk_score=intel["risk_score"],
            threat_level=intel["threat_level"],
            ai_prediction=ai_prediction,
            file_count=file_result.evidence.get("file_count_5min", 0),
            status=file_result.status,
            final_decision=decision["action"]
        )

        save_admin_alert_if_needed(
            session["user"], file_result, intel, decision)

        if decision["allow"] is False:
            return jsonify({
                "type": "security_alert",
                "message": decision["user_message"],
                "rule_id": file_result.rule_id,
                "risk_score": intel["risk_score"],
                "threat_level": intel["threat_level"],
                "ai_prediction": ai_prediction,
                "decision": decision["action"]
            }), 403

        ext = os.path.splitext(filename)[1].lower() or ".dat"

        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({
                "type": "security_alert",
                "message": "Unsupported file type.",
                "rule_id": file_result.rule_id,
                "risk_score": intel["risk_score"],
                "threat_level": intel["threat_level"],
                "ai_prediction": ai_prediction,
                "decision": decision["action"]
            }), 400

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        unique_name = f"{session['user']}_{timestamp}{ext}"

        if os.environ.get("USE_SUPABASE") == "true":
            file_bytes = file.read()
            supabase.storage.from_("uploads").upload(unique_name, file_bytes)
            url = supabase.storage.from_("uploads").get_public_url(unique_name)
        else:
            filepath = os.path.join(UPLOAD_FOLDER, unique_name)
            file.save(filepath)
            url = url_for("uploaded_file",
                          filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="file",
            timestamp=datetime.utcnow()
        )

        db.session.add(new_message)
        db.session.commit()
        message_timestamp = datetime.utcnow().isoformat() + "Z"

        payload = json.dumps({
            "type": "file",
            "sender": session["user"],
            "receiver": receiver,
            "url": url,
            "filename": unique_name,
            "dangerous_file_detected": file_result.rule_id == "R7",
            "abnormal_file_detected": file_result.rule_id == "R5",
            "timestamp": message_timestamp
        })

        # if receiver in connections:
        #     connections[receiver].send(payload)

        # print("[DEBUG] receiver:", receiver)
        # print("[DEBUG] active connections:", list(connections.keys()))
        # print("[DEBUG] receiver online?", receiver in connections)

        # if receiver in connections:
        #     connections[receiver].send(payload)
        #     print("[DEBUG] File sent to receiver")
        # else:
        #     print("[DEBUG] Receiver not connected, file saved only")

        # print("[DEBUG] receiver:", receiver)
        print("[DEBUG] active connections:", list(connections.keys()))
        print("[DEBUG] receiver online?", receiver in connections)
        print("[DEBUG] File uploaded. chat.js will forward it through WebSocket.")

        # if receiver in connections:
        #     try:
        #         connections[receiver].send(payload)
        #         print("[DEBUG] File sent to receiver")
        #     except Exception as e:
        #         print("[DEBUG] Failed to send file to receiver:", e)
        # else:
        #     print("[DEBUG] Receiver not connected, file saved only")

        timestamp = datetime.utcnow().isoformat()
        return jsonify({
            "status": "success",
            "url": url,
            "filename": unique_name,
            "timestamp": timestamp
        }), 201

    except Exception as e:
        db.session.rollback()
        print("[DEBUG] Failed to store file message:", e)
        import traceback
        traceback.print_exc()
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
            url = url_for("uploaded_file",
                          filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="image",
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()
        message_timestamp = datetime.utcnow().isoformat() + "Z"

        payload = json.dumps({
            "type": "image",
            "sender": session["user"],
            "receiver": receiver,
            "url": url,
            "filename": unique_name,
            "timestamp": message_timestamp
        })

        # print("[DEBUG] receiver:", receiver)
        print("[DEBUG] active connections:", list(connections.keys()))
        print("[DEBUG] receiver online?", receiver in connections)
        print("[DEBUG] Image uploaded. chat.js will forward it through WebSocket.")

        # if receiver in connections:
        #     try:
        #         connections[receiver].send(payload)
        #         print("[DEBUG] Image sent to receiver")
        #     except Exception as e:
        #         print("[DEBUG] Failed to send image to receiver:", e)
        # else:
        #     print("[DEBUG] Receiver not connected, image saved only")

        return jsonify({
            "status": "success",
            "url": url,
            "filename": unique_name,
            "timestamp": message_timestamp
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
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

        ext = os.path.splitext(secure_filename(audio.filename))[
            1].lower() or ".webm"
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
            url = url_for("uploaded_file",
                          filename=unique_name, _external=True)

        new_message = Message(
            sender=session["user"],
            receiver=receiver,
            file_name=unique_name,
            msg_type="audio",
            timestamp=datetime.utcnow()
        )

        db.session.add(new_message)
        db.session.commit()
        message_timestamp = datetime.utcnow().isoformat() + "Z"
        print("[DEBUG] Audio message stored in DB")

        # Optional: broadcast to receiver only
        payload = json.dumps({
            "sender": session["user"],
            "receiver": receiver,
            "url": url,
            "filename": unique_name,
            "type": "audio",
            "timestamp": message_timestamp
        })
        if receiver in connections:
            try:
                connections[receiver].send(payload)
            except Exception as e:
                print(
                    f"[DEBUG] Failed to forward audio message to {receiver}: {e}")

        return jsonify({
            "status": "success",
            "url": url,
            "filename": unique_name,
            "timestamp": message_timestamp
        }), 201

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
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
        resp = send_from_directory(
            UPLOAD_FOLDER, filename, as_attachment=False)
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


@app.route("/admin/logs")
def admin_logs():
    logs = get_security_logs()
    return render_template("admin_logs.html", logs=logs)


@app.route("/admin/alerts")
def admin_alerts():
    alerts = get_admin_alerts()
    return render_template("admin_alerts.html", alerts=alerts)


@app.route("/admin/intelligence")
def admin_intelligence():
    logs = get_security_logs()
    users = {}

    def generate_findings(rules):
        findings = []

        if "R1" in rules and "R2" in rules:
            findings.append(
                "Possible account takeover: failed login followed by successful login.")

        if "R1" in rules and "R3" in rules:
            findings.append(
                "Possible brute force attack: repeated failed login caused account lock.")

        if "R4" in rules and "R5" in rules:
            findings.append(
                "Possible spam abuse: many messages and many files.")

        if "R4" in rules and "R6" in rules:
            findings.append(
                "Possible automated attack: spam behavior combined with SQL-like payload.")

        if "R5" in rules and "R7" in rules:
            findings.append(
                "Possible unsafe file sharing: abnormal upload plus high-risk file type.")

        if "R2" in rules and "R7" in rules:
            findings.append(
                "Possible compromised account: suspicious login followed by high-risk file upload.")

        if not findings:
            findings.append(
                "No strong correlation pattern yet. Monitoring continues.")

        return findings

    for log in logs:
        username = log[0]
        rule = log[2]
        risk_score = int(log[4] or 0)
        ai_prediction = log[6] or "UNKNOWN"

        if username not in users:
            users[username] = {
                "rules": set(),
                "risk_score": 0,
                "trend_score": 0,
                "event_count": 0,
                "latest_ai": ai_prediction,
            }

        if rule:
            users[username]["rules"].add(str(rule))

        users[username]["risk_score"] = min(
            100, max(users[username]["risk_score"], risk_score))
        users[username]["trend_score"] += risk_score
        users[username]["event_count"] += 1
        users[username]["latest_ai"] = ai_prediction

    for username, data in users.items():
        final_score = data["risk_score"]
        trend_score = data["trend_score"]
        event_count = data["event_count"]

        if trend_score >= 500 or event_count >= 100:
            data["threat_level"] = "CRITICAL"
            data["final_decision"] = "TEMP_LOCK"
        elif final_score >= 80:
            data["threat_level"] = "HIGH"
            data["final_decision"] = "ADMIN_REVIEW"
        elif final_score >= 40:
            data["threat_level"] = "MEDIUM"
            data["final_decision"] = "RATE_LIMIT"
        elif final_score >= 20:
            data["threat_level"] = "LOW"
            data["final_decision"] = "WARN"
        else:
            data["threat_level"] = "NORMAL"
            data["final_decision"] = "ALLOW"

        data["findings"] = generate_findings(data["rules"])

        if event_count >= 100:
            data["findings"].append(
                "Persistent attacker behavior detected. Extremely high number of suspicious events."
            )

    return render_template("admin_intelligence.html", users=users)


@app.route("/admin/block/<username>", methods=["POST"])
def admin_block_user(username):
    conn = get_db()
    cur = conn.cursor()

    ph = "%s" if os.environ.get("DATABASE_URL") else "?"

    cur.execute(
        f"UPDATE users SET is_blocked=1 WHERE username={ph}",
        (username,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_intelligence"))


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
