from modules.database import get_db, save_threat_log
from modules.ai_intelligence import predict_threat

from modules.threat_detection import (
    log_event,
    check_failed_login,
    check_successful_login,
    record_event_for_intelligence,
    response_decision
)
import hashlib
import hmac
import os

# Decide placeholder style based on environment
ph = "%s" if os.environ.get("DATABASE_URL") else "?"


def hash_password(password):
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000)
    return salt.hex() + ':' + h.hex()


def verify_password(stored, provided):
    try:
        salt_hex, hash_hex = stored.split(':', 1)
        h = hashlib.pbkdf2_hmac(
            'sha256', provided.encode(), bytes.fromhex(salt_hex), 200000)
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:
        return False


def register_user(username, password):
    conn = get_db()
    cur = conn.cursor()

    if not username or not password:
        conn.close()
        return "Username and password are required"

    username = username.strip()
    password = password.strip()

    if len(password) < 6:
        conn.close()
        return "Weak password: must be at least 6 characters"

    if password.isdigit() and len(set(password)) == 1:
        conn.close()
        return "Weak password: cannot be all same numbers"

    # Duplicate user check
    cur.execute(f"SELECT username FROM users WHERE username={ph}", (username,))
    if cur.fetchone():
        conn.close()
        return "Username already exists"

    hashed = hash_password(password)

    try:
        cur.execute(
            f"INSERT INTO users (username, password) VALUES ({ph}, {ph})",
            (username, hashed)
        )
        conn.commit()
        log_event(username, "REGISTER_SUCCESS", "User created")
        conn.close()
        return "success"
    except Exception as e:
        log_event(username, "REGISTER_FAIL", str(e))
        conn.close()
        return "Registration error"


def login_user(username, password):
    conn = get_db()
    cur = conn.cursor()

    # Get user safely
    cur.execute(
        f"SELECT password, failed_attempts, is_blocked FROM users WHERE username={ph}",
        (username,)
    )
    user = cur.fetchone()

    if not user:
        log_event(username, "LOGIN_FAIL", "User not found")
        conn.close()
        return "Invalid credentials"

    db_password, attempts, blocked = user

    if blocked:
        log_event(username, "LOGIN_FAIL", "User is blocked")
        conn.close()
        return "Account is blocked due to multiple failed login attempts"

    if not verify_password(db_password, password):

        detection = check_failed_login(username)
        intel = record_event_for_intelligence(username, detection)
        ai_prediction = predict_threat(
            failed_logins=attempts + 1,
            messages=0,
            sql_injection=0,
            dangerous_file=0
        )

        save_threat_log(
            username=username,
            event_type="LOGIN_FAIL_CHECK",
            description=detection.message,
            rule_triggered=detection.rule_id,
            risk_score=intel["risk_score"],
            threat_level=intel["threat_level"],
            ai_prediction=ai_prediction,
            status=detection.status
        )

        decision = response_decision(intel)

        print("LOGIN INTELLIGENCE:", intel)
        print("RESPONSE DECISION:", decision)

        attempts += 1
        if attempts >= 10:
            cur.execute(
                f"UPDATE users SET failed_attempts={ph}, is_blocked=1 WHERE username={ph}",
                (attempts, username)
            )
            conn.commit()
            log_event(username, "ACCOUNT_BLOCKED", "Too many failed attempts")
            conn.close()
            return "Account blocked due to too many failed attempts"

        remaining = 10 - attempts
        cur.execute(
            f"UPDATE users SET failed_attempts={ph} WHERE username={ph}",
            (attempts, username)
        )
        conn.commit()
        log_event(username, "LOGIN_FAIL",
                  f"Wrong password ({attempts} attempts)")
        conn.close()

        if attempts >= 3:
            return f"Invalid credentials ({remaining} tries left)"
        return "Invalid credentials"

    # Success
    cur.execute(
        f"UPDATE users SET failed_attempts=0 WHERE username={ph}",
        (username,)
    )
    conn.commit()
    log_event(username, "LOGIN_SUCCESS", "User logged in")
    detection = check_successful_login(username)
    intel = record_event_for_intelligence(username, detection)
    ai_prediction = predict_threat(
        failed_logins=0,
        messages=0,
        sql_injection=0,
        dangerous_file=0
    )

    save_threat_log(
        username=username,
        event_type="LOGIN_SUCCESS_CHECK",
        description=detection.message,
        rule_triggered=detection.rule_id,
        risk_score=intel["risk_score"],
        threat_level=intel["threat_level"],
        ai_prediction=ai_prediction,
        status=detection.status
    )

    decision = response_decision(intel)

    print("LOGIN SUCCESS INTELLIGENCE:", intel)
    print("RESPONSE DECISION:", decision)
    conn.close()
    return "success"
