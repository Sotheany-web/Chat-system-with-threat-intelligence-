from modules.database import get_db
from modules.threat_detection import log_event
import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    conn = get_db()
    cur = conn.cursor()

    #  1. REQUIRED FIELD CHECK
    if not username or not password:
        conn.close()
        return "Username and password are required"

    username = username.strip()
    password = password.strip()

    #  2. LENGTH CHECK
    if len(password) < 6:
        conn.close()
        return "Weak password: must be at least 6 characters"

    #  3. CHECK IF PASSWORD IS ALL SAME DIGIT
    if password.isdigit() and len(set(password)) == 1:
        conn.close()
        return "Weak password: cannot be all same numbers"

    #  4. CHECK DUPLICATE USER
    cur.execute("SELECT username FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return "Username already exists"

    #  5. HASH PASSWORD (SHA256 as required)
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

    hashed = hash_password(password)

    #  Get user safely
    cur.execute(
        "SELECT password, failed_attempts, is_blocked FROM users WHERE username=?",
        (username,)
    )

    user = cur.fetchone()
    print("DEBUG user raw:", user)
    

    #  SAME RESPONSE FOR ALL FAIL CASES (SECURITY FIX)
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

    if hashed != db_password:
        attempts += 1

        #  BLOCK ACCOUNT AFTER 5 FAILS
        if attempts >= 5:
            cur.execute(
                "UPDATE users SET failed_attempts=?, is_blocked=1 WHERE username=?",
                (attempts, username)
            )
            conn.commit()

            log_event(username, "ACCOUNT_BLOCKED", "Too many failed attempts")

            conn.close()
            return "Account blocked due to too many failed attempts"

        # WARNING SYSTEM
        remaining = 5 - attempts

        cur.execute(
            "UPDATE users SET failed_attempts=? WHERE username=?",
            (attempts, username)
        )

        conn.commit()

        log_event(username, "LOGIN_FAIL", f"Wrong password ({attempts} attempts)")

        conn.close()

        # show warning only after 3 attempts
        if attempts >= 3:
            return f"Invalid credentials ({remaining} tries left)"

        return "Invalid credentials"

    #  SUCCESS
    cur.execute(
        "UPDATE users SET failed_attempts=0 WHERE username=?",
        (username,)
    )

    conn.commit()
    log_event(username, "LOGIN_SUCCESS", "User logged in")
    conn.close()

    return "success"