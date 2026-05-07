import sqlite3, time 
from datetime import datetime

def get_db():
    return sqlite3.connect("database.db", check_same_thread=False)

def get_all_users():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users")
    users = cur.fetchall()

    conn.close()
    return users

def save_message(sender, receiver, ciphertext, nonce):
    for attempt in range(5):  # retry up to 5 times
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

    # users table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        failed_attempts INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0
    )
    ''')
    # logs table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        event_type TEXT,
        description TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # messages table (ciphertext + nonce only)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        receiver TEXT NOT NULL,
        ciphertext TEXT NOT NULL,
        nonce TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()