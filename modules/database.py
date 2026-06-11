import sqlite3, time
from datetime import datetime

def get_db():
    return sqlite3.connect("database.db", check_same_thread=False)

def get_columns(cur, table):
    """Return a set of existing column names for a table."""
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}

# ── User queries ───────────────────────────────────────────────────────────────

def get_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE is_blocked = 0")
    users = cur.fetchall()
    conn.close()
    return users

def get_friends(username):
    """Return accepted connections for a user as (username,) tuples."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT CASE WHEN sender=? THEN receiver ELSE sender END AS friend
        FROM connections
        WHERE (sender=? OR receiver=?) AND status='accepted'
        ORDER BY friend
    ''', (username, username, username))
    friends = cur.fetchall()
    conn.close()
    return friends

def get_pending_requests(username):
    """Return pending connection requests sent TO this user."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT sender, created_at FROM connections WHERE receiver=? AND status='pending' ORDER BY created_at DESC",
        (username,)
    )
    requests = cur.fetchall()
    conn.close()
    return requests

def search_users(query, current_user):
    """
    Search users by username, excluding:
      - the current user
      - blocked users
      - users already connected or with a pending request (either direction)
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT username FROM users
        WHERE username LIKE ?
          AND username != ?
          AND is_blocked = 0
          AND username NOT IN (
              SELECT CASE WHEN sender=? THEN receiver ELSE sender END
              FROM connections
              WHERE sender=? OR receiver=?
          )
    ''', (f'%{query}%', current_user, current_user, current_user, current_user))
    results = cur.fetchall()
    conn.close()
    return results

# ── Connection management ──────────────────────────────────────────────────────

def send_connection_request(sender, receiver):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO connections (sender, receiver, status) VALUES (?, ?, 'pending')",
            (sender, receiver)
        )
        conn.commit()
        return "success"
    except sqlite3.IntegrityError:
        return "already_exists"
    finally:
        conn.close()

def accept_connection(sender, receiver):
    """Accept the request that `sender` sent to `receiver`."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE connections SET status='accepted' WHERE sender=? AND receiver=? AND status='pending'",
        (sender, receiver)
    )
    conn.commit()
    conn.close()

def reject_connection(sender, receiver):
    """Delete/reject the pending request."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM connections WHERE sender=? AND receiver=? AND status='pending'",
        (sender, receiver)
    )
    conn.commit()
    conn.close()

# ── Messages ───────────────────────────────────────────────────────────────────

def save_message(sender, receiver, ciphertext, nonce):
    for attempt in range(5):
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages (sender, receiver, ciphertext, nonce, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (sender, receiver, ciphertext, nonce, datetime.now()))
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                print("DB locked, retrying...")
                time.sleep(0.1)
            else:
                raise

def get_chat_history(user1, user2):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT sender, receiver, ciphertext, nonce, timestamp
        FROM messages
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        ORDER BY timestamp
    """, (user1, user2, user2, user1))
    history = cur.fetchall()
    conn.close()
    return history

# ── Schema setup + migrations ──────────────────────────────────────────────────

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        username         TEXT UNIQUE,
        password         TEXT,
        failed_attempts  INTEGER DEFAULT 0,
        is_blocked       INTEGER DEFAULT 0
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT,
        event_type  TEXT,
        description TEXT,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        sender      TEXT NOT NULL,
        receiver    TEXT NOT NULL,
        ciphertext  TEXT NOT NULL,
        nonce       TEXT NOT NULL,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS connections (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        sender     TEXT NOT NULL,
        receiver   TEXT NOT NULL,
        status     TEXT DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sender, receiver)
    )
    ''')

    # ── Migrations: safely add missing columns to existing tables ──────────────
    users_cols = get_columns(cur, 'users')
    if 'failed_attempts' not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0")
        print("[DB] Migration: added users.failed_attempts")
    if 'is_blocked' not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        print("[DB] Migration: added users.is_blocked")

    logs_cols = get_columns(cur, 'logs')
    if 'timestamp' not in logs_cols:
        cur.execute("ALTER TABLE logs ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        print("[DB] Migration: added logs.timestamp")

    messages_cols = get_columns(cur, 'messages')
    if 'timestamp' not in messages_cols:
        cur.execute("ALTER TABLE messages ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        print("[DB] Migration: added messages.timestamp")

    conn.commit()
    conn.close()
