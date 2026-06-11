from modules.database import get_db
from modules.threat_detection import log_event
import hashlib, os

# Decide placeholder style based on environment
ph = "%s" if os.environ.get("DATABASE_URL") else "?"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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

    hashed = hash_password(password)

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

    if hashed != db_password:
        attempts += 1
        if attempts >= 5:
            cur.execute(
                f"UPDATE users SET failed_attempts={ph}, is_blocked=1 WHERE username={ph}",
                (attempts, username)
            )
            conn.commit()
            log_event(username, "ACCOUNT_BLOCKED", "Too many failed attempts")
            conn.close()
            return "Account blocked due to too many failed attempts"

        remaining = 5 - attempts
        cur.execute(
            f"UPDATE users SET failed_attempts={ph} WHERE username={ph}",
            (attempts, username)
        )
        conn.commit()
        log_event(username, "LOGIN_FAIL", f"Wrong password ({attempts} attempts)")
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
    conn.close()
    return "success"
