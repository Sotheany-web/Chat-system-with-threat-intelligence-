import sqlite3, time
from datetime import datetime

def get_db():
    return sqlite3.connect("database.db", check_same_thread=False)

def get_columns(cur, table):
    """Return a set of existing column names for a table."""
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}

def get_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE is_blocked = 0")
    users = cur.fetchall()
    conn.close()
    return users

def save_message(sender, receiver, ciphertext, nonce):
    for attempt in range(5):  # retry up to 5 times on DB lock
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

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # ── Create tables if they don't exist ─────────────────────────────────────
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

    # ── Migrations: add any missing columns to existing tables ────────────────
    # If the table already existed before a column was added, this ensures
    # the column gets added without losing any data.

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
