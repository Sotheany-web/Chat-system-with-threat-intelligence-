from modules.database import get_db
from modules.threat_detection import log_event
import hashlib
import os

def hash_password(password):
    """Hash password with a random salt using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex() + ':' + hashed.hex()

def verify_password(stored_password, provided_password):
    """
    Verify a password against the stored hash.
    Supports both:
      - New format:    salt_hex:hash_hex  (PBKDF2, secure)
      - Legacy format: plain sha256 hex   (old accounts, no salt)
    """
    try:
        if ':' in stored_password:
            # New secure format
            salt_hex, hash_hex = stored_password.split(':', 1)
            salt = bytes.fromhex(salt_hex)
            hashed = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt, 100000)
            return hashed.hex() == hash_hex
        else:
            # Legacy fallback — plain SHA-256 (no salt)
            legacy_hash = hashlib.sha256(provided_password.encode()).hexdigest()
            return legacy_hash == stored_password
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

    cur.execute("SELECT username FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return "Username already exists"

    hashed = hash_password(password)

    try:
        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
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

    cur.execute(
        "SELECT password, failed_attempts, is_blocked FROM users WHERE username=?",
        (username,)
    )

    user = cur.fetchone()
    print("DEBUG user raw:", user)

    if not user:
        log_event(username, "LOGIN_FAIL", "User not found")
        conn.close()
        return "Invalid credentials"

    db_password, attempts, blocked = user

    print("DEBUG attempts from DB:", attempts, type(attempts))

    if blocked:
        log_event(username, "LOGIN_FAIL", "User is blocked")
        conn.close()
        return "Account is blocked due to multiple failed login attempts"

    if not verify_password(db_password, password):
        attempts += 1

        if attempts >= 5:
            cur.execute(
                "UPDATE users SET failed_attempts=?, is_blocked=1 WHERE username=?",
                (attempts, username)
            )
            conn.commit()
            log_event(username, "ACCOUNT_BLOCKED", "Too many failed attempts")
            conn.close()
            return "Account blocked due to too many failed attempts"

        remaining = 5 - attempts

        cur.execute(
            "UPDATE users SET failed_attempts=? WHERE username=?",
            (attempts, username)
        )
        conn.commit()
        log_event(username, "LOGIN_FAIL", f"Wrong password ({attempts} attempts)")
        conn.close()

        if attempts >= 3:
            return f"Invalid credentials ({remaining} tries left)"

        return "Invalid credentials"

    # Success — reset failed attempts
    cur.execute(
        "UPDATE users SET failed_attempts=0 WHERE username=?",
        (username,)
    )
    conn.commit()
    log_event(username, "LOGIN_SUCCESS", "User logged in")
    conn.close()

    return "success"
